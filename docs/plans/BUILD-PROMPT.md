# B2B Voice AI 플랫폼 — Build Prompt (vox 내재화 버전)

너는 시니어 풀스택 + AI 솔루션 아키텍트이자 음성 AI(콜봇) 플랫폼 설계 전문가다.

내가 제공하는 비전을 바탕으로 **B2B SaaS 음성 AI 플랫폼**을 처음부터 설계하고 다단계로 구현해줘.
참조 자료는 Vox (https://docs.tryvox.co), Vapi, LiveKit Agents 다.

---

# 배경

우리는 현재 **vox(매니지드 콜봇 플랫폼)를 사용 중**이고, 마이리얼트립 도메인의 **텍스트 챗봇 시스템**(FastAPI + LangGraph + PostgreSQL)을 별도로 운영하고 있다. 이 두 자산을 합쳐:

1. **vox를 내재화한다** — vox가 매니지드로 제공하는 콜봇 서버 기능(STT/TTS/스킬 런타임/지식/도구/빌더 UI/세션 로그)을 **우리가 직접 만들고 운영한다**
2. **B2B SaaS로 확장한다** — 여러 산업의 고객사가 가입해서 자기 도메인의 콜봇을 빌드/운영하는 플랫폼화

즉, **자체 호스팅 콜봇 플랫폼**을 만든다. vox를 그대로 따라가지 않고, 우리에게 맞게 차별화한다.

## 참조 플랫폼

| 플랫폼 | 학습 포인트 |
|---|---|
| **Vox** (tryvox.co) | 페르소나·스킬·지식·도구 4-요소 모델, content.md 기반 스킬 워크플로우, Frontdoor 라우팅 패턴 — *우리가 대체하려는 대상* |
| **Vapi** (vapi.ai) | 빠른 PoC UX, function call webhook 패턴, sub-600ms 광고 |
| **LiveKit Agents** | WebRTC 미디어 인프라(오픈소스 자체 호스팅), 토큰 stream pipeline, MCP 지원 — *Phase 2 media plane 선택지 중 하나* |
| **OpenAI Realtime / Gemini Live** | multimodal 단일 모델 패턴 — 향후 확장 옵션 |
| **Pipecat** | frame-based pipeline, 가장 넓은 벤더 매트릭스 |

## 차별점 (선택 — 1~2개에 집중)

| 차별 축 | 어떻게 |
|---|---|
| **한국어 + 도메인 특화** | 여행·금융·이커머스 산업별 템플릿·지식·도구 미리 제공 |
| **개발자 친화** | git 기반 스킬 버전 관리, code-first 옵션 |
| **데이터 통제** | 자체 호스팅 기본, 한국 데이터 거주성 보장 |
| **컴플라이언스** | 금융·의료 특화 (PCI · 통신비밀보호법 · KISA) |
| **워크플로우 표현력** | LangGraph 기반 정교한 분기 (Vox보다 표현력 ↑) |

---

# 목표

1. **B2B SaaS** — 여러 고객사가 가입 → 자기 도메인 콜봇을 빌드 → 자기 채널로 운영
2. **노코드/로우코드 빌더** — 스킬 작성·도구 등록·지식 업로드 (Vox echo 같은 UI)
3. **음성 인프라는 자체 통제** — MVP는 **WebSocket + Silero VAD**로 시작. Phase 2 이상에서 LiveKit OSS 자체 호스팅 또는 순수 WebRTC로 확장. **벤더 락인 회피가 핵심**
4. **Provider Adapter 패턴** — STT/LLM/TTS 벤더 교체 가능 (lock-in 방지). MVP는 GCP 통일 (Speech-to-Text / Gemini / Cloud TTS)
5. **Multi-tenant 데이터 격리** — 처음부터 설계 (나중에 추가 어려움)
6. **분당 과금** + 동시 통화 한도 + LLM/STT/TTS 외부 비용 패스스루
7. **콜봇 latency 1~2초** — 단일 LLM + 스킬 스왑 패턴

---

# 핵심 개념 (Vox 모델 차용 — 단, 우리가 직접 구현)

Vox docs (https://docs.tryvox.co) 분석 결과를 기반으로 한 자체 모델:

## 4-요소 모델 (Agent 구성)

| 요소 | 역할 | 우리 구현 |
|---|---|---|
| **Persona (페르소나)** | 봇 정체성·말투. Bot 당 1개 | Persona 엔티티 → 시스템 프롬프트 앞단 |
| **Skill (스킬)** | 특정 의도 처리 워크플로우. Bot 당 N개. content.md로 정의 | Skill 엔티티(markdown content) + Frontdoor 라우팅 |
| **Knowledge (지식)** | RAG 참조 문서. Bot에 연결 | Knowledge 엔티티. MVP는 인라인, Phase 2 pgvector |
| **Tool (도구)** | 함수 호출 (built-in + API tool) | Tool 엔티티. MVP는 built-in handover/end_call만 |

## 단일 LLM + 스킬 스왑 패턴 (Vox Echo)

```
[ 단일 LLM 두뇌 ]
    + 페르소나 (고정)
    + 활성 Skill 1개 (동적 교체)
    + 관련 지식 (조건부 RAG)
    + 사용 가능 도구 (스킬에 따라)

→ 매 턴 LLM 호출 1번 (라우팅 비용 0)
→ 스킬 격리 (변경 영향 범위 작음)
```

## 스킬 워크플로우 (content.md 구조 표준)

각 스킬은 markdown 파일로 정의. 표준 섹션:

```markdown
# {스킬명}

## 언제 사용 (Lifecycle)
- must open before/after ...
- open once at session start / always available
- never open again

## 사용 컨텍스트 (Pre-injected Variables)
- context.xxx: 설명

## 하드룰 (MUST / NEVER)
- ...

## 흐름 (Steps)
- Step 1
- Step 2

## 종료 조건 (Exit)
- 다음 Skill 호출
- 종료
- 에스컬레이션
```

## Flow Agent vs Prompt Agent

- **Prompt Agent**: 단일 큰 prompt — 간단 FAQ
- **Flow Agent**: 노드 그래프 (시작·대화·조건·추출·API·종료) — 복잡 분기

→ Skill 안에서 두 패턴 다 지원. MVP는 Prompt만, Phase 2에서 Flow 추가.

---

# 음성 미디어 운반(media plane) 선택지

**핵심 원칙: media plane은 단계별 선택. LiveKit은 필수가 아니라 선택지 중 하나.**

| 단계 | 추천 | 이유 |
|---|---|---|
| MVP (브라우저 1:1 테스트) | WebSocket + AudioWorklet + Silero VAD | 의존성 최소. 디버깅 쉬움. vox 두뇌 부분 구현에 집중 가능 |
| Phase 2 (운영급 full-duplex) | LiveKit OSS 자체 호스팅 (a) 또는 WebSocket 스트리밍 강화 (b) | (a)는 VAD/turn-taking primitives 무료. (b)는 종속 최소. 운영 부담과 정밀도 trade-off |
| Phase 3 (실제 전화 PSTN) | LiveKit SIP / Twilio SIP 트렁크 | SIP 게이트웨이는 어떤 형태로든 필요 |

**MVP에서 LiveKit 도입 금지** — 두뇌 구현에 시간 쓰자. vox 내재화의 본질은 음성 인프라가 아니라 스킬/지식/도구/관리 UI다.

---

# 해야 할 작업 (단계별)

## Phase 0 — 아키텍처 설계 (이미 완료)

산출물: `docs/plans/VOX_INSOURCING_DESIGN.md`

여기에 포함된 내용:
1. vox 책임 영역 분해
2. chatbot-v2 재사용 vs 신규 개발 매트릭스
3. 자체 구축 음성 콜봇 컴포넌트 다이어그램
4. media plane 선택지 비교
5. 데이터 모델 + API 설계 + WebSocket 음성 프로토콜
6. Phase 로드맵

## Phase 1 — Backend + Frontend MVP (지금)

### Backend 디렉토리 구조 (Clean Architecture — chatbot-v2 답습)

```
backend/
├── pyproject.toml
├── .env.example
├── README.md
├── main.py
└── src/
    ├── app.py                       # create_app
    ├── core/                        # config, logging
    ├── domain/                      # entities, ports, prompts (순수)
    ├── application/                 # voice_session, skill_runtime, tool_runtime
    ├── infrastructure/              # db, models, adapters/{stt,tts,llm,vad}
    └── api/
        ├── routers/                 # tenants/bots/skills/knowledge/tools/calls/transcripts
        ├── ws/voice.py              # WebSocket /ws/calls/{id}
        └── static/                  # admin console (HTML/CSS/JS + AudioWorklet)
```

### MVP 구현 항목

- Multi-tenant 모델 (Tenant·User·Bot)
- Skill Loader: markdown content → 런타임 LLM prompt
- Frontdoor 진입 + 스킬 전환 신호 (LLM 응답 JSON `{"next_skill": "..."}` 파싱)
- Tool Registry + dynamic invocation (MVP: end_call, handover_to_human만)
- Knowledge: 텍스트 인라인 (MVP). pgvector는 Phase 2
- Voice Session Orchestrator: idle/listening/thinking/speaking 상태 머신
- Silero VAD 어댑터
- GCP STT streaming 어댑터
- Gemini LLM 어댑터
- GCP TTS 어댑터
- WebSocket `/ws/calls/{id}`: 바이너리 PCM + JSON 컨트롤
- 어드민 콘솔: 대시보드/봇/봇 편집/테스트 콜/통화 로그
- 시드 데이터: 마이리얼트립 데모 봇 + 스킬 3 + 지식 2
- Mock 어댑터 fallback: env에 GCP 키 없으면 echo로 동작

## Phase 2 — 운영 기반 (3주)

- 관측성: per-call trace (Grafana / DataDog), audio quality 메트릭
- pgvector RAG 정식화
- 도구 API 호출 본격화 (입력 스키마 검증, HMAC)
- 통화 후 분석/요약/추출 잡
- 빌링: 분당 과금 ledger, 동시 통화 한도 enforcement
- 에러 처리: 통화 끊김·STT 실패·LLM timeout
- 보안: API key, 통화 녹음 동의 멘트, PII 마스킹
- media plane 결정: WebSocket 확장 vs LiveKit OSS 도입

## Phase 3 — 텔레포니 + 셀프 서비스 (6주)

- SIP/PSTN 연동 (LiveKit SIP 또는 Twilio SIP 트렁크)
- 신규 고객사 가입 → onboarding wizard
- 빌링 대시보드
- 템플릿 마켓플레이스 (산업별 starter pack)
- 캠페인 발신 / DTMF / 통화 전환 / 녹취

---

# 음성 응답 설계 원칙 (콜봇 특화)

코드보다 정책 — 모든 스킬에 적용:

- **응답 길이 제한**: 1~2문장 (15~30단어). 길면 끊고 "더 알려드릴까요?"
- **마크다운 / 이모지 / URL 금지** (URL은 "문자로 보내드릴게요")
- **리스트 / 불릿 금지** — "첫째, 둘째" 자연 전환
- **숫자 / 날짜 발음 친화** — "FTU4T6" → "에프-티-유-사-티-육"
- **확인 패턴** — 중요 정보 복창
- **대화체** — "~해드릴 수 있습니다" → "도와드릴게요"
- **Filler 음성** — 응답 지연 시 "잠시만요" 미리 재생
- **에러 회복** — "잘 못 들었어요, 다시 말씀해주실래요?"

---

# 제공해야 할 산출물

각 Phase 마다:

1. **다이어그램**: Mermaid (아키텍처, ERD, 시퀀스, 상태 흐름)
2. **ADR 문서**: 핵심 결정 기록 (이미 VOX_INSOURCING_DESIGN.md에 일부 포함)
3. **API 스펙**: OpenAPI YAML
4. **핵심 코드**: 실행 가능한 모듈 (테스트 포함)
5. **README**: 로컬 실행·배포·온보딩
6. **운영 가이드**: 새 고객사 추가 절차, 새 스킬 작성 가이드

코드 품질:
- Type hints (Python) / TypeScript strict
- pytest / Jest 단위 + 통합 테스트
- ruff / eslint / prettier
- 의존성 주입 (Clean Architecture)

---

# 제약

- **MVP에 LiveKit/SIP 도입 금지** — vox 두뇌 구현에 집중. 음성 미디어는 WebSocket으로 충분
- **벤더 락인 회피** — STT/LLM/TTS Adapter 패턴. 단, MVP는 GCP 통일
- **첫 MVP에 multi-LLM 금지** — Gemini 1개로 시작, 검증 후 adapter 확장
- **첫 MVP에 multi-tenant 검증 필수** — 1개 테넌트로만 만들면 나중에 못 분리
- **데이터 거주성** — 한국 내 호스팅 옵션 (KISA 인증 가능 구조)
- **PII 처리** — 통화 녹음/transcript의 자동 마스킹 layer 처음부터 포함

---

# Vox docs 참고 페이지

빌드 시 Vox 모델 학습 자료:

- [Overview](https://docs.tryvox.co/docs/start/overview) — Prompt vs Flow Agent 비교
- [Flow Overview](https://docs.tryvox.co/docs/build/flow/overview) — 노드 종류 (시작·대화·조건·추출·API·종료)
- [Tools Overview](https://docs.tryvox.co/docs/build/tools/overview) — Built-in vs API 도구
- [Knowledge Overview](https://docs.tryvox.co/docs/build/knowledge/overview) — Chunking/Embedding/Vector DB + 토큰 크기별 RAG 토글
- [Docs Index](https://docs.tryvox.co/llms.txt)

---

# 출력 순서 (이 prompt 받으면)

1. **이해 확인** — 비전·차별점·MVP 범위에 대한 너의 해석 한 페이지
2. **Phase 0 검토** — `VOX_INSOURCING_DESIGN.md` 읽고 추가 의사결정 필요 사항 1페이지
3. **Phase 1 시작** — 백엔드 디렉토리 scaffolding + 핵심 모듈 1~2개 (Tenant·Skill Loader 등) → 사용자 검토
4. ... 단계별로 진행, 매 단계마다 사용자 검토 요청

너무 큰 단위로 작업하지 말고 **단계별 review 받으며 진행**. 매 phase 끝에 다음 phase 진입 전 의사결정 포인트 정리.

---

# 추가 가이드라인

- **너무 일반론 X** — 구체적 코드·구조·결정
- **마이리얼트립 도메인을 첫 anchor 고객으로 가정** — 스킬은 항공/숙소/투어 기반 시작
- **"왜 그렇게 결정했는지" 모든 ADR에 명시** — Vox 따라할지 다르게 갈지 명확화
- **Vox가 잘하는 건 따라하고, 잘 못하는 부분에서 차별** — 처음부터 너무 reinvent 금지
- **콜봇 latency가 1번 우선순위** — 모든 결정 시 "이게 1~2초 안에 응답 가능한가" 자문
- **media plane 결정 미루기** — MVP는 WebSocket. Phase 2 진입 시점에 LiveKit OSS / aiortc / WebSocket 강화 중 결정

이제 시작해줘. Phase 1부터 단계적으로 진행하고, 각 단계 끝에 내 검토 받아.
