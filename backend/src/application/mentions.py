"""Mention 확장 — `@이름` 토큰을 등록된 스킬/지식/도구 content로 치환.

vox 패턴 (echo UI의 `@` 자동완성)을 백엔드 합성으로 구현.
프롬프트 빌더가 active_skill_content / knowledge content에 적용한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MentionTarget:
    kind: Literal["skill", "knowledge", "tool"]
    name: str
    body: str  # 치환 본문 (스킬/지식의 content 또는 도구 디스크립션)


def expand_mentions(text: str, targets: list[MentionTarget]) -> str:
    """`@이름` 토큰을 본문으로 치환. 한국어 + 공백 포함 이름도 처리.

    등록된 이름을 길이 내림차순으로 정렬 후 가장 긴 매치 우선 치환 →
    "예약 변경"이 "변경"보다 먼저 매치된다.
    재귀적으로 mention된 본문 안의 mention도 1단계까지 펼친다 (무한루프 방지).
    """
    if not text or not targets:
        return text

    by_name = {t.name: t for t in targets}
    return _expand(text, by_name, depth=0, max_depth=2)


def _expand(text: str, by_name: dict[str, MentionTarget], depth: int, max_depth: int) -> str:
    if depth >= max_depth or "@" not in text:
        return text

    # 길이 내림차순으로 검색 (긴 이름 먼저)
    names = sorted(by_name.keys(), key=len, reverse=True)
    result = text
    for name in names:
        token = "@" + name
        if token not in result:
            continue
        t = by_name[name]
        rendered = _render_block(t, depth)
        # mention된 본문도 재귀적으로 확장
        if t.kind != "tool":
            rendered = _expand(rendered, by_name, depth + 1, max_depth)
        result = result.replace(token, rendered)
    return result


def _render_block(t: MentionTarget, depth: int) -> str:
    """치환 블록 — LLM이 참조 영역임을 알도록 명시 마커."""
    prefix = "    " * depth
    if t.kind == "tool":
        return f"`{t.name}` (도구: {t.body})"
    label = {"skill": "스킬", "knowledge": "지식"}[t.kind]
    return (
        f"\n{prefix}┌── 참조 {label}: {t.name} ──\n"
        f"{_indent(t.body, prefix)}\n"
        f"{prefix}└── /참조 {t.name} ──\n"
    )


def _indent(body: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in body.splitlines())
