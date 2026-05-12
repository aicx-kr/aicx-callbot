# callbot-platform 자잘한 이슈 + UI 어색함 수정 로그

> `/loop FIX_LOOP_PROMPT.md` 가 iteration마다 ONE fix씩 append.
> 시작: 2026-05-11

## Seed (사용자 직접 보고 이슈)


| ID  | 이슈                                  | Status       |
| --- | ----------------------------------- | ------------ |
| S1  | 보이스 셀렉터 변경이 통화에 적용 안 됨              | ✅ Fix #3 (메인 페이지 흡수, CallbotAgent PATCH)  |
| S2  | Waterfall 어색 (정렬/색/막대/툴팁)           | 🟡 Fix #7 (툴팁 OK, 잔여: 색·막대 가독성) |
| S3  | 사이드바 워크스페이스 selector dead UI        | ⏳ next iter  |
| S4  | 폼 저장 후 토스트/피드백 없음                   | 🟢 Fix #4 #5 #8 (5/6, 잔여: flow 그래프 별도) |
| S5  | TestPanel 봇 자기 음성 echo 회귀 가능성       | 🟢 Fix #10 #13 (브라우저+GCP 양 모드 보강) |
| S7  | MCP 도구 import + agent_type 사이드바 동기화 | ✅ Fix #1, #2 |


## Fixes

### Fix #1 — MCP 서버에서 발견된 도구를 일반 Tool로 import (운영자 친화)

- **Area**: 6 (데이터 흐름) + 7 (도구)
- **Seed**: 사용자 요청 — "거기 있는 애들 다 도구로 등록"
- **Symptom**: MCP 서버 통합 추상이 한 단계 더 있어 도구 관리가 분산됨. 운영자가 도구 페이지에서 한눈에 안 보임.
- **Root cause**: 발견된 MCP 도구가 우리 Tool 모델로 자동 INSERT 되지 않음.
- **Files changed**:
  - `backend/src/api/routers/mcp_servers.py` — `POST /api/mcp_servers/{id}/import_tools` 신설 (자동 discover + Tool 생성, type='mcp', 중복 skip)
  - `backend/src/application/tool_runtime.py` — `_execute_mcp` 분기 추가, settings.mcp_url/mcp_tool_name/auth_header 사용해 JSON-RPC tools/call 프록시
  - `frontend/src/app/bots/[botId]/mcp/page.tsx` — "도구로 import (N)" 버튼 + 확인 모달
  - `frontend/src/components/Sidebar.tsx` — MCP 서버 메뉴 복귀
- **Verification**: 사용자 endpoint `https://api.dev-aicx.kr/plugins/mcp/tenants/19` 에 대해 CRUD POST 201, discover 502(401 Unauthorized — 인증 토큰 미설정, 정상 에러), import 함수 동작 확인. 토큰 받으면 즉시 사용 가능.
- **Status**: ✅ FIXED (인프라 완성, 토큰 입력만 남음)
- **Fixed**: 2026-05-11 (iter 1)

### Fix #13 — GCP 모드 봇 발화 종료 후 echo grace (500ms)

- **Area**: 7 (음성/통화 흐름)
- **Seed**: S5 잔여 (GCP 모드 — Fix #10은 브라우저 모드만 보강했음)
- **Symptom**: 사용자 이전 보고 "그 다음 발화 안 잡혀". 가설 — 봇 TTS PCM이 클라이언트 스피커로 재생되며 마이크가 잔향을 잡아 백엔드 VAD가 `speech_start`를 false positive로 emit → 봇 자기 발화 직후 짧은 시간 동안 STT가 봇 echo를 사용자 발화로 처리해 다음 진짜 발화 못 받음.
- **Root cause**: `_on_speech_start`가 봇 발화 종료 직후 들어온 speech_start와 진짜 사용자 발화를 구분 못 함.
- **Files changed**:
  - `backend/src/application/voice_session.py:103` — `_ECHO_GRACE_S = 0.5` 상수
  - `backend/src/application/voice_session.py:_SessionState` — `last_speak_end_t: float = 0.0` 필드
  - `backend/src/application/voice_session.py:_on_speech_start` — idle 상태에서 `monotonic() - last_speak_end_t < 0.5s` 이면 echo로 간주, 무시. barge-in (speaking 중 끼어들기)은 영향 X.
  - `backend/src/application/voice_session.py:_speak` — `try/finally`로 발화 종료 시각 항상 기록 (cancel/barge-in 케이스 포함 — 잔향 가능)
- **Verification**:
  - import OK, `_ECHO_GRACE_S=0.5` 노출 확인
  - 백엔드 재기동 → `/api/health` 200, `voice_mode_available=true`
  - 시각 검증은 다음 GCP 모드 통화에서 봇 발화 끝나고 사용자가 즉시 말할 때 차단 없음 + 봇 echo로는 listening 진입 안 됨 확인
- **Trade-off**: 사용자가 봇 발화 종료 후 500ms 안에 말하면 그 발화는 무시됨. 0.5s는 균형점 (Silero VAD 평균 reaction 100-200ms + 잔향 100-300ms).
- **Status**: ✅ FIXED — S5 양 모드 모두 보강 완료
- **Fixed**: 2026-05-12 (iter 12)

### Fix #12 — LLM history에 인사말만 쌓이는 SQLAlchemy 캐시 회귀 (사용자 보고, 큰 임팩트)

- **Area**: 6 (데이터 흐름) + 7 (음성/통화 흐름)
- **Seed**: 사용자 직접 보고 — "history에 내역이 제대로 안 쌓이는 것 같아" + 세션 73 trace 첨부
- **Symptom**: 통화 한 통(turn 5번) 동안 매 `llm.stream` 호출의 history가 **인사말 1개**로 동일. 봇이 사용자 직전 발화와 자기 직전 응답을 전혀 기억 못 함 → 매 turn 막다른 골목 ("모르겠어"·"상품 조회"·"소장품"·"조성범"이 단절 처리). 세션 73 품질 저하의 주범 중 하나.
- **Root cause** (DB 검증으로 확정):
  1. `db.py:20` `SessionLocal = sessionmaker(..., expire_on_commit=False)` — commit 후 인스턴스 attribute 만료 안 됨
  2. `_save_transcript()`: `Transcript(session_id=...)` FK만 설정, `sess.transcripts.append(t)` 또는 `t.session=sess` 안 함 → SQLAlchemy backref 미갱신
  3. `_build_history()`가 `sess.transcripts` relationship 캐시(첫 호출 시 = 인사말 1개)만 반복 참조
- **Files changed**:
  - `backend/src/application/voice_session.py:482-505` — `_build_history()`가 `sess.transcripts` 대신 `self.db.query(models.Transcript).filter(session_id, is_final, role in user/assistant).order_by(id)` 직접 쿼리. relationship 캐시 우회.
- **Verification**:
  - 백엔드 재기동 → `voice_session` import OK, `/api/health` 200
  - 세션 73 DB 데이터로 검증: SQL로 같은 쿼리 돌리면 5 turn 모두 누적된 history (인사말·user·assistant 9개) 반환 — fix 후 동작과 동일
  - 새 통화에서 turn 3 이상에서 `llm.stream` input.history 길이 > 1 확인은 다음 사용자 통화에서 시각 검증
- **Status**: ✅ FIXED (회귀 가드 추가는 별도 — Transcript 직접 쿼리 단위 테스트 추후)
- **Fixed**: 2026-05-12 (iter 11)

### Fix #11 — TestPanel 상태 시인성 + 기본 모드 GCP (사용자 요청)

- **Area**: 2 (시각 일관성) + 7 (음성/통화 흐름)
- **Seed**: 자유 발견 — 사용자 직접 요청 ("마이크 활성화 시 하늘색", "기본을 GCP로")
- **Symptom**:
  - 우측 TestPanel에서 사용자가 발화 중인지(`listening`) 시각적으로 잘 안 보임. 동그라미 색은 있지만 라벨 텍스트는 항상 ink-100. "듣는 중" 문구도 운영 컨텍스트에 어색.
  - 기본 모드가 `browser`로 자동 선택돼 (Chrome SR 가능 시) → 실 운영(GCP TTS/STT)과 동작 차이. GCP 검증을 위해 수동 전환 필요.
- **Files changed**:
  - `frontend/src/components/TestPanel.tsx:420` — 상태 라벨에 state별 색상 (listening=sky, thinking=amber, speaking=emerald) + transition-colors
  - `frontend/src/components/TestPanel.tsx:503` — `stateLabel` "듣는 중" → "고객 발화중..."
  - `frontend/src/components/TestPanel.tsx:53` — 마운트 시 우선순위 변경: `voiceModeAvailable` 우선 → 'gcp', 아니면 SR 가능 시 'browser', 그것도 아니면 'text'
- **Verification**: tsc clean, `/bots/1/persona` 200, backend `voice_mode_available=true` 확인 (= 기본 GCP로 진입)
- **Status**: ✅ FIXED
- **Fixed**: 2026-05-12 (iter 10)

### Fix #10 — 브라우저 모드 echo 차단 시간 한국어 음절 속도에 맞게 보정

- **Area**: 7 (음성/통화 흐름)
- **Seed**: S5 (TestPanel echo 회귀 가능성)
- **Symptom**: 봇 발화가 끝나기 전에 fallback resume(setTimeout estimateMs+1500)이 트리거되면, 발화 잔향이 SR로 들어가 봇 자기 목소리를 사용자 발화로 인식할 위험.
- **Root cause**: `estimateMs = max(2500, text.length * 220)`. 한국어 음절당 220ms는 짧음 — 실측 TTS는 음절당 280~320ms. 긴 응답(예: 20자)일수록 추정과 실제 격차 커짐 (4.4s vs 5.7s).
- **Files changed**:
  - `frontend/src/components/TestPanel.tsx:295` — perChar 도입 (한국어 280, 그 외 100) + rate 1.05 보상. `text.length * 280 / 1.05` ≈ 음절당 267ms.
- **Verification**: tsc clean, `/bots/1/persona` 200, backend ok. echo 시각 검증은 브라우저 모드 직접 통화 필요(다음 사용자 테스트에서 회귀 확인).
- **Status**: ✅ FIXED (S5 차단 시간 보강. GCP 모드 echo는 voice_session VAD 동작 별도 — 추후)
- **Fixed**: 2026-05-12 (iter 9)

### Fix #9 — 콜 상세 빈 상태 일관성 (트랜스크립트 / 도구 호출)

- **Area**: 2 (시각 일관성) + 3 (빈 상태)
- **Seed**: 자유 발견
- **Symptom**: `/bots/N/calls/M` 트랜스크립트·도구 호출 탭의 빈 상태가 "한 줄 텍스트만" — 다른 페이지(/tenants, /tools, /knowledge, /skills, /mcp, /calls)는 모두 `아이콘 10x10 + 제목 + 부연 설명` 정형. 일관성 부족.
- **Root cause**: 빈 상태 UI 초기 작성 시 정형 미적용. 다크모드 색상도 누락.
- **Files changed**:
  - `frontend/src/app/bots/[botId]/calls/[sid]/page.tsx` — 두 빈 상태에 FileText / Wrench 10x10 아이콘 + 2단 메시지 + dark variant
- **Verification**: tsc clean, `/bots/1/calls/55` 200, backend ok
- **Status**: ✅ FIXED
- **Fixed**: 2026-05-12 (iter 8)

### Fix #8 — tools 인라인 createTool 에러 핸들링 + 성공 토스트

- **Area**: 1 (UI 상호작용) + 6 (데이터 흐름)
- **Seed**: S4 잔여 (toast 누락 — 마지막 인라인 create 분)
- **Symptom**: `/bots/N/tools`에서 "추가" 버튼 → prompt로 이름 → `api.post` 호출. 실패 시 try/catch 없어 silent crash, 성공 시 라우팅만 되고 피드백 없음. 또 빈 문자열 trim 검사 없음.
- **Root cause**: createTool에 try/catch + toast + name.trim 누락.
- **Files changed**:
  - `frontend/src/app/bots/[botId]/tools/page.tsx` — useToast import, name.trim() 가드, try/catch + 성공/실패 toast
- **Verification**: `/bots/1/tools` 200, tsc clean. 백엔드 죽어 재기동 후 `/api/health` ok 복귀.
- **Status**: ✅ FIXED — **S4 전체 5/6 페이지 완료** (잔여: flow/page.tsx는 그래프 인터랙션 별도 작업)
- **Fixed**: 2026-05-12 (iter 7)

### Fix #7 — Waterfall 행/막대 hover 시 native tooltip (kind·이름·offset·duration·error)

- **Area**: 8 (Waterfall/Trace 시각화)
- **Seed**: S2 (Waterfall 어색 — 정렬/색/막대/툴팁 중 "툴팁" 분)
- **Symptom**: 짧은 막대(폭 12% 미만)는 `fmtMs` 라벨이 가려져 클릭 후 우측 DetailPanel을 봐야 정보 확인 가능. 노드 비교가 번거로움.
- **Root cause**: 행/막대에 hover tooltip 없음. native `title` 속성만으로도 비용 0, 가독성 큼.
- **Files changed**:
  - `frontend/src/components/Waterfall.tsx` — 각 행 div에 `title={tooltip}` 추가. 4줄 multiline: `[kind] name / 시작 +Nms / 소요 Nms / 오류 첫 줄(있을 때)`
- **Verification**: tsc clean, `/bots/1/calls/55` 200 (Waterfall 렌더링되는 마지막 세션). hover 시 native tooltip 표시 — 추후 시각 검증.
- **Status**: ✅ FIXED (S2의 "툴팁" 부분. 잔여: 색·정렬·막대 가독성)
- **Fixed**: 2026-05-12 (iter 6)

### Fix #6 — /tenants 다크모드 색상 누락 + 빈 상태 일관성

- **Area**: 2 (시각 일관성) + 3 (빈 상태) — Area 1 연속 회피
- **Seed**: 자유 발견
- **Symptom**: `/tenants` 표가 다크모드에서 회색이 거의 안 보이고 hover/border 색상 누락. 빈 상태도 아이콘 없이 한 줄 텍스트만 — 다른 페이지(/bots/N/tools, /bots/N/calls 등)와 패턴 불일치.
- **Root cause**: 초기 작성 시 dark 변형 누락 + 빈 상태 UI 정형(아이콘+제목+설명)과 어긋남.
- **Files changed**:
  - `frontend/src/app/tenants/page.tsx` — thead/tbody/td/button에 dark variant + hover state 추가, 빈 상태에 Building2 10x10 아이콘 + 2단 메시지("아직 고객사가 없습니다." / "우측 상단 …" 안내)
- **Verification**: `/tenants` 200, tsc clean
- **Status**: ✅ FIXED
- **Fixed**: 2026-05-12 (iter 5)

### Fix #5 — agents 페이지 alert → toast 일관성 + 생성 성공 토스트

- **Area**: 1 (UI 상호작용)
- **Seed**: S4 (잔여 분량 — Fix #4 후속)
- **Symptom**: `/agents` 새 에이전트 생성에서 4 가지 케이스가 `alert()`로 처리됨 — 모달 다이얼로그가 워크플로우를 끊고 토스트 패턴 불일치. 생성 성공 시 토스트도 없음.
- **Root cause**: `useToast` 미사용. (4) "고객사 없음", "이름 입력 안 함", "생성 실패", 그리고 (성공 시 토스트 누락).
- **Files changed**:
  - `frontend/src/app/agents/page.tsx` — useToast import, 4 alert → toast (error/error/error + 신규 success "에이전트 N 생성됨")
- **Verification**: `/agents` 200, tsc clean
- **Status**: ✅ FIXED (S4 잔여 = flow / tools 인라인 create 2개 남음)
- **Fixed**: 2026-05-12 (iter 4)

### Fix #4 — 저장 후 토스트 누락 페이지 3곳 채움 (env / tools[id] / mcp)

- **Area**: 1 (UI 상호작용) + 6 (데이터 흐름)
- **Seed**: S4 — 폼 저장 후 토스트/피드백 없음
- **Symptom**: 환경변수·도구 편집·MCP 서버 설정 페이지에서 save 후 화면 변화 없음(dirty가 사라지지만 아무 표시 없음). 성공인지 실패인지 불명. settings/persona/callbot-agents는 이미 toast 있는데 패턴 불일치.
- **Root cause**: `save()`에 `try/catch + useToast` 패턴 누락. fetch 응답 .ok 체크도 없어 4xx 응답이 silent로 dirty=false 됨.
- **Files changed**:
  - `frontend/src/app/bots/[botId]/env/page.tsx` — useToast, fetch.ok 체크, success/error toast
  - `frontend/src/app/bots/[botId]/tools/[toolId]/page.tsx` — save/remove 둘 다 try/catch + toast
  - `frontend/src/app/bots/[botId]/mcp/page.tsx` — saveServer try/catch + create/update 구분 메시지
- **Verification**: `/bots/1/env` 200, `/bots/1/mcp` 200, `/bots/1/tools/11` 200, tsc clean
- **Status**: ✅ FIXED (Seed S4 6개 페이지 중 3개. 나머지: flow/page.tsx, agents/page.tsx, tools/page.tsx 인라인 create — 다음 iter)
- **Fixed**: 2026-05-12 (iter 3)

### Fix #3 — 메인 봇 페르소나 페이지에 통화 일관 설정 + 워크플로우 그래프 흡수 (IA 통합)

- **Area**: 1 (UI 상호작용) + 6 (데이터 흐름)
- **Seed**: 사용자 보고 — "메인이 여행 상담 콜봇이야. 통화 일관 설정 이런거 다 메인으로 들어와야해" + "플로우 에이전트들은 노드 그래프로 연결, 메인 워크플로우 시각화"
- **Symptom**: 페르소나 페이지에서 인사말/음성/언어/LLM이 비활성 + 별도 콜봇 페이지로 가야 편집 → 메인 사용자 입장에서 두 화면 왕복. 분기 워크플로우도 콜봇 페이지에만 있어 메인 편집 흐름과 단절.
- **Root cause**: CallbotAgent 컨테이너가 사용자 멘탈모델("콜봇 ≡ 메인 봇")과 어긋남. UI가 데이터 모델을 그대로 노출.
- **Files changed**:
  - `frontend/src/app/bots/[botId]/persona/page.tsx` — 메인일 때 통화 일관 설정 4필드 활성(`/api/callbot-agents/{cid}` PATCH) + BranchesFlowView 그래프 섹션 + 서브일 땐 모두 hide + 단독 Bot은 Bot PATCH로 유지
  - `frontend/src/app/callbot-agents/[id]/page.tsx` — 통화 일관 설정 섹션 제거 (메인 페이지로 흡수됨 안내만)
- **Verification**: `tsc --noEmit` 통과. 메인 페이지 한 화면에서 그래프(분기 드래그·트리거 편집) + 통화 설정 + 페르소나/system_prompt 동시 편집. CallbotAgent PATCH 후 SWR 무효화로 즉시 반영.
- **Status**: ✅ FIXED
- **Fixed**: 2026-05-11 (iter 2)

### Fix #2 — Agent type 전환 시 사이드바 즉시 미반영 (SWR 캐시 미동기화)

- **Area**: 6 (데이터 흐름)
- **Seed**: 사용자 질문 — "Flow agent 봇 단위 설정으로 바꿀 수 있게 어떻게 변경한다고 하지 않았나"
- **Symptom**: 페르소나/봇 설정 페이지에서 PROMPT↔FLOW 토글 → DB는 갱신되지만 사이드바 메뉴가 스킬↔Flow로 즉시 안 바뀜. 페이지 새로고침해야 적용.
- **Root cause**: settings/persona 페이지의 `mutate()`가 단일 봇 캐시(`/api/bots/${id}`)만 갱신. Sidebar는 `/api/bots` 리스트 캐시 사용 — 별도 SWR 키라 갱신 안 됨.
- **Files changed**:
  - `frontend/src/app/bots/[botId]/persona/page.tsx` — `useSWRConfig().mutate('/api/bots')` 추가
  - `frontend/src/app/bots/[botId]/settings/page.tsx` — 동일
- **Verification**: switchAgentType / save 후 `Promise.all([mutate(), globalMutate('/api/bots')])` 호출 — 사이드바 useSWR이 새 fetch 트리거.
- **Status**: ✅ FIXED
- **Fixed**: 2026-05-11 (iter 1)

---

## 정리 — FIX_LOOP 사용자 명시 종료 (2026-05-12)

- **종료 시각**: 2026-05-12 (사용자 "loop 종료해줘")
- **iter 진행**: 12회 (Fix #1 ~ #13, 단 #1~#2는 같은 iter)
- **Seed 표 최종**:

| ID  | 이슈                                       | Status |
|-----|------------------------------------------|--------|
| S1  | 보이스 셀렉터 변경이 통화에 적용 안 됨    | 🟢 Fix #3 |
| S2  | Waterfall 어색 (정렬/색/막대/툴팁)        | 🟡 Fix #7 (툴팁 완료, 색·막대 미진) |
| S3  | 사이드바 워크스페이스 selector dead UI    | ⚪ OPEN (조사 결과 dead onClick 없음 — 의미 모호로 미진행) |
| S4  | 폼 저장 후 토스트/피드백 없음             | 🟢 Fix #4 #5 #8 (5/6, 잔여 flow 그래프) |
| S5  | TestPanel echo 회귀 가능성                | 🟢 Fix #10 #13 (브라우저+GCP 양 모드) |

- **사용자 직접 보고 닫힌 큰 buggy**:
  - Fix #12 — history SQLAlchemy 캐시 회귀 (turn 누적 안 됨)
  - Fix #13 — GCP 발화 직후 echo grace
- **자유 발견 fix**: #6 /tenants 다크모드·빈상태, #9 콜 상세 빈상태, #11 TestPanel UI 강화

- **남은 작업** (다음 iter에 픽업하면 좋은 것):
  - S2 잔여: Waterfall 막대 색 대비·짧은 막대 가독성
  - S3: 사이드바 워크스페이스 UX 명확화 (단일 tenant ChevronDown 의미 등)
  - 세션 73 진단 후속: STT speech adaptation (도메인 어휘 힌트) + system_prompt 도구 사용 가이드 강화 (LLM이 사용자 의도 → 도구 매핑 적극)
  - Bot 단위 토스트 누락 잔여: `flow/page.tsx` 그래프 인터랙션

