"""Skill 런타임 — Bot/Skill/Knowledge → 런타임 시스템 프롬프트 합성.

LLM 응답 마지막 줄의 JSON 신호({"next_skill":"..."} | {"tool":"..."})를 파싱한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..domain.entities import BotRuntime
from ..domain.prompts import build_system_prompt
from ..infrastructure import models
from .mentions import MentionTarget, expand_mentions


@dataclass
class LLMSignal:
    next_skill: str | None = None
    tool: str | None = None
    args: dict | None = None
    extracted: dict | None = None  # 사용자 발화에서 추출된 슬롯 (예: {"reservationNo": "ACM-..."})


def find_bot(db: Session, bot_id: int) -> models.Bot | None:
    return db.get(models.Bot, bot_id)


def find_frontdoor(bot: models.Bot) -> models.Skill | None:
    for s in bot.skills:
        if s.is_frontdoor:
            return s
    return bot.skills[0] if bot.skills else None


def find_skill_by_name(bot: models.Bot, name: str) -> models.Skill | None:
    for s in bot.skills:
        if s.name == name:
            return s
    return None


def _resolve_callbot_settings(db: Session, bot: models.Bot) -> tuple[str, str, str, str, dict, dict]:
    """봇이 속한 CallbotAgent의 통화 일관 설정을 우선 반환.
    sub 멤버라면 voice_override를 우선. CallbotAgent 없으면 Bot 자체값 fallback.

    Returns: (voice, greeting, language, llm_model, pronunciation_dict, dtmf_map)
    """
    membership = (
        db.query(models.CallbotMembership)
        .filter(models.CallbotMembership.bot_id == bot.id)
        .first()
    )
    if membership is None:
        return (
            bot.voice or "",
            bot.greeting or "",
            bot.language or "ko-KR",
            bot.llm_model or "gemini-3.1-flash-lite",
            {},
            {},
        )
    callbot = membership.callbot
    voice = membership.voice_override if membership.voice_override else callbot.voice
    return (
        voice,
        callbot.greeting,
        callbot.language,
        callbot.llm_model,
        callbot.pronunciation_dict or {},
        callbot.dtmf_map or {},
    )


def build_runtime(
    db: Session, bot_id: int, active_skill_name: str | None = None,
    auto_context: dict | None = None,
    variables: dict | None = None,
) -> tuple[BotRuntime, str | None]:
    """봇 + 활성 스킬로부터 런타임 시스템 프롬프트를 합성한다.

    Returns: (런타임, 선택된 스킬 이름)
    """
    bot = find_bot(db, bot_id)
    if bot is None:
        raise ValueError(f"Bot {bot_id} not found")

    active_skill = None
    if active_skill_name:
        active_skill = find_skill_by_name(bot, active_skill_name)
    if active_skill is None:
        active_skill = find_frontdoor(bot)

    others = [
        (s.name, s.description) for s in bot.skills if active_skill is None or s.id != active_skill.id
    ]
    knowledge_pairs = [(k.title, k.content) for k in bot.knowledge]
    # callbot_v0 흡수 — 스킬별 도구 화이트리스트로 LLM 노출 범위 제한.
    # active_skill.allowed_tool_names 가 비어있지 않으면 그 목록만 시스템 프롬프트에 보여줌.
    skill_allowed: set[str] | None = None
    if active_skill and active_skill.allowed_tool_names:
        skill_allowed = set(active_skill.allowed_tool_names)

    tools = [
        {
            "name": t.name,
            "type": t.type,
            "description": t.description,
            "parameters": t.parameters or [],
        }
        for t in bot.tools
        if t.is_enabled and (skill_allowed is None or t.name in skill_allowed)
    ]
    # MCP 서버에서 발견된 도구도 함께 노출 (동일 이름이면 DB 도구 우선)
    existing_names = {t["name"] for t in tools}
    mcp_servers = (
        db.query(models.MCPServer)
        .filter(models.MCPServer.bot_id == bot_id, models.MCPServer.is_enabled.is_(True))
        .all()
    )
    for srv in mcp_servers:
        for mt in srv.discovered_tools or []:
            name = mt.get("name")
            if not name or name in existing_names:
                continue
            if skill_allowed is not None and name not in skill_allowed:
                continue
            tools.append({
                "name": name,
                "type": f"mcp:{srv.id}",
                "description": mt.get("description", ""),
                "parameters": mt.get("parameters", []),
            })
            existing_names.add(name)

    # Mention 대상 모음 — `@스킬/지식/도구` 토큰 치환에 사용
    targets: list[MentionTarget] = []
    for s in bot.skills:
        targets.append(MentionTarget(kind="skill", name=s.name, body=s.content or ""))
    for k in bot.knowledge:
        targets.append(MentionTarget(kind="knowledge", name=k.title, body=k.content or ""))
    for t in bot.tools:
        if t.is_enabled:
            targets.append(MentionTarget(kind="tool", name=t.name, body=t.description or ""))

    active_content = active_skill.content if active_skill else None
    if active_content:
        active_content = expand_mentions(active_content, targets)
    expanded_knowledge = [(title, expand_mentions(content, targets)) for title, content in knowledge_pairs]

    branches = bot.branches or []
    # 분기 표시용: 같은 테넌트의 봇 id→name lookup
    bot_lookup = {b.id: b.name for b in db.query(models.Bot).filter(models.Bot.tenant_id == bot.tenant_id).all()}
    # CallbotAgent 통화 일관 설정 우선 (없으면 bot 자체 값 fallback)
    voice, greeting, language, llm_model, _pron, _dtmf = _resolve_callbot_settings(db, bot)
    system_prompt = build_system_prompt(
        persona=bot.persona or "",
        bot_system_prompt=bot.system_prompt or "",
        active_skill_name=active_skill.name if active_skill else None,
        active_skill_content=active_content,
        other_skills=others,
        knowledge=expanded_knowledge,
        greeting=greeting,
        tools=tools,
        auto_context=auto_context,
        voice_rules=bot.voice_rules or None,
        branches=branches,
        bot_lookup=bot_lookup,
        variables=variables,
    )

    runtime = BotRuntime(
        bot_id=bot.id,
        name=bot.name,
        language=language,
        voice=voice,
        llm_model=llm_model,
        greeting=greeting,
        system_prompt=system_prompt,
    )
    return runtime, (active_skill.name if active_skill else None)


def _find_balanced_json(text: str) -> list[tuple[int, int]]:
    """텍스트에서 brace-balanced JSON 객체의 (start, end) 위치를 모두 찾는다.
    `{"tool":"end_call","args":{}}` 같은 중첩 객체도 정확히 매치.
    """
    results: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 1
        j = i + 1
        in_str = False
        esc = False
        while j < n and depth > 0:
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
            j += 1
        if depth == 0:
            results.append((i, j))
            i = j
        else:
            break  # 닫히지 않은 객체 → 중단
    return results


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|(?<=까요\?)\s*|(?<=세요\.)\s*|(?<=세요\?)\s*")


def _dedupe_consecutive_sentences(body: str) -> str:
    """같은 문장이 연달아 나오면 한 번만 남긴다.
    LLM이 마무리 질문("더 알려드릴까요?")을 두 번 붙이는 케이스 방어.
    """
    if not body:
        return body
    parts = [p.strip() for p in _SENT_SPLIT_RE.split(body) if p and p.strip()]
    if len(parts) < 2:
        return body
    out: list[str] = []
    for p in parts:
        if out and out[-1] == p:
            continue
        out.append(p)
    return " ".join(out)


def parse_signal_and_strip(text: str) -> tuple[str, LLMSignal]:
    """LLM 응답에서 신호 JSON 다중 처리 (tool + extracted + next_skill 동시 가능)."""
    if not text:
        return text, LLMSignal()

    matches = _find_balanced_json(text)
    sig_dicts: list[tuple[int, int, dict]] = []
    for start, end in matches:
        snippet = text[start:end]
        try:
            data = json.loads(snippet)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if any(k in data for k in ("next_skill", "tool", "extracted")):
            sig_dicts.append((start, end, data))

    # body에서 모든 시그널 JSON 영역 제거 (역순으로 인덱스 안 깨지게)
    body = text
    for start, end, _ in reversed(sig_dicts):
        body = body[:start] + body[end:]
    body = body.strip()

    # 시그널 합성 — tool/next_skill은 첫 매칭, extracted는 머지
    signal = LLMSignal()
    extracted_merged: dict = {}
    for _, _, data in sig_dicts:
        if signal.next_skill is None and data.get("next_skill"):
            signal.next_skill = data["next_skill"]
        if signal.tool is None and data.get("tool"):
            signal.tool = data["tool"]
            if isinstance(data.get("args"), dict):
                signal.args = data["args"]
        if isinstance(data.get("extracted"), dict):
            extracted_merged.update(data["extracted"])
    if extracted_merged:
        signal.extracted = extracted_merged

    body = _dedupe_consecutive_sentences(body)
    return body, signal
