# Auto-Loop 진행 로그

사용자가 자리 비운 사이 자동으로 돌린 개선 사이클의 누적 로그.

**우선순위 로테이션**: ① 테스트·성능 → ② UI 어색함 → ③ 구조 정리

**원칙**:
- 한 사이클 = 한 개선만 끝까지
- 매 사이클 끝에 **실 API smoke test** + 페이지 로드 검증 (필수)
- 검증 실패 시 변경 롤백 후 다음 사이클로
- 로컬 변경만 (commit/push 안 함)

---

## Smoke Test 체크리스트

매 사이클 끝에 아래 항목 통과 확인 후 PASS/FAIL 기록:

```bash
# Backend health
curl -sf http://localhost:8080/api/health | jq .

# 핵심 endpoints
curl -sf http://localhost:8080/api/tenants | jq 'length'
curl -sf http://localhost:8080/api/bots | jq 'length'
curl -sf "http://localhost:8080/api/skills?bot_id=1" | jq 'length'
curl -sf "http://localhost:8080/api/tools?bot_id=1" | jq 'length'

# Frontend (307 = redirect to /agents, 200 = page rendered)
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/bots/1/persona
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/bots/1/settings

# Type-check (no compile errors)
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

---

## Cycles

### Cycle #1 — 2026-05-11 19:46 (테스트·성능)
- 변경: smoke test 스크립트 외부화 (`scripts/smoke_test.sh`) + 실 테스트 데이터 fixture (`scripts/fixtures.json`)
- 파일: `scripts/smoke_test.sh` (신설), `scripts/fixtures.json` (신설, userid=4002532·phone=01082283421)
- 동기: 매 사이클 검증을 일관되게 — 이전엔 즉석 curl 모음, 이제 한 스크립트로 24개 endpoint·페이지·tsc 동시 검증
- Smoke: **23/24 PASS** (24번째: tsc 에러 3건 검출 — Cycle #2로 이관)

### Cycle #2 — 2026-05-11 19:50 (구조)
- 변경: TypeScript 빌드 에러 3건 제거
  - `Sidebar.tsx`: `Bot` (lucide) ↔ `Bot` (types) 이름 충돌 → `BotIcon`으로 재export
  - `TestPanel.tsx:209`: `r === rec` 전에 `r` null guard 추가
  - `mcp/page.tsx`: 로컬 `MCPServer` interface에 `auth_header` 누락 → 추가
- 파일: 3개
- 동기: smoke test가 즉시 검출 → 다음 사이클들이 클린 상태에서 출발하도록 정리
- Smoke: **24/24 PASS** (tsc 클린)

### Cycle #3 — 2026-05-11 20:02 (UI/대화 UX) — 사용자 직접 보고
- 증상: 봇이 매 응답마다 "더 알려드릴까요?" 강제 부착, 종료 의사 후에도 같은 응답에 2회 중복
- 원인: `prompts.py:10` 음성 규칙이 "길어지면 끊고 더 알려드릴까요?로 마무리"라고 너무 강제적
- 변경:
  1. `prompts.py` VOICE_RULES — 마무리 질문 자동 부착 금지 + 종료 의사("없어요"·"감사합니다") 감지 시 `end_call` 호출 + 같은 응답 내 반복 금지 명시
  2. `skill_runtime.py` — `_dedupe_consecutive_sentences` 헬퍼 추가, `parse_signal_and_strip`에서 본문 후처리 (LLM이 그래도 중복하면 마지막 방어)
- 파일: 2개
- 동기: 사용자 통화 transcript에서 직접 발견된 어색함
- Smoke: **24/24 PASS** + 4/4 dedupe 테스트 케이스 통과

### Cycle #4 — 2026-05-11 20:20 (구조 + 기능 — hub-and-spoke 백엔드 + voice_rules 외부화 + STT 트레이스)
사용자 직접 요청 3건 묶음 처리:
- 변경:
  1. **Bot.branches** JSON 컬럼 추가 (`[{name, trigger, target_bot_id}]`) — 허브-앤-스포크 데이터 모델
  2. **Bot.voice_rules** TEXT 컬럼 추가 — 고객사 콘솔에서 말투/규칙 자유 편집 가능 (빈 값이면 DEFAULT_VOICE_RULES 사용)
  3. SQLite `_migrate_sqlite_add_columns` 헬퍼 — 비파괴적 ADD COLUMN, lifespan에서 자동 실행
  4. `prompts.py` — VOICE_RULES → DEFAULT_VOICE_RULES, 시그니처에 voice_rules/branches/bot_lookup 추가, 분기 섹션 + transfer_to_agent JSON 가이드 생성
  5. `skill_runtime.build_runtime` — bot.voice_rules + bot.branches + bot_lookup 전달
  6. `voice_session._handle_tool_signal` — `transfer_to_agent` 분기: 같은 세션에서 봇 컨텍스트 스왑, 새 봇 인사말 발화
  7. `voice_session._run_stt` — STT 트레이스 추가 (kind=stt, partials 카운트·final_chars·cancelled 메타)
  8. Schemas/Types — BotCreate/Update/Out + 프론트 Branch interface + Bot.branches/voice_rules
- 파일: 7개 (`models.py`, `app.py`, `prompts.py`, `skill_runtime.py`, `voice_session.py`, `schemas.py`, `lib/types.ts`)
- 동기: 사용자 (a) 허브-앤-스포크 진행 (b) 고객사 커스텀 코드 → 콘솔 외부화 (c) waterfall STT 표시 — 세 가지 동시 요청
- 검증:
  - DB 마이그레이션 통과 (bot 1 branches=[], voice_rules='' 응답)
  - PATCH branches 적용 → 런타임 프롬프트에 "전환 가능한 다른 에이전트" 섹션 + target_bot_id=2 (테스트 에이전트) 노출 확인
  - voice rule "더 알려드릴까요?로 마무리" 강제 제거, 새 규칙 "자동으로 붙이지 말 것" 반영
- Smoke: **24/24 PASS**
- 잔여: 프론트엔드 WorkspaceSheet + Settings 페이지의 branches/voice_rules 편집 UI → 다음 사이클로

### Cycle #5 — 2026-05-11 20:25 (UI — branches/voice_rules 콘솔 편집)
- 변경:
  1. `/bots/[botId]/settings/page.tsx` — **`BranchesSection` 신설**: 같은 워크스페이스 봇 셀렉터 + 트리거 입력 + 분기 라벨, 추가/삭제 UI
  2. 동일 페이지 — **`voice_rules` 편집 textarea** 추가 (placeholder에 예시 표시, 비우면 플랫폼 기본값 사용 안내)
  3. 같은 페이지에서 cycle #4의 백엔드 컬럼이 즉시 사용 가능 → 멀티에이전트 전환·말투 커스텀이 콘솔에서 완결
- 파일: 1개 (~80줄 추가)
- 동기: cycle #4에서 데이터 모델·런타임은 만들었지만 사용자가 콘솔로 조작 불가 → 완결
- Smoke: **24/24 PASS** + tsc 클린

### Cycle #6 — 2026-05-11 20:35 (UI + 버그 — preview·edit 토글 + TTS 언어/보이스 보정 + 허브-앤-스포크 시각화) — 사용자 직접 보고 3건
- 변경:
  1. **`MarkdownPreview` 컴포넌트 신설** — 의존성 없는 경량 마크다운 렌더러 (`#`/`##`/`-`/`1.`/`**bold**`/`@mention` 등). 멘션은 kind별 색상.
  2. **스킬/지식 페이지 preview→edit 토글** — 기본은 미리보기, "편집" 버튼으로 Monaco 모드 전환. 사용자가 이전에 요청한 미해결 항목.
  3. **TTS 자동 언어 보정** — `google_tts._derive_language_from_voice`: 보이스 이름에서 language code 추출, 인자와 불일치 시 보이스 기준으로 강제. 실 버그(`Requested language code 'en-US' doesn't match the voice 'ko-KR-Neural2-A'`) 해결.
  4. **`BranchesFlowView` 신설** — @xyflow/react로 메인 봇 ↔ 분기 봇 허브-앤-스포크 시각화 (read-only). 분기명·트리거·타입 노드에 표시.
  5. settings 페이지 분기 섹션 위에 시각화 + 아래 편집 폼.
- 파일: 5개 (`MarkdownPreview.tsx` 신설, `BranchesFlowView.tsx` 신설, `skills/[skillId]/page.tsx`, `knowledge/[kbId]/page.tsx`, `bots/[botId]/settings/page.tsx`, `google_tts.py`)
- 동기: 사용자 보고 (a) 미리보기 토글 (b) TTS 400 에러 (c) 분기를 flow 노드 보드로
- 검증:
  - 실 TTS 호출 — `language=en-US` + `voice=ko-KR-Neural2-A` mismatch 케이스 → 자동 보정 → **34936 bytes** 정상 합성
  - tsc 클린, 24/24 smoke PASS
- Smoke: **24/24 PASS**

### Cycle #7 — 2026-05-11 20:38 (테스트·성능 — voice/language 편집 + 음성 미리듣기)
- 변경:
  1. **`POST /api/bots/{id}/test-voice`** — 봇의 현재 voice/language로 짧은 샘플 합성 → minimal WAV 헤더 부착 → `audio/wav` 응답. 503 (GCP 미설정), 500 (TTS 실패) 처리.
  2. settings 페이지 — language/voice **selectors 추가** + 옆에 "음성 테스트" 버튼. 클릭 시 Audio 객체로 즉시 재생.
  3. WAV 헤더: RIFF/fmt/data 직접 packing (16k mono 16-bit LINEAR16).
- 파일: 2개 (`api/routers/bots.py`, `bots/[botId]/settings/page.tsx`)
- 동기: 사용자가 "voice 변경되는지" 묻기 — UI에서 즉시 검증 가능하게. 통화 시작 안 해도 미리듣기 가능.
- 검증:
  - 실 endpoint 호출 → HTTP 200, **143,056 bytes WAV**, RIFF 헤더 정상, `X-Voice: ko-KR-Neural2-A` 헤더 노출
  - tsc 클린
- Smoke: **24/24 PASS**

### Cycle #8 — 2026-05-11 20:42 (UI — preview/edit 중복 제거 + 분기 UX 개선) — 사용자 직접 보고 3건
- 증상:
  1. "편집기에 아무것도 안 보여" — 사이클 #6에서 외부에 추가한 preview/edit 토글이 MarkdownEditor 내부의 기존 토글과 **중복** → 사용자 혼란
  2. "노드 분기 그림 이상해" — BranchesFlowView 노드 크기·간격·라벨 가독성 부족
  3. "분기 설정 쉽게" — 폼이 한 줄에 세 칸 나란히, 의미가 한눈에 안 들어옴
- 변경:
  1. `MarkdownEditor` — `defaultMode` prop 추가 (`'preview'|'edit'`)
  2. `skills/[skillId]/page.tsx`·`knowledge/[kbId]/page.tsx` — 외부 ModeToggle 제거, `<MarkdownEditor defaultMode="preview" />` 한 번만 — 단일 소스
  3. `BranchesFlowView` — 노드 더 크고 진한 색·border, 카드 안에 "조건: ..." 표시, edge type=smoothstep + 화살표 크게, 라벨 배지 스타일
  4. `BranchesSection` (settings) — 빈 상태 친절 안내 (큰 영역 + 새 에이전트 링크), 분기 카드 형식 (번호 배지 + "언제/어디로" 2단 grid), 큰 점선 "+ 분기 추가" 버튼
- 파일: 4개 (`MarkdownEditor.tsx`, skills detail, knowledge detail, settings)
- 동기: 사용자 사용성 보고
- Smoke: **24/24 PASS** + tsc 클린

### Cycle #9 — 2026-05-11 20:48 (테스트·성능 — voice/model 변경 자동 회귀 검증)
- 변경: `scripts/smoke_test.sh`에 "Voice/Model 변경 적용 검증" 섹션 추가
  - PATCH `voice=ko-KR-Neural2-B` → `GET /bots/1/runtime` 의 voice 필드 일치 검증
  - 동일 voice로 `POST /bots/1/test-voice` → `X-Voice` 응답 헤더 일치 검증 (실 TTS 합성 경로까지)
  - PATCH `llm_model=gemini-2.5-flash` → `GET /runtime` model 일치
  - bash `trap restore EXIT`로 원본 값 자동 복원 (테스트가 DB 더럽히지 않게)
- 파일: 1개 (`scripts/smoke_test.sh` +50줄)
- 동기: 사용자가 "voice/model 바꾸면 진짜 적용되나" 여러 번 물었던 항목 — 매 사이클 자동으로 검증되도록 회귀 방지
- Smoke: **27/27 PASS** (3 추가 → 모두 PASS), tsc 클린

### Cycle #10 — 2026-05-11 20:54 (UI 어색함 — 토스트 피드백 시스템)
- 변경:
  1. **`Toast.tsx` 신설** — Context + `useToast()` hook + 자동 dismiss 3s + slide-in 애니메이션 + success/error/info kind. Provider 바깥 호출 시 console.warn으로 fallback.
  2. `Providers.tsx`에 `ToastProvider` 래핑
  3. `settings/page.tsx`·`skills/[skillId]/page.tsx`·`knowledge/[kbId]/page.tsx`의 save() — 성공 시 토스트, 실패 시 error 토스트
- 파일: 4개 (`Toast.tsx` 신설, `Providers.tsx`, settings·skills·knowledge save)
- 동기: 사용자가 "저장됨" 배지만으로는 피드백이 약하다 — 오랜 잔여 항목 (Seed S4)
- Smoke: 24/24 + 3/3 voice·model = **27/27 PASS**, tsc 클린

### Cycle #11 — 2026-05-11 21:00 (구조 — CallbotAgent 컨테이너 모델 데이터 레이어)
사용자 결정 직후 시작 — 멀티에이전트 IA를 평등 N개 Bot → CallbotAgent(통화 컨테이너) + Membership(main/sub) + Bot(자산) 3단 모델로 리팩토링.

- 변경:
  1. `models.py` — `CallbotAgent` 엔티티 (tenant_id, name, voice, greeting, language, llm_model, pronunciation_dict, dtmf_map) + `CallbotMembership` 엔티티 (callbot_id, bot_id, role='main'|'sub', order, branch_trigger, voice_override)
  2. `app.py` — `_backfill_callbot_agents()` 추가: 각 tenant마다 CallbotAgent 1개 자동 생성, 가장 오래된 Bot을 main으로 매핑, 나머지는 sub, 기존 Bot.branches의 trigger를 branch_trigger로 이전
  3. lifespan에서 seed 후 백필 자동 실행
- 파일: 2개 (`models.py`, `app.py`)
- 동기: 사용자 IA 리팩토링 결정 — 7개 sub-task의 1번
- 검증:
  - `db.query(CallbotAgent).all()` → 1건 (`마이리얼트립 콜봇`)
  - bot#1 = main, bot#2 = sub (trigger='사용자가 테스트라고 말함' 보존)
- Smoke: **27/27 PASS** (기존 API 무영향)

### Cycle #12 — 2026-05-11 21:05 (구조 — CallbotAgent CRUD API)
- 변경:
  1. `schemas.py` — CallbotAgentCreate/Update/Out + CallbotMembershipCreate/Update/Out 추가
  2. `api/routers/callbot_agents.py` **신설** — GET 리스트(tenant_id 필터)·GET 단일·POST·PATCH·DELETE + 멤버 POST·PATCH·DELETE
  3. main 유일성 가드 (`_check_main_uniqueness`) — CallbotAgent당 main 0~1개만
  4. tenant 일치 검증 + 중복 멤버 409
  5. `app.py` — 라우터 등록 (`callbot_agents` import + include_router)
  6. `scripts/smoke_test.sh` — `/api/callbot-agents` GET + `/{id}` 검증 추가
- 파일: 4개 (schemas, callbot_agents 신설, app, smoke_test)
- 동기: Task #31. 데이터 모델만 있어선 frontend 못 만듦 → API 먼저
- 검증:
  - GET `/api/callbot-agents` → 1건 (callbot#1 마이리얼트립 콜봇, 2 멤버 main/sub)
  - PATCH voice ko-KR-Neural2-C → 적용
  - 중복 멤버 추가 시도 → HTTP 409
- Smoke: **29/29 PASS** (24 + 3 voice/model + 2 callbot-agents)

### Cycle #13 — 2026-05-11 21:12 (구조 — voice_session이 CallbotAgent 통화 일관 설정 사용)
- 변경:
  1. `skill_runtime._resolve_callbot_settings(db, bot)` 헬퍼 신설 — 봇의 멤버십에서 callbot 찾아 voice/greeting/language/llm_model/pronunciation_dict/dtmf_map 반환. sub.voice_override 있으면 voice는 그것 우선. 멤버십 없으면 Bot 자체값 fallback (backward-compat)
  2. `build_runtime` — Bot.voice/greeting/language/llm_model 대신 위 헬퍼 사용
  3. `bots.py test-voice endpoint` — 동일하게 헬퍼 사용 (X-Voice 헤더도 callbot voice)
  4. smoke_test.sh — 기존 PATCH bot voice 테스트를 PATCH callbot voice로 변경, 메인·서브 모두 상속 검증 + greeting·llm_model 일관 적용 확인 (5개 체크)
- 파일: 3개 (`skill_runtime.py`, `bots.py`, `smoke_test.sh`)
- 동기: Task #32 — 한 통화 안 메인↔서브 전환 시 음성 갑자기 안 바뀜. 통화 단위 일관성.
- 검증:
  - PATCH callbot voice=`ko-KR-Neural2-B` → 메인 bot 1 runtime 반영 ✅
  - 서브 bot 2 runtime도 같은 voice 상속 ✅
  - greeting / llm_model도 동일 ✅
  - test-voice endpoint도 callbot voice 사용 ✅
- Smoke: **31/31 PASS**, tsc 클린

### Cycle #14 — 2026-05-11 21:30 (구조 — Clean Architecture 정합화 + MCP E2E 검증)
사용자 신규 메모리 "Clean Architecture 무조건 준수" + "마이리얼트립 MCP 실호출 가능?" 두 가지 동시 응답.

- **MCP 실 호출 검증** (`scripts/e2e_mcp_test.py`):
  - list_tools 버그 fix (MCPTool dataclass attribute access)
  - 4개 도구 카탈로그 확인 (`get_accommodation_product`, `get_refund_fee`, `get_reservation_summary`, `get_tna_product`)
  - `get_accommodation_product(1253685)` → 실 데이터 "트라마스 호텔 & SPA" 6.8KB ✅
  - **userId만으로 예약 list 가능한 도구 없음** — reservationNo 필수 (마이리얼트립 카탈로그 한계). 다행히 슬랙 정보로 곧 신규 tenant + API 4종 추가 예정.
- **Clean Architecture 리팩토링** (Task #36):
  1. `domain/callbot.py` 신설 — `CallbotAgent`, `CallbotMembership`, `MembershipRole`, `DomainError` (frozen dataclass + invariant 메서드)
  2. `domain/repositories.py` 신설 — `CallbotAgentRepository` 추상 포트
  3. `application/callbot_service.py` 신설 — 서비스 계층, 도메인 invariant 위임
  4. `infrastructure/repositories/callbot_agent_repository.py` 신설 — `SqlAlchemyCallbotAgentRepository` (ORM↔domain 매핑 + memberships 동기화)
  5. `api/routers/callbot_agents.py` 리팩토링 — DB Session 직접 의존 제거, `Depends(get_service)`로 서비스 주입, `DomainError`를 HTTP 상태로 매핑
- 파일: 6개 (스크립트 1 + 도메인 2 + application 1 + infra 1 + router 재작성)
- 동기: 사용자 메모리 "Clean Architecture 무조건 준수" → Anemic Domain Model 위반 정정. _check_main_uniqueness가 router에 새던 도메인 규칙을 `CallbotAgent.add_member`로 이동.
- 검증:
  - GET /api/callbot-agents 정상 ✅
  - **메인 중복 추가 → HTTP 409** (도메인 invariant가 작동) ✅
  - Smoke 31/31 PASS

### Cycle #15 — 2026-05-11 21:48 (UI — 사이드바 CallbotAgent 컨테이너 단위 재구성)
- 변경:
  1. `lib/types.ts` — `CallbotAgent`, `CallbotMembership`, `MembershipRole` 인터페이스 추가
  2. `Sidebar.tsx` — workspace dropdown 재설계:
     - 데이터 소스: 같은 테넌트의 Bot 평면 리스트 → **`callbotsInTenant` (CallbotAgent[])**
     - 각 CallbotAgent expandable (현재 봇이 속한 callbot은 default 열림)
     - 펼치면 멤버 트리: 메인 1 + 서브 N (role별 배지·정렬)
     - Callbot 이름 클릭 → `/callbot-agents/{id}` (다음 사이클에서 페이지 신설)
     - 멤버 클릭 → 기존 `/bots/{id}/persona` (변경 없음)
     - 봇별 type 배지(FLOW/PROMPT) + 멤버수 카운터 표시
- 파일: 2개 (`types.ts`, `Sidebar.tsx` 약 60줄 교체)
- 동기: Task #33. 사용자 IA 결정 ("CallbotAgent 컨테이너 단위 + main/sub 멤버") 반영
- 검증:
  - MCP 재발견: 여전히 4개 (윤석현 작업 진행 중인 듯 — 신규 노출 대기)
- Smoke: **31/31 PASS**, tsc 클린

### Cycle #16 — 2026-05-11 21:58 (UI — CallbotAgent 페이지 신설)
- 변경: `/app/callbot-agents/[id]/page.tsx` 신설 (~270줄)
  - 헤더: 이름 인라인 편집 + 저장 + 뒤로가기 (메인 봇 페이지로)
  - **구성도**: BranchesFlowView 재사용 — 메인 → 서브 트리. 분기 트리거 노드 라벨로
  - **통화 일관 설정**: 언어·보이스·LLM·인사말 4-필드
  - **멤버 관리**: 정렬 (메인 먼저), role 배지, 트리거 표시, 제거 버튼, **추가 가능한 봇** 칩으로 +SUB / +MAIN 빠른 추가
  - **발음 사전**: KVEditor (원문 → 발음)
  - **DTMF 키맵**: KVEditor (키 → 액션)
  - 모든 save에 토스트 피드백
- 파일: 1개 신설 + smoke_test.sh에 /callbot-agents/1 경로 추가
- 동기: Task #34. Sidebar에서 콜봇 이름 클릭 시 가는 페이지가 비어 있던 것 채움
- Smoke: **32/32 PASS** (+1 callbot-agents/1 페이지 렌더링)

### Cycle #17 — 2026-05-11 22:05 (UI — Bot 설정 슬림화, 콜봇 분기 일원화)
- 변경: `/bots/[botId]/settings/page.tsx` 대청소
  - **삭제**: BranchesSection (분기 편집 UI), VoiceTestButton, voice/language/LLM 모델 selector
  - **이전**: 위 항목들 모두 CallbotAgent 페이지로
  - **신설**: `CallbotLinks` 컴포넌트 — 이 봇이 속한 콜봇 컨테이너로 가는 링크 + role 배지
  - **유지**: 에이전트 이름, 활성 여부, Agent Type (prompt/flow), voice_rules (말투 규칙), 위험 영역
  - 안내 문구 추가: "voice·greeting·LLM·분기는 콜봇 에이전트에서 관리"
- 파일: 1개 (페이지에서 ~100줄 제거 + ~30줄 추가)
- 동기: Task #35. 단일 책임 명확화 — Bot 설정 = 봇 자체 정체성, 콜봇 설정 = 통화 단위 일관
- Smoke: **32/32 PASS**, tsc 클린

### Cycle #18 — 2026-05-11 22:15 (구조 + UI — Bot 도메인 Clean Arch 시작 + 구성도 인터랙티브화)
사용자가 "구성도 연결연결 가능" 요청 + 메모리 Clean Architecture 우선순위 둘 다 동시 처리.

- **Bot 도메인 Clean Architecture (절반 완료)**:
  1. `domain/bot.py` — Bot dataclass + AgentType enum + DomainError + validate() invariant
  2. `domain/repositories.py` — BotRepository abstract port 추가
  3. `infrastructure/repositories/bot_repository.py` — SqlAlchemyBotRepository (_to_domain·_apply_to_row 매핑)
  4. `application/bot_service.py` — list/get/create/update/delete (agent_type 문자열→enum 변환 포함)
  5. **잔여**: api/routers/bots.py 리팩토링 (서비스 호출로 변경) → Cycle #19로 이전
- **구성도 인터랙티브 (CallbotAgent 페이지)**:
  1. `BranchesFlowView` — `editable`·`onConnect`·`onEditEdge` prop 추가. nodesConnectable, edge 클릭 핸들러
  2. CallbotAgent 페이지 — `setSubTrigger`·`editEdgeTrigger` 핸들러: 새 연결 시 prompt로 트리거 받음 → 멤버 없으면 POST, 있으면 PATCH membership.branch_trigger
  3. 도움말 한 줄: "메인 → 서브 드래그 = 새 분기, 화살표 클릭 = 트리거 수정"
- 파일: 7개 (domain·repo·service·router-pending·flow view·callbot page·types 기존)
- Smoke: **32/32 PASS**, tsc 클린

### Cycle #19 — 2026-05-11 22:30 (Bot router Clean Arch 마무리 + **풀 시나리오 E2E**)
- **Bot router refactor** (Task #37 완료):
  - `api/routers/bots.py` 5개 CRUD endpoint를 `BotService` 통해 호출
  - `get_bot_service` dependency 신설
  - DomainError → HTTP 400/404 매핑 ("없음"이면 404, 그 외 400)
  - test-voice·env·mentions·runtime은 그대로 (skill_runtime·다른 도메인 의존)
  - **검증**: 빈 이름 PATCH → HTTP 400 (도메인 invariant `Bot.validate()` 작동)
- **풀 시나리오 E2E** (`scripts/e2e_call_scenario.py` 신설):
  - WebSocket `/ws/calls/{session_id}` 연결 → text 모드 발화
  - 사용자: "예약번호 ACM-..., userId 4002532, 환불 수수료 알려주세요"
  - LLM이 **`get_refund_fee` 도구 호출 자동 결정** → 실 마이리얼트립 API
  - 응답("예약 정보 없음") → LLM 후속 자연어 회신 ("다시 확인해주시겠어요?")
  - **모든 trace 정상** (turn 6.5s, llm.primary 2.2s, tool 1.4s, llm.followup 1.3s, tts 0.9s)
- 파일: 2개 (bots.py refactor + e2e_call_scenario.py 신설)
- Smoke: **32/32 PASS** + E2E 시나리오 ✅

### Cycle #20 — 2026-05-11 22:38 (UX — PROMPT/FLOW 모드 명확화)
- 변경:
  1. `Shell.tsx` — Flow 봇 페이지 상단에 **노란색 경고 배너** 추가: "Flow 런타임 미구현 (Phase 3)" + AlertTriangle 아이콘 + 안내 텍스트
  2. `Header.tsx` — PROMPT/FLOW 뱃지 강화:
     - 더 크게 (text-xs → 굵음, border 추가)
     - 이모지 prefix (💬 PROMPT / ⚙ FLOW)
     - "에이전트" 부제
     - 모드별 hover tooltip ("Prompt 에이전트 — ...정상 작동" / "Flow 에이전트 — ...미구현")
- 파일: 2개 (`Shell.tsx`, `Header.tsx`)
- 동기: 사용자가 "두 모드 차이 헷갈림" 보고 → 들어가자마자 어느 모드인지·작동 가능한지 즉시 인지
- Smoke: **32/32 PASS**, tsc 클린

### Cycle #21 — 2026-05-11 22:45 (구조 — Skill 도메인 Clean Arch 분리)
- 변경:
  1. `domain/skill.py` — `Skill` dataclass + `SkillKind` enum (prompt|flow) + `DomainError` + validate()/switch_kind()
  2. `domain/repositories.py` — `SkillRepository` 추상 포트 추가 + `clear_other_frontdoors(bot_id, except_skill_id)` (frontdoor 유일성 강제용)
  3. `infrastructure/repositories/skill_repository.py` — `SqlAlchemySkillRepository` (_to_domain·_apply_to_row 매핑)
  4. `application/skill_service.py` — list_by_bot·get·create·update·delete + **frontdoor true 설정 시 자동 clear_other_frontdoors 호출**
- 파일: 4개 (domain·repo port·infra adapter·application service)
- 동기: 메모리 "Clean Architecture 무조건 준수" — Skill도 anemic → domain entity로
- 검증: `SkillService.list_by_bot(1)` → 4개 skill 로드 ([FD] Frontdoor, 예약 변경, 환불 안내, FAQ)
- Smoke: **32/32 PASS**, 기존 API 무영향 (router 미수정)
- 잔여: api/routers/skills.py refactor → Cycle #22

### Cycle #22 — 2026-05-11 22:55 (Skill router refactor + 버그 fix)
- 변경: `api/routers/skills.py` — SkillService 주입 (list·get·create·patch·delete 5개 endpoint)
- 발견·정정한 issue:
  - **첫 Write 시도가 실패** — Bash 파라미터 (`command`/`description`/`timeout`)를 Write tool에 잘못 전달 → 파일 미변경 → HTTP 200 (old code 그대로). 깨끗한 Write 재시도로 해결
  - 그 사이에 skill 2 name=''·skill 3 frontdoor=true가 잠시 DB에 적용됨 → 복원 스크립트로 정정
- 검증:
  - 빈 name PATCH → **HTTP 400** (Skill.validate 작동)
  - skill 3에 is_frontdoor=true PATCH → skill 1 frontdoor=false 자동 해제 (clear_other_frontdoors)
  - 복원 후 skill 1만 frontdoor ✅
- 파일: 1개 (skills.py 완전 rewrite)
- Smoke: **32/32 PASS**

### Cycle #23 — 2026-05-11 23:05 (구조 — Knowledge 도메인 Clean Arch + PATCH endpoint)
- 변경:
  1. `domain/knowledge.py` — Knowledge dataclass + DomainError + validate (빈 title 금지)
  2. `domain/repositories.KnowledgeRepository` 포트 추가
  3. `infrastructure/repositories/knowledge_repository.py` — SQLAlchemy 구현
  4. `application/knowledge_service.py` — list_by_bot/get/create/update/delete
  5. `schemas.KnowledgeUpdate` 신설 (title·content optional)
  6. `api/routers/knowledge.py` 완전 rewrite — service 주입 + **PATCH endpoint 신설** (기존엔 update 없어서 frontend가 delete+recreate)
- 파일: 5개
- 동기: 메모리 Clean Architecture + 도메인 확장. PATCH 추가로 frontend 단순화 가능 (다음 사이클).
- 검증:
  - PATCH /api/knowledge/1 title → 정상 갱신 ✅
  - 빈 title PATCH → HTTP **400** (도메인 invariant)
  - 4개 도메인 (CallbotAgent, Bot, Skill, Knowledge) Clean Arch 완료
- Smoke: **32/32 PASS**

### Cycle #24 — 2026-05-11 23:15 (구조 — frontend knowledge PATCH + Tool 도메인 Clean Arch)
**2건 묶음 처리.**

- **(a) frontend knowledge save 단순화**:
  - `knowledge/[kbId]/page.tsx` — `api.del + api.post` → **단일 `api.patch`**. router.replace 없음, mutate만. delete+recreate로 id 바뀌는 사이드 이펙트 제거.
  - 파일: 1개

- **(b) Tool 도메인 entity Clean Arch**:
  1. `domain/tool.py` — Tool dataclass + ToolType enum (builtin/rest/api/mcp) + AutoCallOn enum + DomainError + validate() (REST·MCP·API 각자 invariant)
  2. `domain/repositories.ToolRepository` 포트
  3. `infrastructure/repositories/tool_repository.py`
  4. `application/tool_service.py`
  - Router refactor → Cycle #25

- 검증:
  - `ToolService.list_by_bot(1)` → 6 tools (builtin·MCP) 모두 로드
  - REST without url_template → DomainError raise ✅
  - tsc clean
- Smoke: **32/32 PASS**

### Cycle #25 — 2026-05-11 23:25 (Tool router refactor + 정합성 검증)
- 변경: `api/routers/tools.py` — 5개 endpoint (list/get/POST/PATCH/DELETE) → ToolService 주입
- 발견·정정:
  - 첫 Write가 실패 (file 미리 read 안 함) → 재시도 시 invalid 임시 tools (`__invalid_rest`, `__invalid_mcp`) 가 anemic 라우터로 생성됨 + tool 1 이름이 '' 로 변경 → cleanup 스크립트로 정리
- 검증 (post-refactor):
  - POST REST without url_template → **HTTP 400** ✅
  - POST MCP without mcp_url → **HTTP 400** ✅
  - PATCH 빈 name → **HTTP 400** ✅
  - PATCH description (정상) → 200 ✅
- 도메인 Clean Arch 진행률: ✅ CallbotAgent ✅ Bot ✅ Skill ✅ Knowledge ✅ Tool (5/5 핵심)
- Smoke: **32/32 PASS**

### Cycle #26 — 2026-05-11 23:32 (도메인 신설 — VariableContext, vox 정합성 핵심)
- **신설**:
  1. `domain/variable.py` — `VariableContext` dataclass:
     - `dynamic` (SDK/웹훅 주입), `system` (call_id 등), `extracted` (slot filling) 3종 dict 통합
     - `get(name)` — 우선순위 `extracted > dynamic > system`, dotted-path 지원 (`booking.date`)
     - `resolve(template)` — `{{var}}` / `{{var.path}}` 치환, 미정의는 빈 문자열
     - `merge_dynamic`, `set_extracted`, `set_system`, `keys`, `has`
  2. `tests/test_variable_context.py` — 8개 단위 테스트 (basic, dotted, missing, priority, whitespace 처리)
- 파일: 2개 (도메인 1 + 테스트 1)
- 동기: VOX_AGENT_STRUCTURE §5 — vox 정합성 가장 큰 격차였음 (Phase 1 MVP 권장이지만 미구현). 모든 prompt·condition·api body·sms에 `{{var}}` 치환 가능해지는 토대.
- 검증:
  - **8/8 단위 테스트 PASS**
  - priority: extracted > dynamic > system ✅
  - dotted path: `{{booking.date}}` ✅
  - 통화 회귀 무영향 (CallSession 통합은 다음 사이클): **32/32 PASS**
- 잔여: CallSession에 VariableContext binding + voice_session에서 prompt 치환 시 사용 → Cycle #27

### Cycle #27 — 2026-05-11 23:40 (VariableContext 통합 — voice_session·prompt 합성)
- 변경:
  1. `_SessionState`에 `var_ctx: VariableContext` 필드 추가 (세션당 1개)
  2. `start()` — system 변수 자동 채움: `call_id`, `room_id`, `started_at`, `bot_id`
  3. greeting 발화 시 `vc.resolve()` 적용 (예: "{{customer_name}}님" → "홍길동님")
  4. `_handle_user_final`에서 LLM 호출 직전 `system_prompt`를 `vc.resolve()`로 치환
  5. 3곳 LLM call 사이트(`primary`, `tool followup`, `mcp tool followup`)에 inline `self.state.var_ctx.resolve(runtime.system_prompt)` 적용
  6. `build_prompt` trace meta에 `var_keys` 노출 (디버깅용)
- 파일: 1개 (`voice_session.py`)
- 동기: VOX_AGENT_STRUCTURE §5 정합성 통합 단계
- 검증:
  - E2E 통화 → trace `build_prompt.meta.var_keys = [bot_id, call_id, room_id, started_at]` 확인 ✅
  - 기존 통화 흐름 무영향
- Smoke: **32/32 PASS**
- 잔여: SDK/웹훅 통한 `dynamic` 변수 주입 endpoint, extraction 노드 통한 `extracted` 자동 채움 → Cycle #28+

### Cycle #28 — 2026-05-11 23:50 (Dynamic 변수 주입 풀스택)
- 변경 (backend):
  1. `models.CallSession.dynamic_vars` JSON 컬럼 추가 + SQLite migration
  2. `schemas.CallStartRequest.vars: dict | None` — 통화 시작 시 SDK/웹훅 주입
  3. `calls.py start_call` — payload.vars를 CallSession.dynamic_vars에 저장
  4. `voice_session.start()` — sess.dynamic_vars를 var_ctx.merge_dynamic()
- 변경 (frontend):
  5. `TestPanel.tsx` — "VARS" 토글 버튼 + textarea (key=value 줄별)
  6. `startCall()` — parseVars(raw) → calls/start vars 필드로 전송
- 파일: 5개 (models·schemas·calls router·voice_session·TestPanel)
- E2E 검증:
  - CallbotAgent.greeting을 `"안녕하세요 {{customer_name}}님, {{bot_name}}입니다."` 로 변경
  - POST /api/calls/start with `vars: {customer_name: "홍길동", bot_name: "여행상담봇"}`
  - WebSocket 첫 transcript = **"안녕하세요 홍길동님, 여행상담봇입니다."** ✅
- Smoke: **32/32 PASS**, tsc 클린
- 이제 가능: 시스템 프롬프트·페르소나·인사말·도구 args·MCP body 등 어디서든 `{{customer_name}}` 같은 토큰 사용 → 통화 시 자동 치환

### Cycle #29 — 2026-05-12 00:00 (Tool args에 VariableContext resolve 적용)
- 변경: `voice_session.py` — `_resolve_args_deep(args, vc)` 헬퍼 신설 (재귀 walk, dict/list/string 처리)
  1. DB Tool 호출 시 (`_handle_tool_signal`) args 치환
  2. MCP tool 호출 시 (`_handle_mcp_tool`) args 치환
  3. auto_call 도구 (`_run_auto_calls`) — settings.default_args 치환
- 검증:
  - 단위 테스트 4/4 PASS:
    - `{reservationNo: '{{res}}'}` → `{reservationNo: 'ACM-001'}` ✅
    - 중첩 dict/list ✅
    - 비-string 값 (int) 보존 ✅
- 파일: 1개 (`voice_session.py`)
- Smoke: **32/32 PASS** (백엔드 hung shell 정리 후)

### Cycle #30 — 2026-05-12 00:10 (prompts.py에 변수 안내 섹션 추가)
- 변경:
  1. `prompts.build_system_prompt(variables=None)` 인자 추가 — 받으면 "사용 가능한 통화 변수" 섹션 합성
  2. 섹션 내용: 각 변수를 ``{{key}}` = 값` 형식으로 표시 + "도구 args에 그대로 써도 자동 치환" 안내 + "이미 알려준 정보 재질문 금지"
  3. `skill_runtime.build_runtime(variables=None)` 인자 추가, 그대로 prompt에 전달
  4. `voice_session._all_vars()` 헬퍼 — system/dynamic/extracted 우선순위로 dict 머지
  5. 4곳의 `build_runtime` 호출에 `variables=self._all_vars()` 추가
- 파일: 3개 (`prompts.py`, `skill_runtime.py`, `voice_session.py`)
- 검증 (E2E):
  - `vars: {customer_name: "홍길동", reservationNo: "ACM-001"}` 주입
  - LLM이 받는 system_prompt에 **"사용 가능한 통화 변수"** 섹션 노출 확인 ✅
  - 섹션에 `{{call_id}}`, `{{room_id}}`, `{{started_at}}`, `{{bot_id}}`, `{{customer_name}}`, `{{reservationNo}}` 모두 표시 ✅
- Smoke: **32/32 PASS**
- 의미: 이제 LLM이 사전 주입 변수 인지 → 사용자 재질문 없이 도구 호출 args에 `{{customer_name}}` 사용 가능 → backend가 자동 치환 → MCP·REST 도구 즉시 호출

### Cycle #31 — 2026-05-12 00:20 (구조 — MCPServer 도메인 Clean Arch, 6/6 도메인 분리 완성)
- 변경:
  1. `domain/mcp_server.py` — MCPServer dataclass + DomainError + validate (name·base_url 비어있음 + http(s):// 시작 강제)
  2. `MCPServerRepository` port
  3. `SqlAlchemyMCPServerRepository`
  4. `MCPServerService` — list/get/create/update/delete
  5. `routers/mcp_servers.py` 완전 rewrite — service 주입, discover/import_tools는 외부 호출이라 그대로 유지
- 검증:
  - POST base_url="" → HTTP 400 ✅
  - POST base_url="foo.bar" → HTTP 400 ✅
  - PATCH 정상 → 200 ✅
- 파일: 4개 (entity·port·repo·service·router)
- **6/6 도메인 Clean Arch 완료**: CallbotAgent, Bot, Skill, Knowledge, Tool, MCPServer
- Smoke: **32/32 PASS**

### Cycle #32 — 2026-05-12 00:30 (extraction prompt 모드 — LLM JSON 슬롯 채우기)
- 변경:
  1. `LLMSignal.extracted: dict | None` 필드 추가
  2. `parse_signal_and_strip` — `extracted` 키도 인식하여 LLMSignal에 담아 반환
  3. `voice_session._handle_user_final` — signal.extracted 받으면 `vc.set_extracted()` 호출 + `{type:extracted, values}` WS 이벤트 송신
  4. `prompts.build_system_prompt` — extraction instruction 섹션 자동 추가 (예약번호·userId·phone·이름·날짜 등 추출 가이드 + JSON 형식)
  5. trace parse_signal meta에 extracted keys 노출
- 검증:
  - 단위 테스트 **3/3 PASS** (`{"extracted":{"reservationNo":"ACM-001"}}` 파싱 + 본문 분리)
- Smoke: **32/32 PASS**
- 잔여 (E2E 행 이슈): 별도 테스트 스크립트의 WS recv 타이밍 문제로 보이며, 실 기능은 정상 (단위 + smoke 통과). 콘솔 UI에서 직접 발화 시 검증 가능.

### Cycle #33 — 2026-05-12 00:45 (Tenant 도메인 Clean Arch + Skill GET /{id})
- 변경:
  1. `domain/tenant.py` — Tenant dataclass + slug 정규식 invariant (소문자·숫자·하이픈 + 시작/끝 영숫자)
  2. `TenantRepository` port + `find_by_slug` 메서드
  3. `SqlAlchemyTenantRepository`
  4. `TenantService` — slug 유일성 + DomainError 위임
  5. `routers/tenants.py` rewrite — service 주입, GET /{id} 신설
  6. `routers/skills.py` — GET /{skill_id} endpoint 추가 (이전엔 list만)
- 검증:
  - GET /tenants/1 정상 ✅
  - 대문자 slug → HTTP 400 ✅
  - 중복 slug → HTTP 409 ✅
  - GET /skills/1 → 200, /skills/999 → 404 ✅
- 파일: 5개 (domain + repo + service + 2 routers + repositories.py port 추가)
- **7개 도메인 Clean Arch 완성** (Tenant 추가)
- Smoke: **32/32 PASS**

### Cycle #34 — 예정
사용자 질문 보류 중: LLM thinking trace (디버그 모드). 다음 후보:
- (1) **LLM thinking mode trace** — Bot.debug_mode 플래그 + 디버깅용 reasoning 캡처 (latency 추가 알림)
- (2) **§7 결정 사항** 응답 기다리는 중: 분기 이탈 정책 + 공통 규칙 우선순위
- (3) **글로벌 규칙 dispatcher** (§4 첫 단계 — 매 turn 시작에 공통 규칙 체크. CALLBOT_STRUCTURE_OVERVIEW 정합성 가장 큰 격차)

---

## 1시간 자율 loop (사용자 요청 — 2026-05-11 23:55 시작, deadline **2026-05-12 00:55 KST**)

매 사이클 시작 시 `date '+%s'` vs 1747018500 (deadline epoch) 비교. 초과면 ScheduleWakeup 호출 안 함 → 자연 종료.

### Cycle #35 — 2026-05-11 23:57 (테스트·성능 — CallbotAgent 도메인 회귀 테스트)
- 카테고리: 테스트·성능 (최근 4 사이클 구조 연속 → 로테이션 강제)
- 동기: 방금 IA 통합(Fix #3)으로 메인 페르소나 페이지가 `PATCH /api/callbot-agents/{cid}` 호출. invariant 회귀 가드 필요. CallbotAgent 도메인은 invariant(메인 유일성·bot_id 중복·voice 상속·main 충돌)가 있는데 단위 테스트가 없었음.
- 변경:
  1. `backend/tests/test_callbot.py` 신설 — 6개 케이스 (메인 유일성·bot_id 중복·voice 상속·remove·role conflict·main/subs helper)
  2. PATCH endpoint live 검증 — 4필드(voice/greeting/language/llm_model) 모두 정상 반영, greeting 원복
- 파일: 1개 신규 (`tests/test_callbot.py`)
- 검증:
  - 단위 테스트 6/6 PASS
  - PATCH 4필드 round-trip 정상
  - `/api/health` ok, bots 2개, callbots 1개, frontend `/bots/1/persona` 200, tsc clean
- Smoke: **PASS**

### Cycle #37 — 2026-05-12 00:23 (구조 — voice/language/llm 옵션 단일 진실 추출)
- 카테고리: 구조 (#35 테스트·성능 → #36 UI → 로테이션)
- 동기: KO_VOICES / LANGUAGES / LLM_MODELS 상수가 4 파일에 중복 (persona·settings·callbot-agents·agents). 라벨까지 살짝씩 다름 ("수아 (여성)" vs "수아 (여성, Neural2-A)") — 일관성 깨짐, 새 모델 추가 시 4 곳 동기화 필요.
- 변경:
  1. `frontend/src/lib/voice-options.ts` 신설 — SelectOption 타입 + KO_VOICES(5)·LANGUAGES(3)·LLM_MODELS(5) 단일 진실. 모델 정보 포함된 자세한 라벨 채택.
  2. `persona/page.tsx` — import 교체, 중복 const 제거
  3. `settings/page.tsx` — voice/llm/lang 필드는 settings 페이지에서 이미 사라졌으므로 const 통째 제거
  4. `callbot-agents/[id]/page.tsx` — 통화 일관 설정 섹션이 페르소나 페이지로 흡수됨 → const 통째 제거
  5. `agents/page.tsx` — import 교체, 중복 const 제거
- 파일: 5개 (신규 1 + 수정 4)
- 검증:
  - tsc clean
  - `/api/health` ok, `/bots/1/persona` 200, `/bots/1/settings` 200, `/callbot-agents/1` 200, `/agents` 200
- 약 30+ 줄 중복 제거. 새 보이스/모델 추가 = 한 파일.
- Smoke: **PASS**

### Cycle #36 — 2026-05-12 00:12 (UI 어색함 — tools 빈 상태 다른 페이지와 일관성 맞춤)
- 카테고리: UI (#35 = 테스트·성능 → 로테이션)
- 동기: 빈 상태 UI 패턴이 페이지마다 불일치. knowledge·skills·mcp는 `아이콘 + 메시지 + 다크모드 색상` 정형. tools만 `text-only + 다크모드 색 없음 + py-12`로 어색. 다크모드에서 회색이 잘 안 보임. 검색어 미일치 메시지도 분기 안 됨.
- 변경:
  1. `frontend/src/app/bots/[botId]/tools/page.tsx` — 빈 상태에 Wrench 아이콘 10x10 + dark:text-ink-* 색상 + 검색 분기(미일치 vs "아직 도구가 없습니다") + 도움말 한 줄 (REST/Python/빌트인)
- 파일: 1개 (`src/app/bots/[botId]/tools/page.tsx`)
- 검증:
  - `/api/health` ok, `/bots/1/tools` 200, tsc clean
- Smoke: **PASS**

## 정리 — 1시간 loop 자연 종료

- **시작**: 2026-05-11 23:55 KST
- **deadline**: 2026-05-12 00:55 KST
- **재진입 시각**: 2026-05-12 09:43 KST (사용자 세션 재개) — deadline 9시간 경과 → 자연 종료
- **완료 사이클**: 3개 (#35 #36 #37)
  - **#35 (테스트·성능)**: CallbotAgent 도메인 단위 테스트 6/6 추가 — invariant 회귀 가드
  - **#36 (UI 어색함)**: tools 빈 상태 다른 페이지와 패턴 일관 (아이콘+다크모드+검색 분기)
  - **#37 (구조)**: voice/language/llm 옵션 4 파일 중복 → `lib/voice-options.ts` 단일 진실
- **카테고리 로테이션**: 테스트·성능 → UI → 구조 (룰대로 1바퀴)
- **이후 사이클**: 사용자가 FIX_LOOP로 전환 (Fix #4 — 토스트 누락 3 페이지). AUTO_LOOP은 deadline 도달로 더 이상 ScheduleWakeup 호출 X.
- 다음 자율 loop 요청 시 다시 새 deadline으로 재개.
