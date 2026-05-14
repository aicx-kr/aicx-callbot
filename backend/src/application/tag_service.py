"""통화 태깅 서비스 — AICC-912.

태그 카탈로그 CRUD + 통화별 태그 추가/제거 + 봇 자동태깅 정책 관리 + 자동 태깅 hook.

비즈니스 규칙은 도메인 (`Tag.validate`, `BotTagPolicy.filter_allowed`) 에 위임,
서비스는 흐름 조립 + 로깅 만 담당.
"""

from __future__ import annotations

import logging

from ..domain.repositories import (
    BotTagPolicyRepository,
    CallTagRepository,
    TagRepository,
)
from ..domain.tag import (
    DEFAULT_TENANT_ID,
    BotTagPolicy,
    CallTag,
    DomainError,
    Tag,
    TagSource,
)

logger = logging.getLogger(__name__)


class TagService:
    """태그 카탈로그 + 통화 태깅 + 봇 자동태깅 정책.

    repository 3개를 DI 로 받아 도메인 객체에 위임. SQL 직접 발행 금지.
    """

    def __init__(
        self,
        tag_repo: TagRepository,
        call_tag_repo: CallTagRepository,
        policy_repo: BotTagPolicyRepository,
    ) -> None:
        self._tags = tag_repo
        self._call_tags = call_tag_repo
        self._policies = policy_repo

    # ---------- 태그 카탈로그 ----------

    async def list_tags(
        self, tenant_id: str = DEFAULT_TENANT_ID, *, include_inactive: bool = False
    ) -> list[Tag]:
        return await self._tags.list(tenant_id, include_inactive=include_inactive)

    async def get_tag(self, tag_id: int) -> Tag | None:
        return await self._tags.get(tag_id)

    async def create_tag(
        self, *, name: str, color: str = "", tenant_id: str = DEFAULT_TENANT_ID
    ) -> Tag:
        # 같은 이름이 이미 active 또는 inactive 로 있으면 재사용 (idempotent)
        existing = await self._tags.find_by_name(tenant_id, name)
        if existing is not None:
            if not existing.is_active:
                # 비활성 태그를 재활성화 + color 갱신
                existing.is_active = True
                if color:
                    existing.color = color
                return await self._tags.save(existing)
            return existing
        tag = Tag(id=None, tenant_id=tenant_id, name=name, color=color, is_active=True)
        return await self._tags.save(tag)

    async def update_tag(
        self,
        tag_id: int,
        *,
        name: str | None = None,
        color: str | None = None,
        is_active: bool | None = None,
    ) -> Tag:
        tag = await self._tags.get(tag_id)
        if tag is None:
            raise DomainError(f"Tag {tag_id} 없음")
        if name is not None:
            tag.name = name
        if color is not None:
            tag.color = color
        if is_active is not None:
            tag.is_active = is_active
        return await self._tags.save(tag)

    async def delete_tag(self, tag_id: int) -> None:
        """soft delete."""
        await self._tags.delete(tag_id)

    # ---------- 통화 ↔ 태그 ----------

    async def list_call_tags(self, call_session_id: int) -> list[CallTag]:
        return await self._call_tags.list_by_call(call_session_id)

    async def add_call_tag(
        self,
        call_session_id: int,
        tag_id: int,
        *,
        source: str = "manual",
        user_id: str | None = None,
    ) -> CallTag:
        tag = await self._tags.get(tag_id)
        if tag is None:
            raise DomainError(f"Tag {tag_id} 없음")
        ct = CallTag(
            call_session_id=call_session_id,
            tag_id=tag_id,
            source=TagSource(source),
            created_by=user_id,
        )
        saved = await self._call_tags.add(ct)
        logger.info(
            "tag.assign call_session_id=%s tag_id=%s tag_name=%s source=%s",
            call_session_id, tag_id, tag.name, source,
        )
        return saved

    async def remove_call_tag(self, call_session_id: int, tag_id: int) -> None:
        await self._call_tags.remove(call_session_id, tag_id)
        logger.info(
            "tag.unassign call_session_id=%s tag_id=%s", call_session_id, tag_id
        )

    async def list_calls_by_tags(
        self, bot_id: int, tag_ids: list[int], *, mode: str = "and"
    ) -> list[int]:
        """봇 내 통화 중 주어진 태그 셋과 매칭되는 call_session_id 목록 (필터 검색용)."""
        return await self._call_tags.list_call_ids_by_tags(bot_id, tag_ids, mode=mode)

    # ---------- BotTagPolicy ----------

    async def get_bot_tag_policy(self, bot_id: int) -> BotTagPolicy:
        return await self._policies.get(bot_id)

    async def set_bot_tag_policy(self, bot_id: int, allowed_tag_ids: list[int]) -> BotTagPolicy:
        policy = BotTagPolicy(bot_id=bot_id, allowed_tag_ids=list(allowed_tag_ids))
        return await self._policies.save(policy)

    # ---------- 자동 태깅 (post_call hook) ----------

    async def auto_tag_call(
        self,
        call_session_id: int,
        bot_id: int,
        llm_proposed_tag_names: list[str],
        *,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> list[CallTag]:
        """post-call 분석에서 호출. LLM 제안 태그명을 정책으로 필터하고 CallTag(auto) 저장.

        흐름:
        1. 빈 입력 → no-op
        2. BotTagPolicy.allowed_tag_ids 조회
        3. LLM 제안 태그명 → Tag 매칭 (tenant_id 내, is_active)
        4. 매칭된 Tag.id 중 정책에 포함된 것만 통과 — 정책 외는 logger.warning "tag.reject"
        5. 통과한 태그를 CallTag(source="auto") 로 저장 (idempotent)
        """
        if not llm_proposed_tag_names:
            return []

        policy = await self._policies.get(bot_id)
        if not policy.allowed_tag_ids:
            # 정책 미설정 — 모든 제안 거부 (로그만)
            for name in llm_proposed_tag_names:
                logger.warning(
                    "tag.reject call_session_id=%s tag_name=%s reason=no_policy bot_id=%s",
                    call_session_id, name, bot_id,
                )
            return []

        # 정규화 (공백/대소문자) 한 번 한 후 매칭 — 운영자 친화
        normalized = [n.strip() for n in llm_proposed_tag_names if n and n.strip()]
        matched = await self._tags.find_by_names(tenant_id, normalized)
        matched_by_name = {t.name: t for t in matched if t.is_active}

        # 정책 외 / 미존재 거부 로깅
        allowed = set(policy.allowed_tag_ids)
        accepted: list[CallTag] = []
        for name in normalized:
            t = matched_by_name.get(name)
            if t is None or t.id is None:
                logger.warning(
                    "tag.reject call_session_id=%s tag_name=%s reason=tag_not_found",
                    call_session_id, name,
                )
                continue
            if t.id not in allowed:
                logger.warning(
                    "tag.reject call_session_id=%s tag_id=%s tag_name=%s reason=not_in_policy bot_id=%s",
                    call_session_id, t.id, name, bot_id,
                )
                continue
            ct = CallTag(
                call_session_id=call_session_id,
                tag_id=t.id,
                source=TagSource.AUTO,
            )
            saved = await self._call_tags.add(ct)
            logger.info(
                "tag.assign call_session_id=%s tag_id=%s tag_name=%s source=auto",
                call_session_id, t.id, name,
            )
            accepted.append(saved)
        return accepted
