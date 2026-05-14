import datetime as _dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.bot_service import BotService
from ...application.skill_runtime import build_runtime
from ...domain.bot import Bot as DomainBot, DomainError
from ...infrastructure import models
from ...infrastructure.db import get_db
from ...infrastructure.repositories.bot_repository import SqlAlchemyBotRepository
from .. import schemas

router = APIRouter(prefix="/api/bots", tags=["bots"])


def get_bot_service(db: AsyncSession = Depends(get_db)) -> BotService:
    return BotService(SqlAlchemyBotRepository(db))


def _to_out(bot: DomainBot) -> dict:
    # 도메인 Bot → BotOut dict. created_at은 DB row에 있지만 도메인엔 없음 → 별도 조회 또는 default.
    return {
        "id": bot.id,
        "tenant_id": bot.tenant_id,
        "name": bot.name,
        "persona": bot.persona,
        "system_prompt": bot.system_prompt,
        "greeting": bot.greeting,
        "language": bot.language,
        "voice": bot.voice,
        "llm_model": bot.llm_model,
        "is_active": bot.is_active,
        "agent_type": bot.agent_type.value,
        "graph": bot.graph,
        "branches": bot.branches,
        "voice_rules": bot.voice_rules,
        "external_kb_enabled": bot.external_kb_enabled,
        "external_kb_inquiry_types": list(bot.external_kb_inquiry_types or []),
        "created_at": _dt.datetime.utcnow(),  # placeholder; UI는 created_at 거의 사용 안 함
    }


@router.get("", response_model=list[schemas.BotOut])
async def list_bots(tenant_id: int | None = None, svc: BotService = Depends(get_bot_service)):
    return [_to_out(b) for b in await svc.list(tenant_id=tenant_id)]


@router.post("", response_model=schemas.BotOut, status_code=status.HTTP_201_CREATED)
async def create_bot(payload: schemas.BotCreate, svc: BotService = Depends(get_bot_service), db: AsyncSession = Depends(get_db)):
    if not await db.get(models.Tenant, payload.tenant_id):
        raise HTTPException(400, "tenant not found")
    try:
        bot = await svc.create(**payload.model_dump())
    except DomainError as e:
        raise HTTPException(400, str(e))
    return _to_out(bot)


@router.get("/{bot_id}", response_model=schemas.BotOut)
async def get_bot(bot_id: int, svc: BotService = Depends(get_bot_service)):
    b = await svc.get(bot_id)
    if not b:
        raise HTTPException(404)
    return _to_out(b)


@router.patch("/{bot_id}", response_model=schemas.BotOut)
async def update_bot(bot_id: int, payload: schemas.BotUpdate, svc: BotService = Depends(get_bot_service)):
    try:
        b = await svc.update(bot_id, **payload.model_dump(exclude_unset=True))
    except DomainError as e:
        msg = str(e)
        raise HTTPException(404 if "없음" in msg else 400, msg)
    return _to_out(b)


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(bot_id: int, svc: BotService = Depends(get_bot_service)):
    await svc.delete(bot_id)


@router.get("/{bot_id}/runtime")
async def get_bot_runtime(bot_id: int, db: AsyncSession = Depends(get_db)):
    """런타임 합성 프롬프트 미리보기 (디버깅용)."""
    try:
        runtime, active = await build_runtime(db, bot_id, None)
    except ValueError:
        raise HTTPException(404)
    return {
        "bot_id": runtime.bot_id,
        "name": runtime.name,
        "language": runtime.language,
        "voice": runtime.voice,
        "llm_model": runtime.llm_model,
        "greeting": runtime.greeting,
        "active_skill": active,
        "system_prompt": runtime.system_prompt,
    }


@router.post("/{bot_id}/test-voice")
async def test_voice(bot_id: int, db: AsyncSession = Depends(get_db)):
    """봇의 현재 voice/language로 짧은 샘플 음성 합성 — 콘솔 미리듣기용.

    돌려주는 WAV 16k LINEAR16 raw bytes를 audio/wav 헤더 붙여 반환.
    voice_mode_available=false면 503.
    """
    from io import BytesIO
    import struct

    from fastapi import Response

    from ...infrastructure.adapters.factory import get_tts, is_voice_mode_available

    b = await db.get(models.Bot, bot_id)
    if not b:
        raise HTTPException(404)
    if not is_voice_mode_available():
        raise HTTPException(503, "voice mode unavailable (GCP creds 미설정)")

    # CallbotAgent 통화 일관 설정 우선 — sub.voice_override 있으면 그것
    from ...application.skill_runtime import _resolve_callbot_settings
    voice, _greet, language, _llm, _pron, _dtmf = await _resolve_callbot_settings(db, b)

    tts = get_tts()
    sample = f"안녕하세요, {b.name} 입니다. 보이스 테스트 중입니다."
    pcm = bytearray()
    try:
        async for chunk in tts.synthesize(
            text=sample, language=language, voice=voice, sample_rate=16000,
        ):
            pcm.extend(chunk)
    except Exception as e:
        raise HTTPException(500, f"TTS 실패: {type(e).__name__}: {e}")

    if not pcm:
        raise HTTPException(500, "TTS가 빈 오디오 반환")

    # raw LINEAR16 PCM → minimal WAV 헤더 부착 (mono, 16kHz, 16-bit)
    sr = 16000
    data = bytes(pcm)
    buf = BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(data)))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(data)))
    buf.write(data)
    return Response(
        content=buf.getvalue(),
        media_type="audio/wav",
        headers={"X-Voice": voice, "X-Language": language, "X-Bytes": str(len(data))},
    )


@router.get("/{bot_id}/env")
async def get_env(bot_id: int, reveal: bool = False, db: AsyncSession = Depends(get_db)):
    """환경변수 조회. reveal=true면 값 포함, 기본은 키 목록만."""
    b = await db.get(models.Bot, bot_id)
    if not b:
        raise HTTPException(404)
    env = b.env_vars or {}
    if reveal:
        return {"env_vars": env, "keys": list(env.keys())}
    return {"keys": list(env.keys())}


@router.put("/{bot_id}/env")
async def update_env(bot_id: int, payload: schemas.EnvVarsUpdate, db: AsyncSession = Depends(get_db)):
    """환경변수 전체 dict 갱신. 빈 값/공백 키는 제거."""
    b = await db.get(models.Bot, bot_id)
    if not b:
        raise HTTPException(404)
    cleaned = {k.strip(): v for k, v in (payload.env_vars or {}).items() if k and k.strip()}
    b.env_vars = cleaned
    await db.commit()
    return {"updated": True, "count": len(cleaned)}


@router.get("/{bot_id}/mentions")
async def list_mentions(bot_id: int, db: AsyncSession = Depends(get_db)):
    """`@` 자동완성용 — 봇이 가진 모든 스킬/지식/도구 이름 + 설명."""
    from ...application.skill_runtime import find_bot
    b = await find_bot(db, bot_id)
    if not b:
        raise HTTPException(404)
    items: list[dict] = []
    for s in b.skills:
        items.append({"kind": "skill", "name": s.name, "description": s.description or ""})
    for k in b.knowledge:
        items.append({"kind": "knowledge", "name": k.title, "description": (k.content or "")[:80]})
    for t in b.tools:
        if t.is_enabled:
            items.append({"kind": "tool", "name": t.name, "description": t.description or ""})
    # MCP 서버 도구도 mention 후보에 포함
    mcp_stmt = (
        select(models.MCPServer).where(
            models.MCPServer.bot_id == bot_id, models.MCPServer.is_enabled.is_(True)
        )
    )
    mcp_srvs = (await db.execute(mcp_stmt)).scalars().all()
    existing = {(i["kind"], i["name"]) for i in items}
    for srv in mcp_srvs:
        for mt in srv.discovered_tools or []:
            key = ("tool", mt.get("name", ""))
            if mt.get("name") and key not in existing:
                items.append({"kind": "tool", "name": mt["name"], "description": f"[MCP:{srv.name}] {mt.get('description', '')}"})
                existing.add(key)
    return {"items": items}
