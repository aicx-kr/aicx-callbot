"""통화 태깅 도메인 — Tag, CallTag, BotTagPolicy.

순수 도메인. ORM/Pydantic 의존 없음. 비즈니스 규칙(허용 목록 제한 정책 등) 강제.

AICC-912 결정사항:
- 정의 외 태그명 처리: **허용 목록 제한** (BotTagPolicy 에 등록된 태그만 자동 태깅 허용)
- 수동 태그 권한: 누구나 (1인 운영이라 의미 적음)
- tenant_id 는 "default" 상수 (멀티테넌트화 시점에 의무 필드 승격 — AICC-909 의 ContextVar 와 동일 정책)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# tenant_id 기본값 — AICC-909 와 동일 정책. 멀티테넌트화 시점에 의무 필드 승격.
DEFAULT_TENANT_ID = "default"


class TagSource(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class DomainError(Exception):
    """태그 도메인 불변식 위반."""


@dataclass
class Tag:
    """통화 태그.

    비즈니스 규칙:
    - name 비어 있을 수 없음
    - color 는 hex (#rrggbb) 또는 팔레트 키. 빈 문자열이면 운영자 미지정 → UI 기본색 적용.
    - (tenant_id, name) UNIQUE — DB 제약으로 강제 (infrastructure 레이어)
    """

    id: int | None
    tenant_id: str
    name: str
    color: str = ""
    is_active: bool = True

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise DomainError("Tag.name 은 비어 있을 수 없습니다")
        if not self.tenant_id:
            raise DomainError("Tag.tenant_id 는 비어 있을 수 없습니다")


@dataclass(frozen=True)
class CallTag:
    """통화↔태그 연결. composite identity = (call_session_id, tag_id).

    source:
      - AUTO   → post-call 분석에서 BotTagPolicy 매칭으로 자동 생성
      - MANUAL → 운영자가 UI 에서 추가
    """

    call_session_id: int
    tag_id: int
    source: TagSource = TagSource.MANUAL
    created_at: datetime | None = None
    created_by: str | None = None  # manual 시 사용자 ID (선택). 1인 운영이라 미사용 가능.


@dataclass
class BotTagPolicy:
    """봇별 자동 태그 허용 목록.

    AICC-912 §3.4 — 허용 목록 제한 정책:
      LLM 이 BotTagPolicy.allowed_tag_ids 외 태그를 제안해도 무시 + warning 로그.
      운영자가 콘솔에서 명시적으로 태그 풀을 정의해야 함 (1인 운영의 태그 폭증 방지).
    """

    bot_id: int
    allowed_tag_ids: list[int] = field(default_factory=list)

    def is_allowed(self, tag_id: int) -> bool:
        return tag_id in self.allowed_tag_ids

    def filter_allowed(self, candidate_tag_ids: list[int]) -> list[int]:
        """후보 중 허용된 것만 반환. 정책 외 태그는 제거됨."""
        allowed = set(self.allowed_tag_ids)
        return [tid for tid in candidate_tag_ids if tid in allowed]
