"""FastAPI 애플리케이션 팩토리."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .api.routers import bots, callbot_agents, calls, knowledge, mcp_servers, skills, tags, tenants, tools, transcripts
from .api.ws import voice
from .infrastructure.db import SessionLocal
from .infrastructure.seed import seed_if_empty


def _run_alembic_upgrade() -> None:
    """startup 시 alembic upgrade head 자동 실행.
    K8s 환경에선 Init Container 로 빼는 게 더 깔끔하지만 일단 lifespan 통합.
    alembic env.py 가 내부적으로 asyncio.run 을 호출하므로, 외부 event loop 안에서는
    실행할 수 없다 → asyncio.to_thread 로 별도 스레드에서 실행한다.
    """
    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    command.upgrade(cfg, "head")


async def _backfill_callbot_agents(db):
    """기존 Bot들을 새 CallbotAgent + Membership 모델로 매핑.
    각 tenant마다 CallbotAgent가 없으면 1개 생성, 그 tenant의 Bot들을 멤버로 추가.
    가장 오래된 Bot (id 최소) = main, 나머지 = sub. branches → branch_trigger 이전.
    """
    from .infrastructure import models as M

    tenants_rows = (await db.execute(select(M.Tenant))).scalars().all()
    for t in tenants_rows:
        existing_stmt = select(M.CallbotAgent).where(M.CallbotAgent.tenant_id == t.id)
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            continue
        bots_stmt = select(M.Bot).where(M.Bot.tenant_id == t.id).order_by(M.Bot.id)
        bots_rows = list((await db.execute(bots_stmt)).scalars().all())
        if not bots_rows:
            continue
        primary = bots_rows[0]
        callbot = M.CallbotAgent(
            tenant_id=t.id,
            name=f"{t.name} 콜봇",
            voice=primary.voice,
            greeting=primary.greeting,
            language=primary.language,
            llm_model=primary.llm_model,
        )
        db.add(callbot)
        await db.flush()
        branch_triggers: dict[int, str] = {}
        for b in bots_rows:
            for br in (b.branches or []):
                tgt = br.get("target_bot_id")
                if tgt and tgt not in branch_triggers:
                    branch_triggers[tgt] = br.get("trigger") or br.get("name") or ""
        for i, b in enumerate(bots_rows):
            db.add(M.CallbotMembership(
                callbot_id=callbot.id,
                bot_id=b.id,
                role="main" if b.id == primary.id else "sub",
                order=i,
                branch_trigger=branch_triggers.get(b.id, "") if b.id != primary.id else "",
            ))
    await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # alembic upgrade — 별도 스레드에서 (env.py 내부의 asyncio.run 과 충돌 방지)
    await asyncio.to_thread(_run_alembic_upgrade)
    async with SessionLocal() as db:
        await seed_if_empty(db)
        await _backfill_callbot_agents(db)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Callbot Platform", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for r in [tenants.router, callbot_agents.router, bots.router, skills.router, knowledge.router, tools.router, mcp_servers.router, calls.router, transcripts.router, tags.router]:
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
