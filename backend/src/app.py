"""FastAPI 애플리케이션 팩토리."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routers import bots, callbot_agents, calls, knowledge, mcp_servers, skills, tenants, tools, transcripts
from .api.ws import voice
from .infrastructure.db import Base, SessionLocal, engine
from .infrastructure.seed import seed_if_empty


def _migrate_sqlite_add_columns():
    """SQLite는 ALTER TABLE ADD COLUMN만 지원 — 누락된 컬럼을 비파괴적으로 추가."""
    from sqlalchemy import inspect, text

    pending = [
        ("bots", "branches", "TEXT DEFAULT '[]'"),
        ("bots", "voice_rules", "TEXT DEFAULT ''"),
        ("call_sessions", "dynamic_vars", "TEXT DEFAULT '{}'"),
        ("callbot_agents", "global_rules", "TEXT DEFAULT '[]'"),
        ("skills", "allowed_tool_names", "TEXT DEFAULT '[]'"),
        ("bots", "external_kb_enabled", "INTEGER DEFAULT 0"),
        ("bots", "external_kb_inquiry_types", "TEXT DEFAULT '[]'"),
    ]
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, col, decl in pending:
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            if col not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {decl}"))


def _backfill_callbot_agents(db):
    """기존 Bot들을 새 CallbotAgent + Membership 모델로 매핑.
    각 tenant마다 CallbotAgent가 없으면 1개 생성, 그 tenant의 Bot들을 멤버로 추가.
    가장 오래된 Bot (id 최소) = main, 나머지 = sub. branches → branch_trigger 이전.
    """
    from .infrastructure import models as M

    tenants = db.query(M.Tenant).all()
    for t in tenants:
        # 이미 CallbotAgent가 있으면 skip
        existing = db.query(M.CallbotAgent).filter(M.CallbotAgent.tenant_id == t.id).first()
        if existing:
            continue
        bots = db.query(M.Bot).filter(M.Bot.tenant_id == t.id).order_by(M.Bot.id).all()
        if not bots:
            continue
        primary = bots[0]
        callbot = M.CallbotAgent(
            tenant_id=t.id,
            name=f"{t.name} 콜봇",
            voice=primary.voice,
            greeting=primary.greeting,
            language=primary.language,
            llm_model=primary.llm_model,
        )
        db.add(callbot)
        db.flush()  # callbot.id 확보
        # 기존 branches: bot_id → branch_trigger 맵
        branch_triggers: dict[int, str] = {}
        for b in bots:
            for br in (b.branches or []):
                tgt = br.get("target_bot_id")
                if tgt and tgt not in branch_triggers:
                    branch_triggers[tgt] = br.get("trigger") or br.get("name") or ""
        for i, b in enumerate(bots):
            db.add(M.CallbotMembership(
                callbot_id=callbot.id,
                bot_id=b.id,
                role="main" if b.id == primary.id else "sub",
                order=i,
                branch_trigger=branch_triggers.get(b.id, "") if b.id != primary.id else "",
            ))
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_add_columns()
    db = SessionLocal()
    try:
        seed_if_empty(db)
        _backfill_callbot_agents(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Callbot Platform", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for r in [tenants.router, callbot_agents.router, bots.router, skills.router, knowledge.router, tools.router, mcp_servers.router, calls.router, transcripts.router]:
        app.include_router(r)
    app.include_router(voice.router)

    @app.get("/api/health")
    def health():
        from .infrastructure.adapters.factory import is_voice_mode_available

        return {"status": "ok", "voice_mode_available": is_voice_mode_available()}

    static_dir = Path(__file__).parent / "api" / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
