"""시드 데이터 — 마이리얼트립 데모 봇."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models


async def seed_if_empty(db: AsyncSession) -> None:
    count = (await db.execute(select(func.count()).select_from(models.Tenant))).scalar_one()
    if count > 0:
        return

    tenant = models.Tenant(name="마이리얼트립", slug="myrealtrip")
    db.add(tenant)
    await db.flush()

    bot = models.Bot(
        tenant_id=tenant.id,
        name="여행 상담 콜봇",
        persona=(
            "당신은 마이리얼트립의 친절한 여행 상담사입니다. "
            "차분하고 또박또박한 한국어로 안내합니다. 사용자가 편안하게 느낄 수 있도록 공감 표현을 자연스럽게 사용합니다."
        ),
        system_prompt=(
            "여행 일정, 항공·숙소·투어 예약 변경, 환불, FAQ를 도와주는 보이스 어시스턴트입니다. "
            "예약번호나 결제 정보 같은 민감 정보는 받지 않고, 필요한 경우 보안 채널 안내로 유도합니다."
        ),
        greeting="안녕하세요, 마이리얼트립 여행 상담 콜봇입니다. 무엇을 도와드릴까요?",
        language="ko-KR",
        voice="ko-KR-Neural2-A",
        llm_model="gemini-3.1-flash-lite",
    )
    db.add(bot)
    await db.flush()

    db.add_all(
        [
            models.Skill(
                bot_id=bot.id,
                name="Frontdoor",
                description="진입 — 사용자의 의도를 파악하고 적절한 스킬로 안내",
                content=(
                    "## 흐름\n"
                    "1. 따뜻하게 인사하고 무엇을 도와드릴지 묻기\n"
                    "2. 사용자 발화에서 의도(예약 변경/환불/FAQ/기타)를 파악\n"
                    "3. 해당 스킬로 자연스럽게 전환\n\n"
                    "## 하드룰\n"
                    "- 절대 길게 말하지 않는다 (한 문장)\n"
                    "- 모호하면 한 번 더 구체적으로 묻는다"
                ),
                is_frontdoor=True,
                order=0,
            ),
            models.Skill(
                bot_id=bot.id,
                name="예약 변경",
                description="기존 예약의 일정/인원 변경 처리",
                content=(
                    "## 흐름\n"
                    "1. 예약 번호를 묻고 복창\n"
                    "2. 어떤 항목을 변경하는지 확인\n"
                    "3. 변경 가능 여부 안내(규정 기반)\n"
                    "4. 가능하면 처리 단계 안내, 어려우면 상담사 전환\n\n"
                    "## 하드룰\n"
                    "- 결제·카드 정보는 받지 않는다\n"
                    "- 정확한 일자는 반드시 복창"
                ),
                order=1,
            ),
            models.Skill(
                bot_id=bot.id,
                name="환불 안내",
                description="환불 정책 안내 및 신청 도움",
                content=(
                    "## 흐름\n"
                    "1. 예약 정보를 묻고 확인\n"
                    "2. 환불 정책 안내 (지식베이스 참고)\n"
                    "3. 가능 시 신청 안내, 불가 시 사유 설명 후 상담사 전환"
                ),
                order=2,
            ),
            models.Skill(
                bot_id=bot.id,
                name="FAQ",
                description="자주 묻는 질문 응대",
                content=(
                    "## 흐름\n"
                    "- 지식베이스를 우선 참고\n"
                    "- 정확히 모르는 사항은 추측하지 않고 상담사 전환 안내"
                ),
                order=3,
            ),
        ]
    )

    db.add_all(
        [
            models.Knowledge(
                bot_id=bot.id,
                title="환불 정책 요약",
                content=(
                    "패키지 상품: 출발 7일 전 전액 환불, 3일 전 50% 환불, 1일 전 환불 불가. "
                    "항공권은 항공사 규정에 따름. 호텔은 상품별 정책 상이."
                ),
            ),
            models.Knowledge(
                bot_id=bot.id,
                title="고객센터 운영시간",
                content=(
                    "평일 9시부터 18시까지 운영. 주말 휴무. 긴급 문의는 카카오톡 채널을 이용."
                ),
            ),
        ]
    )

    # Tools
    db.add_all(
        [
            models.Tool(
                bot_id=bot.id,
                name="end_call",
                type="builtin",
                description="통화를 종료할 때 호출. 사용자 작별 인사 후 사용.",
                parameters=[],
                settings={},
            ),
            models.Tool(
                bot_id=bot.id,
                name="transfer_to_specialist",
                type="builtin",
                description="복잡한 사례·민감 정보·환불 거부 등에서 사람 상담사로 전환.",
                parameters=[{"name": "reason", "type": "string", "description": "전환 사유 요약", "required": True}],
                settings={},
            ),
            # callbot_v0 패턴 — 통화 시작 시 발신번호로 예약 정보 사전 조회.
            # auto_call_on=session_start 이므로 _run_auto_calls에서 자동 실행됨.
            # script 본문은 운영자가 어드민 콘솔에서 실제 endpoint URL과 인증 정보로 채워야 함.
            # 결과 dict는 dynamic_vars(var_ctx.dynamic)에 머지되어 시스템 프롬프트에 노출됨.
            models.Tool(
                bot_id=bot.id,
                name="reservations_phone",
                type="api",
                description=(
                    "발신번호로 사용자 예약 내역을 조회 (자동 호출). "
                    "결과: userId, reservationNo, air_reservations, nonair_reservations 등."
                ),
                parameters=[
                    {"name": "phone_number", "type": "string", "description": "발신 전화번호 (E.164 또는 010-...)", "required": True},
                ],
                code=(
                    "# TODO: 운영 환경의 실제 예약 조회 endpoint로 교체.\n"
                    "# secrets: tool_secrets 또는 Bot.env_vars의 RESERVATION_API_BASE / RESERVATION_API_TOKEN.\n"
                    "import requests, json\n"
                    "url = '{{RESERVATION_API_BASE}}/lookup'\n"
                    "headers = {'Authorization': 'Bearer {{RESERVATION_API_TOKEN}}'}\n"
                    "try:\n"
                    "    r = requests.get(url, params={'phone': phone_number}, headers=headers, timeout=4)\n"
                    "    if r.status_code != 200:\n"
                    "        result = {}\n"
                    "    else:\n"
                    "        data = r.json() or {}\n"
                    "        # dynamic_vars에 머지될 key 형태로 반환 (값은 모두 str)\n"
                    "        result = {\n"
                    "            'userId': str(data.get('userId') or ''),\n"
                    "            'reservationNo': str(data.get('reservationNo') or ''),\n"
                    "            'air_reservations': data.get('air_reservations_summary', ''),\n"
                    "            'nonair_reservations': data.get('nonair_reservations_summary', ''),\n"
                    "        }\n"
                    "        result = {k: v for k, v in result.items() if v}\n"
                    "except Exception as e:\n"
                    "    result = {}\n"
                ),
                settings={
                    "timeout_sec": 5,
                    # _run_auto_calls가 이 args를 var_ctx로 치환해 도구에 넘김.
                    "default_args": {"phone_number": "{{callerPhone}}"},
                    # 결과 dict를 var_ctx.dynamic에 머지 (callbot_v0 패턴).
                    "merge_result_into_vars": True,
                },
                is_enabled=False,  # 기본은 비활성 — 운영자가 endpoint·secret 설정 후 켤 것
                auto_call_on="session_start",
            ),
            # 마이리얼트립 도메인 API 도구들 (aicx-plugins-mcp manifest 기반)
            models.Tool(
                bot_id=bot.id,
                name="lookup_user_by_identifier",
                type="rest",
                description="전화번호·이메일 등 식별자로 회원 정보를 조회한다. 본인 확인용.",
                parameters=[
                    {"name": "identifier", "type": "string", "description": "전화번호 또는 이메일", "required": True},
                ],
                settings={
                    "method": "GET",
                    "url_template": "{{MRT_CS_API_BASE}}/v1/users/lookup?identifier={identifier}",
                    "headers": {"X-API-Token": "{{API_TOKEN}}"},
                    "timeout_sec": 5,
                },
            ),
            models.Tool(
                bot_id=bot.id,
                name="lookup_user_by_user_id",
                type="rest",
                description="user_id로 회원 상세 정보를 조회한다. 인증 후 사용.",
                parameters=[
                    {"name": "user_id", "type": "string", "description": "회원 ID(숫자)", "required": True},
                ],
                settings={
                    "method": "GET",
                    "url_template": "{{MRT_CS_API_BASE}}/v1/users/{user_id}",
                    "headers": {"X-API-Token": "{{API_TOKEN}}"},
                    "timeout_sec": 5,
                },
            ),
            models.Tool(
                bot_id=bot.id,
                name="get_reservation",
                type="rest",
                description="예약 번호로 예약 정보(상품/일정/결제)를 조회한다.",
                parameters=[
                    {"name": "reservation_no", "type": "string", "description": "예약 번호", "required": True},
                    {"name": "user_id", "type": "string", "description": "회원 ID", "required": True},
                ],
                settings={
                    "method": "GET",
                    "url_template": "{{MRT_CS_API_BASE}}/v1/reservations/{reservation_no}?userId={user_id}",
                    "headers": {"X-API-Token": "{{API_TOKEN}}"},
                    "timeout_sec": 5,
                },
            ),
            models.Tool(
                bot_id=bot.id,
                name="get_flight_by_pnr",
                type="rest",
                description="PNR(예약기록번호)로 항공권 정보를 조회한다.",
                parameters=[
                    {"name": "pnr", "type": "string", "description": "PNR (6자리 영문/숫자)", "required": True},
                ],
                settings={
                    "method": "GET",
                    "url_template": "{{MRT_CS_API_BASE}}/v1/flights/by-pnr?pnr={pnr}",
                    "headers": {"X-API-Token": "{{API_TOKEN}}"},
                    "timeout_sec": 5,
                },
            ),
            models.Tool(
                bot_id=bot.id,
                name="get_refund_fee",
                type="rest",
                description="항공권 환불 수수료(취소 수수료)를 조회한다. 출발일 기준 구간별 수수료.",
                parameters=[
                    {"name": "user_id", "type": "string", "description": "회원 ID", "required": True},
                    {"name": "reservation_no", "type": "string", "description": "예약 번호", "required": True},
                ],
                settings={
                    "method": "GET",
                    "url_template": "{{MRT_CS_API_BASE}}/v1/voxai/flights/refund-fee?userId={user_id}&reservationNo={reservation_no}&includePeriod=false",
                    "headers": {"X-API-Token": "{{API_TOKEN}}"},
                    "timeout_sec": 8,
                },
            ),
            models.Tool(
                bot_id=bot.id,
                name="get_accommodation",
                type="rest",
                description="숙소 예약 상세(체크인/체크아웃/취소 정책)를 조회한다.",
                parameters=[
                    {"name": "reservation_no", "type": "string", "description": "예약 번호", "required": True},
                ],
                settings={
                    "method": "GET",
                    "url_template": "{{MRT_CS_API_BASE}}/v1/accommodations/{reservation_no}",
                    "headers": {"X-API-Token": "{{API_TOKEN}}"},
                    "timeout_sec": 5,
                },
            ),
            models.Tool(
                bot_id=bot.id,
                name="get_tna_product",
                type="rest",
                description="투어/액티비티(TnA) 상품 정보(가격·운영시간·취소규정)를 조회한다.",
                parameters=[
                    {"name": "product_id", "type": "string", "description": "상품 ID", "required": True},
                ],
                settings={
                    "method": "GET",
                    "url_template": "{{MRT_CS_API_BASE}}/v1/tna/products/{product_id}",
                    "headers": {"X-API-Token": "{{API_TOKEN}}"},
                    "timeout_sec": 5,
                },
            ),
            models.Tool(
                bot_id=bot.id,
                name="create_zendesk_ticket",
                type="rest",
                description="상담사 핸드오프 시 Zendesk 티켓을 자동 생성한다. 통화 요약을 본문에 포함.",
                parameters=[
                    {"name": "subject", "type": "string", "description": "티켓 제목 (예: '환불 문의 - 예약 ABC123')", "required": True},
                    {"name": "body", "type": "string", "description": "통화 요약 본문", "required": True},
                    {"name": "requester_email", "type": "string", "description": "요청자 이메일", "required": False},
                    {"name": "priority", "type": "string", "description": "우선순위 (low/normal/high/urgent)", "required": False},
                ],
                settings={
                    "method": "POST",
                    "url_template": "{{ZENDESK_API_BASE}}/v2/tickets.json",
                    "headers": {
                        "Authorization": "Basic {{ZENDESK_AUTH}}",
                        "Content-Type": "application/json",
                    },
                    "body_template": '{"ticket":{"subject":"{subject}","comment":{"body":"{body}"},"priority":"{priority}","requester":{"email":"{requester_email}"}}}',
                    "timeout_sec": 8,
                },
            ),
        ]
    )

    await db.commit()
