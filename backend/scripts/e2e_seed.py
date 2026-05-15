"""E2E 테스트 격리 데이터 시드.

목적:
  Playwright 가 검증할 격리된 테스트 데이터를 생성. 마이리얼트립 등 기존 데이터는
  절대 건드리지 않고 slug="callbot-e2e-test" tenant 하나에만 격리.

생성물 (cascade 로 한 번에 정리됨):
  tenant      "callbot-e2e-test"
   ├── bot   "e2e-main"    (silent_transfer 메인)
   │   ├── skill "e2e-skill-refund"  ← 스킬 활용 검증용
   │   └── knowledge "테스트 보험 약관" ← RAG 검증용
   ├── bot   "e2e-sub"     (silent_transfer 인계 대상)
   └── callbot_agent "e2e-callbot"
        ├── membership(main, e2e-main, branch_trigger="")
        └── membership(sub,  e2e-sub,  branch_trigger="환불")

실행:
  cd backend && uv run python scripts/e2e_seed.py             # cleanup + seed
  cd backend && uv run python scripts/e2e_seed.py --cleanup   # 삭제만

출력 (stdout, JSON 1줄): 생성된 ID 들. Playwright spec 이 파싱.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# backend/src 를 path 에 추가 — 스크립트 형태로 실행 시 임포트 해결
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.infrastructure import models  # noqa: E402
from src.infrastructure.db import SessionLocal  # noqa: E402


E2E_TENANT_SLUG = "callbot-e2e-test"
E2E_TENANT_NAME = "E2E Test (Auto-Generated)"


async def cleanup() -> int | None:
    """기존 e2e tenant 가 있으면 삭제. cascade 로 bots/callbot_agents 함께 정리."""
    async with SessionLocal() as db:
        stmt = select(models.Tenant).where(models.Tenant.slug == E2E_TENANT_SLUG)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is None:
            return None
        prev_id = existing.id
        await db.delete(existing)
        await db.commit()
        return prev_id


async def seed() -> dict:
    """격리 데이터 생성. cleanup 직후에만 호출."""
    async with SessionLocal() as db:
        tenant = models.Tenant(name=E2E_TENANT_NAME, slug=E2E_TENANT_SLUG)
        db.add(tenant)
        await db.flush()

        main_bot = models.Bot(
            tenant_id=tenant.id,
            name="e2e-main",
            persona="E2E 테스트용 메인 봇",
            # system_prompt 는 sub bot id 확보 후 아래에서 업데이트.
            system_prompt="(placeholder)",
            greeting="안녕하세요, E2E 테스트입니다.",
            language="ko-KR",
            voice="ko-KR-Neural2-A",
            llm_model="gemini-2.5-flash",
            agent_type="prompt",
        )
        sub_bot = models.Bot(
            tenant_id=tenant.id,
            name="e2e-sub",
            persona="E2E 테스트용 sub (환불) 봇",
            system_prompt="당신은 환불 전담 봇입니다.",
            greeting="환불 안내를 도와드리겠습니다.",
            language="ko-KR",
            voice="ko-KR-Neural2-B",
            llm_model="gemini-2.5-flash",
            agent_type="prompt",
        )
        db.add_all([main_bot, sub_bot])
        await db.flush()

        # sub_bot.id 확보 후 main_bot system_prompt 업데이트 — LLM 이 환불 의도 시
        # transfer_to_agent 도구를 정확한 target_bot_id 로 호출하도록 안내.
        main_bot.system_prompt = (
            "당신은 친절한 안내 봇입니다 ({{bot_id}}).\n"
            f"환불 관련 문의가 들어오면 즉시 transfer_to_agent 도구를 호출해서 "
            f"target_bot_id={sub_bot.id} 에 인계하세요. 다른 답변은 하지 마세요."
        )

        skill = models.Skill(
            bot_id=main_bot.id,
            name="e2e-skill-refund",
            description="환불 트리거 검증용 스킬",
            kind="prompt",
            content="환불 정책을 안내한다. 사용자 의도가 환불일 때 활성화.",
            is_frontdoor=False,
            order=0,
        )
        knowledge = models.Knowledge(
            bot_id=main_bot.id,
            title="테스트 보험 약관",
            content=(
                "여행자 보험 가입 시 24시간 이내 청구 가능. 청구 시 영수증 사본 필수. "
                "지급 처리 5영업일 소요. (E2E 테스트 픽스처 — 실 약관 아님)"
            ),
        )
        db.add_all([skill, knowledge])

        callbot = models.CallbotAgent(
            tenant_id=tenant.id,
            name="e2e-callbot",
            voice="ko-KR-Neural2-A",
            # barge_in 시나리오용 — 인사말이 길어야 sim 이 PCM 송신 시 봇이 아직 발화 중.
            greeting=(
                "안녕하세요. E2E 자동 테스트 콜봇입니다. "
                "지금부터 자동화 검증을 시작합니다. 무엇을 도와드릴까요?"
            ),
            language="ko-KR",
            llm_model="gemini-2.5-flash",
            greeting_barge_in=True,  # e2e: barge_in 시나리오 검증을 위해 활성
            # e2e: idle_timeout 시나리오 사이클 시간 단축. 다른 시나리오는 5초 안에 응답 도착하므로 영향 X.
            idle_prompt_ms=2000,
            idle_terminate_ms=5000,
            idle_prompt_text="여보세요?",
            # e2e: DTMF 시나리오 검증용 매핑.
            dtmf_map={
                "1": {"type": "say", "payload": "1번 안내입니다"},
                "0": {"type": "terminate", "payload": ""},
            },
        )
        db.add(callbot)
        await db.flush()

        main_mem = models.CallbotMembership(
            callbot_id=callbot.id,
            bot_id=main_bot.id,
            role="main",
            order=0,
            branch_trigger="",
            silent_transfer=False,
        )
        sub_mem = models.CallbotMembership(
            callbot_id=callbot.id,
            bot_id=sub_bot.id,
            role="sub",
            order=1,
            branch_trigger="환불",
            silent_transfer=False,
        )
        db.add_all([main_mem, sub_mem])

        await db.commit()

        return {
            "tenant_id": tenant.id,
            "tenant_slug": E2E_TENANT_SLUG,
            "main_bot_id": main_bot.id,
            "sub_bot_id": sub_bot.id,
            "skill_id": skill.id,
            "knowledge_id": knowledge.id,
            "callbot_id": callbot.id,
            "main_membership_id": main_mem.id,
            "sub_membership_id": sub_mem.id,
        }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true", help="삭제만 (seed 안 함)")
    args = parser.parse_args()

    deleted = await cleanup()
    if args.cleanup:
        print(json.dumps({"deleted_tenant_id": deleted}))
        return

    ids = await seed()
    print(json.dumps(ids))


if __name__ == "__main__":
    asyncio.run(main())
