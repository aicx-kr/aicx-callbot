# callbot-platform 어색함 점검 로그

> `/loop REVIEW_LOOP_PROMPT.md` 가 iteration마다 한 finding씩 append.
> 시작: 2026-05-11

## Findings

### Finding #1 — LLM 호출 시그니처에 대화 히스토리 인자 없음 (turn 간 컨텍스트 망각) ✅ FIXED (iter 2)
- **Status**: 2026-05-11 수정 완료. `LLMPort.generate(..., history=[ChatMessage])` 추가, Gemini 어댑터에서 content list 변환, voice_session에서 `_build_history` (최근 12 turn) 자동 첨부. 다중 turn 테스트 통과 ("환불 도와줘" → "그러면 시간 얼마나 걸려?" → "환불 절차" 답변 — 이전 문맥 유지).
- **Area**: C — 백엔드 도메인/애플리케이션 레이어
- **Files**:
  - `backend/src/domain/ports.py:47` — `LLMPort.generate(system_prompt, user_text, model)` 시그니처에 messages/history 없음
  - `backend/src/infrastructure/adapters/gemini_llm.py:19` — 어댑터도 동일 시그니처
  - `backend/src/application/voice_session.py:216` — 매 turn `system_prompt + 현재 user_text`만 LLM에 전달
  - `backend/src/application/voice_session.py:343` — followup LLM 호출도 동일 (tool 결과 후 자연어 응답)
- **Awkwardness**:
  매 turn 봇이 "첫 turn처럼" 행동한다. 실제 통화 로그 예시:
    `사용자: "환불" → 봇: 스킬 전환 + 환불 정책 안내`
    `사용자: "예약 번호 모르겠는데" → 봇: handover 안내`
    `사용자: "도와줘" → 봇: "안녕하세요, 마이리얼트립 여행 상담 콜봇입니다…"` ← **인사말 반복**
  Gemini가 이전 turn을 모르기 때문에 매 호출이 cold start. 대화의 연속성이 깨진다.
- **Why it matters**:
  콜봇의 핵심 가치인 "자연스러운 다중 turn 대화"가 동작하지 않는다. 사용자가 후속 발화에서 앞 turn을 참조하면 ("그러면 그 환불은 얼마야?") 봇이 무엇을 가리키는지 모름.
- **Proposed fix**:
  옵션 1: `LLMPort.generate` 시그니처에 `history: list[Message]` 추가. Message = `{role: 'user'|'assistant', text: str}`. voice_session 이 transcript에서 final 메시지들을 추출해 전달.
  옵션 2: `Conversation` 도메인 객체로 더 풍부하게 (turn마다 metadata 포함) — Phase 2.
  Gemini SDK는 `model.start_chat(history=[...])` 또는 `generate_content([Content...])` 패턴 지원. 어댑터에서 transcript → Gemini Content 변환.
- **Effort**: S (시그니처 변경 + Gemini 어댑터 + voice_session 한 곳, 1~2시간)
- **Found**: 2026-05-11 (iteration 1)

### Finding #2 — Waterfall tick 라벨 겹침 + 막대 미니화 (시간축 영역이 좁음)
- **Area**: B — 프론트엔드 UI/UX
- **Files**:
  - `frontend/src/components/Waterfall.tsx:18` — `grid-cols-1 xl:grid-cols-[1fr_360px]` — Detail panel이 1280px 이상에서만 옆 배치, 그 미만에서도 사용자 화면이 좁으면 시간축 압축
  - `frontend/src/components/Waterfall.tsx:226-237` — `makeTicks()` step 결정 (totalMs>30s → 5s 간격으로 9개 tick)
  - `frontend/src/app/bots/[botId]/calls/[sid]/page.tsx` — 상위 wrapper `max-w-[1200px]` (사이드바 260 + 우측 테스트패널 420 빼면 좌측 컬럼 220 + 시간축 ~200px = 매우 좁음)
- **Awkwardness**:
  사용자가 실제 본 화면 (총 44.96s, 20개 노드): tick 라벨이 `0  5s10s15s20s25s30s35s40s` 형태로 거의 겹쳐 보이고, 4초짜리 LLM 호출 막대가 시간축 폭의 5% 정도만 차지해 미니 정사각형으로만 보임. waterfall의 본래 목적(어디서 시간이 가는지)이 시각적으로 안 보임.
- **Why it matters**:
  Waterfall은 latency 디버깅의 핵심 도구인데, 시간축이 좁으면 LLM 1.3s vs TTS 2.1s 같은 비교가 안 됨. 사용자가 LangSmith 스크린샷을 참고로 줬을 때 기대한 가로 펼침과 한참 다름.
- **Proposed fix**:
  옵션 1 (즉시): tick step 더 보수적으로 — totalMs>30s면 10s 간격(5개 tick), >60s면 20s. 라벨 가독성 회복.
  옵션 2 (구조): Call detail 페이지에서 테스트 패널 자동 접기 또는 Waterfall만 전체 폭 사용 (`max-w-full`로 풀고 사이드바 외 전부 캔버스). Detail panel은 아래로 스택.
  옵션 3 (인터랙션): 가로 zoom/pan 컨트롤 + minimap (현재 minimap 있음). zoom 기본 fit-to-content.
  → 옵션 1+2 같이 권장. 옵션 3는 부가.
- **Effort**: S (Waterfall.tsx + page.tsx 폭, 30~60분)
- **Found**: 2026-05-11 (iteration 2)

### Finding #3 — MCP 서버 통합 미구현 (도구 발견·호출 외부 위임 불가) ✅ FIXED → 🔄 SUPERSEDED (iter 3)
- **Status**: MCP 서버 추상으로 구현했으나 운영자에게 추상이 한 단계 더 있어 어색. 사용자 피드백으로 **방향 전환**: aicx-plugins-mcp의 8개 도구를 우리 일반 Tool로 직접 시드 (REST type). 사이드바 MCP 메뉴 제거. 운영자는 도구 페이지 한 곳에서 모든 도구를 관리.
  - 시드된 도구: lookup_user_by_identifier, lookup_user_by_user_id, get_reservation, get_flight_by_pnr, get_refund_fee, get_accommodation, get_tna_product, create_zendesk_ticket (총 8개 + builtin 2 = 10개)
  - 환경변수 키: MRT_CS_API_BASE, API_TOKEN, ZENDESK_API_BASE, ZENDESK_AUTH (.env.example 추가)
  - MCPServer 모델/페이지/클라이언트 코드는 보존됨 (deep link로 접근 가능). 향후 외부 자체 MCP 서버 자유 등록 시 활용 가능.
- **Area**: E — 변수 컨텍스트 / 도구 / 지식 통합
- **Files**:
  - `backend/src/infrastructure/models.py` — Tool 모델 있으나 외부 MCP 서버 등록 entity 없음
  - `backend/src/application/tool_runtime.py` — builtin/rest/api 타입만, MCP 호출 분기 없음
  - `backend/src/application/skill_runtime.py` — build_runtime에서 봇 Tool만 LLM에 노출
- **Awkwardness**:
  사용자는 `aicx-plugins-mcp` 같은 사내 MCP 서버에 정의된 8개 도구(`get_reservation`, `get_refund_fee`, `lookup_user_by_phone` 등)를 즉시 활용하고 싶지만, 우리 플랫폼은 도구를 봇별로 우리 DB에 일일이 등록해야만 사용 가능. MCP는 표준 프로토콜이므로 한 번 base_url+tenant_id 등록으로 N개 도구 자동 발견되어야 자연스러움.
- **Why it matters**:
  고객사가 이미 자체 도메인 API를 MCP 서버로 노출했을 때, 그걸 우리 콜봇에 붙이는 비용이 너무 큼 (도구마다 수동 등록). 진짜 vox/agent 플랫폼 수준이 되려면 MCP가 1급.
- **Proposed fix** (이번 iter에 적용):
  1. `MCPServer` 엔티티: `bot_id, name, base_url, mcp_tenant_id, auth_header, is_enabled`
  2. `mcp_client.py`: JSON-RPC 2.0 over HTTP (`tools/list`, `tools/call`)
  3. CRUD 라우터 `/api/mcp_servers`
  4. `skill_runtime.build_runtime`: MCP 서버에서 도구 list → 시스템 프롬프트의 "사용 가능한 도구" 섹션에 합성
  5. `voice_session._handle_tool_signal`: DB 도구에 없으면 MCP 서버로 proxy
  6. Frontend: 사이드바 "MCP 서버" + 등록/발견 페이지
- **Effort**: M (~3시간 — 백엔드 + 프론트 풀세트)
- **Found**: 2026-05-11 (iteration 3)

### Finding #4 — Flow Agent 봇의 실행 엔진 미구현 (데이터만 있고 런타임 비어있음)
- **Area**: A — 프롬프트 ↔ 플로우 에이전트 통합
- **Files**:
  - `backend/src/infrastructure/models.py:46-49` — Bot.agent_type / Bot.graph 필드 있음
  - `backend/src/application/voice_session.py:start` — `build_runtime()` 항상 호출, agent_type 분기 없음
  - `backend/src/application/skill_runtime.py` — Skill 기반 프롬프트 합성만 지원
- **Awkwardness**:
  Bot 설정에서 `agent_type='flow'`로 전환 + Flow 페이지에서 그래프를 그려도, 통화 시작 시 백엔드는 여전히 Skill/Persona 합성으로만 LLM 호출. 그래프가 실제로 실행되지 않음. 사용자는 "Flow Agent 봇"을 만들어도 동작이 Prompt Agent와 동일하다고 느낌.
- **Why it matters**:
  Flow 모드 UI는 vox 수준이지만 백엔드가 실행 못 함. "그래프 빌더는 있지만 그래프대로 안 굴러감" 상태 — 사용자가 그래프 그리는 노력이 무의미.
- **Proposed fix**:
  새 모듈 `application/flow_runtime.py`:
  - GraphState (active_node_id, variables: VariableContext)
  - turn마다 현재 노드 실행 (kind별 분기): begin/conversation/extraction/condition/api/tool/transfer/end/global
  - 각 노드 처리 → edges 평가 → 다음 노드 결정
  - voice_session에서 `if bot.agent_type=='flow': flow_runtime.handle_turn(...)` else 기존 경로
- **Effort**: L (4~6시간 — 그래프 실행 엔진은 처음 만드는 게 핵심 작업)
- **Found**: 2026-05-11 (iteration 4) — 미수정

### Finding #5 — 테스트 패널에 turn별 latency/cost 미표시 (vox에는 있음)
- **Area**: D — 테스트 패널 & 라이브 통화 UX
- **Files**:
  - `frontend/src/components/TestPanel.tsx` — Bubble 컴포넌트가 텍스트만 표시, 메타 없음
  - vox 스크린샷에서 본 형식: `6.0s · 1 turns · $0.28`
- **Awkwardness**:
  통화 중 봇 응답이 얼마 걸렸는지(LLM+TTS), 토큰/비용은 얼마였는지 testPanel에서 즉시 안 보임. waterfall 페이지에서 통화 종료 후 확인은 가능하지만 실시간 디버깅에 부족. vox echo는 각 turn 응답에 latency·cost를 인라인으로 표시.
- **Why it matters**:
  스킬·프롬프트 튜닝 중 "이 응답이 왜 느릴까", "이 답변 한 번에 얼마야"를 즉시 봐야 빠르게 반복 가능. 통화 끝나야 waterfall에서 확인은 느림.
- **Proposed fix**:
  - 백엔드: assistant transcript 송신 시 `latency_ms`, `tokens_in`, `tokens_out`, `cost_usd` 메타 함께 보냄 (Gemini는 `response.usage_metadata`로 토큰 수 확인 가능, cost는 모델별 단가 매핑)
  - 프론트: Bubble 우하단에 `1.42s · 234↑/89↓ · $0.0012` 작게 표시
- **Effort**: M (~2시간 — Gemini usage_metadata 파싱 + 단가 테이블 + WS 메시지 + UI)
- **Found**: 2026-05-11 (iteration 4) — 미수정

### Finding #6 — 워크스페이스 선택기 dead UI (멀티테넌트 전환 동작 안 함)
- **Area**: F — 어드민 어포던스
- **Files**:
  - `frontend/src/components/Sidebar.tsx:38-47` — 워크스페이스 selector 버튼이 시각적으로만 있고 onClick 없음
  - tenant CRUD는 `/tenants` 페이지에 있으나 사이드바 selector와 무관
- **Awkwardness**:
  사이드바 상단의 "AICX, vox.ai 공동 워..." 같은 워크스페이스 영역이 마치 셀렉터처럼 ChevronDown 아이콘과 함께 있는데, **클릭해도 아무 일 안 일어남**. 운영자가 여러 고객사(테넌트) 사이를 어떻게 전환하는지 UX 자체가 막혀 있음.
- **Why it matters**:
  B2B SaaS의 핵심은 멀티테넌트. 운영자가 고객사 A 봇과 B 봇을 자유롭게 오가야 하는데 그 흐름이 없음. 현재는 `/tenants` 페이지에서 봇 목록 → 클릭 패턴으로만 가능 (사이드바와 분리).
- **Proposed fix**:
  - 워크스페이스 셀렉터 클릭 → 드롭다운 또는 모달 → 등록된 tenant 리스트 + 각 tenant의 봇들 → 봇 선택 시 `/bots/{id}/persona`로 라우팅
  - 또는 사이드바 상단의 헤더에 봇 선택기 추가 (현재는 페이지 헤더에만 있음)
- **Effort**: S (~1시간 — 드롭다운 UI + tenant→bots 매핑)
- **Found**: 2026-05-11 (iteration 4) — 미수정

---

## 정리 (Triage)

종료 조건 충족: Findings 6개 + 모든 영역(A~F) 1회 이상 커버.

### P0 (콜봇 기능 자체에 영향)
- **#4** Flow Agent 실행 엔진 — 그래프 그려도 안 굴러감 (L)
- (#1, #2, #3 모두 fixed)

### P1 (운영자 UX 개선)
- **#5** TestPanel latency/cost (M)
- **#6** 워크스페이스 selector dead UI (S)

### P2 (이미 fixed, 회귀 모니터링)
- #1 대화 히스토리 — multi-turn 시나리오 회귀 테스트 정기
- #2 Waterfall 좁은 화면 회귀
- #3 MCP/도구 정책 변경 시 시드 일관성

### 권장
- 다음 작업 우선순위: **#6 (S, 빠른 이김) → #5 (M, 운영 가치 큼) → #4 (L, 본격적)**
- loop 자연 종료. 다음 finding은 새 점검 사이클에서.
