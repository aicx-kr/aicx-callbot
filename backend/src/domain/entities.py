"""도메인 엔티티 (순수). ORM은 infrastructure/models.py."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BotRuntime:
    """LLM 호출 직전에 합성된 런타임 구성."""

    bot_id: int
    name: str
    language: str
    voice: str
    llm_model: str
    greeting: str
    system_prompt: str
