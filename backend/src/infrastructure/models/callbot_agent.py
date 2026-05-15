"""CallbotAgent ORM 모델."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._helpers import _utcnow

if TYPE_CHECKING:
    from .callbot_membership import CallbotMembership
    from .tenant import Tenant


class CallbotAgent(Base):
    """통화 단위 컨테이너 — 한 콜봇 에이전트가 메인 1 + 서브 N개의 Bot으로 구성.
    통화 일관 설정(voice/greeting/language/llm_model/발음사전/DTMF)을 여기에 둠.
    """

    __tablename__ = "callbot_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 통화 동안 일관 — sub.voice_override 있으면 그것 우선
    voice: Mapped[str] = mapped_column(String(64), default="ko-KR-Neural2-A")
    greeting: Mapped[str] = mapped_column(String(500), default="안녕하세요, 무엇을 도와드릴까요?")
    language: Mapped[str] = mapped_column(String(8), default="ko-KR")
    llm_model: Mapped[str] = mapped_column(String(64), default="gemini-3.1-flash-lite")
    # (d) AICC-910 — pronunciation_dict 는 레거시 호환 유지. 신규 쓰기는 tts_pronunciation 으로.
    pronunciation_dict: Mapped[dict] = mapped_column(JSON, default=dict)
    # (d) AICC-910 — TTS 텍스트 치환용 (예: "FTU" → "에프티유"). NOT NULL — 도메인 default {}.
    tts_pronunciation: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # (d) AICC-910 — STT phrase hint (도메인 키워드 인식률 보정). list[str] 기본, dict[str,float] (boost) 도 허용. NOT NULL — 도메인 default [].
    stt_keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # (c) AICC-910 — dtmf_map 신규 스키마. {"1": {"type": "transfer_to_agent", "payload": "42"}}
    dtmf_map: Mapped[dict] = mapped_column(JSON, default=dict)
    # (a) AICC-910 — 인사말 중 사용자 끼어들기 허용 여부
    greeting_barge_in: Mapped[bool] = mapped_column(Boolean, default=False)
    # (b) AICC-910 — 무응답 자동 종료 정책 (ms)
    idle_prompt_ms: Mapped[int] = mapped_column(Integer, default=7000)
    idle_terminate_ms: Mapped[int] = mapped_column(Integer, default=15000)
    idle_prompt_text: Mapped[str] = mapped_column(String(500), default="여보세요?")
    # (e) AICC-910 — TTS 발화 속도/피치
    tts_speaking_rate: Mapped[float] = mapped_column(Float, default=1.0)
    tts_pitch: Mapped[float] = mapped_column(Float, default=0.0)
    # (f2) AICC-910 — Gemini ThinkingConfig.thinking_budget. NULL = SDK 기본(=dynamic).
    # 0 = off, -1 = dynamic 명시, 양수 N = 토큰 한도.
    llm_thinking_budget: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    # 공통 규칙 (§4 첫 단계) — 매 turn LLM 호출 전 매칭 검사
    # [{pattern, action: 'handover'|'end_call'|'transfer_agent', reason, priority, target_bot_id?}]
    global_rules: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="callbot_agents")
    memberships: Mapped[list["CallbotMembership"]] = relationship(
        "CallbotMembership", back_populates="callbot",
        cascade="all, delete-orphan", order_by="CallbotMembership.order",
    )
