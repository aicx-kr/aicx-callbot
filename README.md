# aicx-callbot

B2B 콜봇 SaaS 플랫폼. 한 통화에 메인 1명 + 서브 N명의 봇이 협업하고, 운영자는 콘솔에서 자산(페르소나·스킬·지식·도구)을 편집해 고객사별 콜봇을 만든다.

> 상세 구조: [`docs/plans/CALLBOT_STRUCTURE_OVERVIEW.pdf`](docs/plans/CALLBOT_STRUCTURE_OVERVIEW.pdf) 한 페이지 요약 / [`docs/plans/VOX_AGENT_STRUCTURE.md`](docs/plans/VOX_AGENT_STRUCTURE.md) 상세 정의

**상태**: MVP — 백엔드/프론트엔드 모두 동작. GCP key 있으면 음성 모드(GCP STT/TTS) 활성, 없으면 텍스트·브라우저 SR 모드 자동 fallback.
**첫 anchor 고객**: 마이리얼트립 (여행 — 항공·숙소·투어 예약 조회/변경·환불).

---

## 디렉토리 맵

```
aicx-callbot/
├── backend/             FastAPI + SQLAlchemy 2.0 + SQLite (port 8765)
│   ├── src/
│   │   ├── domain/          ① 비즈니스 규칙 (entity·invariant·port)
│   │   ├── application/     ② 서비스·통화 오케스트레이션·tool runtime
│   │   ├── infrastructure/  ③ DB·GCP·Gemini 어댑터·repository
│   │   ├── api/             ④ FastAPI 라우터·WebSocket
│   │   └── core/            설정
│   ├── tests/               pytest 단위 테스트
│   └── scripts/             smoke·e2e
├── frontend/            Next.js 15 + React 19 + Tailwind + SWR (port 3000)
│   └── src/
│       ├── app/             App Router 페이지
│       ├── components/      재사용 UI (Sidebar / TestPanel / Waterfall ...)
│       └── lib/             api·types·voice-options
├── docs/plans/          설계·로그 문서 (구조, AUTO_LOOP_LOG, FIX_LOG 등)
└── scripts/             공통 smoke·verify
```

각 디렉토리에 `README.md`가 있어 폴더 안에서 무엇을 다루는지 짧게 안내합니다.

---

## 핵심 모델 한 페이지

```
Tenant (고객사)
  └─ CallbotAgent (통화 단위 컨테이너)
       ├─ 통화 일관 설정: voice·greeting·language·llm_model·pronunciation·DTMF
       ├─ global_rules: 매 turn 첫 단계 dispatcher (handover/end_call/transfer)
       └─ CallbotMembership (역할: main 1 + sub N)
            └─ Bot (자산 보관소)
                 ├─ Persona / system_prompt / voice_rules
                 ├─ Skill / Knowledge / Tool / MCPServer
                 └─ env_vars (API 토큰 등)
```

- **메인 봇 ≡ 콜봇 그 자체** (UI 단일화) — `/bots/{mainBotId}/persona`에 통화 일관 설정 + 워크플로우 그래프 + 페르소나 한 화면
- **서브 봇** = 환불·결제·외국어 등 특정 절차 전문, 핸드오프로 진입 (인사말 불필요)

---

## 통화 흐름 (한 발화 처리)

```
사용자 발화 → STT → ① 글로벌 규칙 dispatcher → ② 현재 활성 봇 실행
                                                  ├─ LLM streaming (Gemini)
                                                  ├─ 문장 단위 TTS streaming (Google Neural2)
                                                  └─ 도구 호출 (REST / MCP / builtin)
                                              → 핸드오프 시 다음 활성 봇 갱신
```

직렬 → 파이프라인 최적화로 첫 음성까지 ~2초 (`prefetch_runtime` + `llm.stream` + `tts.s0~sN`).

---

## 빠른 시작

### Backend (port 8765)

```bash
cd backend
# .env 파일 준비
#   GOOGLE_SERVICE_ACCOUNT_BASE64=<base64 SA>  또는
#   GOOGLE_APPLICATION_CREDENTIALS=<file path>
PORT=8765 ./run.sh
# → http://localhost:8765/api/health 200 + voice_mode_available=true
```

### Frontend (port 3000)

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000 → 첫 콜봇 메인 페르소나로 자동 진입
```

### 테스트 통화

`/bots/1/persona` → 우측 TestPanel:
- 모드: 음성 (GCP) / 음성 (브라우저) / 텍스트
- **VARS** 토글로 통화 시작 시 `dynamic_vars` 주입 (`userId=4002532`, `phone=01082283421` 등)
- **시작** 누르고 발화

---

## 사용 모델

| 종류 | 기본 | 어댑터 |
|---|---|---|
| LLM | `gemini-3.1-flash-lite` | `backend/src/infrastructure/adapters/gemini_llm.py` (streaming + function calling) |
| STT | Google Cloud Speech-to-Text v1 streaming, LINEAR16 16kHz | `google_stt.py` |
| TTS | Google Cloud TTS Neural2 (`ko-KR-Neural2-A` 기본) | `google_tts.py` |
| VAD | Silero VAD | `silero_vad.py` |

콜봇 컨테이너 단위로 voice/언어/LLM 모델 변경 가능 (콘솔 `/bots/{mainBotId}/persona`).

---

## 개발 참여

[`CONTRIBUTING.md`](CONTRIBUTING.md) 필독 — **Clean Architecture 4층 룰** + 고객사 확장성 가이드라인.

- 새 도메인 추가: domain → repository port → repository 구현 → service → router 5단계
- 새 fix는 `docs/plans/FIX_LOG.md`에 ONE iteration = ONE fix 룰로 누적
- 자율 개선 사이클은 `docs/plans/AUTO_LOOP_LOG.md`에 카테고리(테스트·성능/UI/구조) 로테이션
