너는 시니어 AI 솔루션 아키텍트이자 B2B Voice AI 플랫폼 설계 전문가다.

내가 제공하는 기존 챗봇 레포지토리와 `vox` 매니지드 콜봇 플랫폼(`https://docs.tryvox.co`)을 참고해서,
**vox를 내재화한 B2B 고객사 확장 가능한 콜봇 플랫폼**을 설계해줘.

# 목표

우리는 현재 vox를 매니지드로 사용하면서, 동시에 기존 챗봇 시스템도 운영 중이다.
이 두 자산을 합쳐 **vox 종속을 끊고 자체 호스팅 콜봇 플랫폼**을 만들고 싶다.

단순 음성 챗봇이 아니라 B2B 고객사가 사용할 수 있는 콜봇 플랫폼이어야 하며,
고객사별 설정/시나리오/상담 흐름/지식베이스/통화 로그/운영 관리가 가능해야 한다.

# 참고 대상

아래를 반드시 분석해줘.

1. 기존 챗봇 레포지토리(chatbot-v2) — 재사용 가능한 도메인 자산
2. vox docs (`https://docs.tryvox.co`) — 현재 매니지드로 제공받는 콜봇 기능
3. 현재 코드에서 재사용 가능한 구조 (LLM/RAG/Prompt/Tenant/Webhook)
4. **media plane 선택지** (LiveKit OSS, WebRTC, WebSocket) — LiveKit은 필수가 아니라 선택지

# 핵심 전제

콜봇은 챗봇과 다르게 단순 request/response 구조가 아니라,
실시간 음성 스트리밍 기반 시스템이다.

따라서 아래 구조를 중심으로 설계해줘.

```
User / Phone / Web Client
→ Media plane (WebSocket(MVP) / WebRTC(Phase2) / SIP(Phase3))
→ Voice Agent Backend
  → VAD (Silero)
  → STT (GCP Speech-to-Text)
  → LLM / Agent Logic (Gemini + Skill Runtime)
  → Tool / RAG / Business Logic
  → TTS (GCP Cloud TTS)
→ Media plane
→ User
```

**media plane은 단계별 선택지**:
- MVP: WebSocket + AudioWorklet + Silero VAD
- Phase 2: LiveKit OSS 자체 호스팅 *or* WebSocket 강화 *or* aiortc
- Phase 3: SIP 게이트웨이 (LiveKit SIP / Twilio SIP)

# 반드시 포함할 내용

## 1. 전체 플랫폼 아키텍처

B2B 고객사 확장형 + vox 내재화 구조로 설계해줘.

포함 항목:

* Multi-tenant 구조
* 고객사별 Bot 설정
* 고객사별 Knowledge Base / RAG
* 고객사별 Prompt / Policy
* 고객사별 통화 시나리오 (Skill markdown)
* 고객사별 상담 로그
* 고객사별 관리자 화면
* 권한 관리
* 통화 모니터링
* 통계/리포트
* media plane 추상화 (어떤 옵션으로 바꿔도 백엔드 변경 없음)
* Voice Agent Server 구조

너무 딥한 프로토콜 설명은 제외하고,
서비스 아키텍처 관점에서 설명해줘.

---

## 2. 백엔드 구조 설계

백엔드는 아래 관점에서 설계해줘.

* API Server (FastAPI)
* Auth / Tenant 관리
* Bot Configuration 관리
* Skill / Flow 관리 (markdown content + 옵션 노드 그래프)
* Prompt 관리 (시스템 가드레일 + 페르소나 + 활성 스킬 합성)
* Knowledge Base / RAG 관리
* Call Session 관리 (WebSocket 라이프사이클)
* Voice Session Orchestrator (상태 머신: idle/listening/thinking/speaking)
* VAD / STT / LLM / TTS Provider Adapter
* Tool Calling / 외부 API 연동 (built-in + API tool)
* Call Log / Transcript 저장
* Analytics / Monitoring
* Admin API

각 컴포넌트별로:

* 역할
* 필요한 이유
* 기존 챗봇 레포에서 재사용 가능한 부분
* vox 대체로 신규 개발이 필요한 부분
* 구현 우선순위

를 표로 정리해줘.

---

## 3. 프론트엔드 구조 설계

프론트엔드는 B2B 관리자 콘솔 기준으로 설계해줘.

포함 화면:

* 로그인 / 조직 선택
* 대시보드
* 고객사별 Bot 목록
* Bot 생성 / 수정 (페르소나 / 시스템 프롬프트 / 인사말 / 음성 / 언어)
* Skill 편집 (markdown editor + 미리보기)
* Knowledge Base 업로드 / 관리
* Tool 등록 (built-in 토글 + API 도구 등록)
* 테스트 콜 화면 (마이크 + 라이브 트랜스크립트 + 오디오 재생 + barge-in)
* 실시간 콜 모니터링
* 통화 로그 / 녹취 / Transcript
* 실패 케이스 리뷰
* 통계 / 리포트
* 사용자 / 권한 관리

각 화면별로:

* 목적
* 주요 기능
* 필요한 API
* 백엔드와 연결되는 데이터
* MVP 포함 여부

를 정리해줘.

---

## 4. media plane 선택 가이드 (LiveKit은 옵션)

media plane을 어떤 옵션으로 갈지 단계별로 명확히 설명해줘.

포함 항목:

* MVP: WebSocket + AudioWorklet 구조 (PCM16 16kHz 청크 단위)
* Silero VAD로 발화 경계 판정
* 백엔드와 미디어 운반의 책임 분리
* Phase 2 진입 시점 의사결정 포인트
  - LiveKit OSS 자체 호스팅의 장단점
  - 순수 WebRTC(aiortc)의 장단점
  - WebSocket 스트리밍 확장의 장단점
* Phase 3 SIP/전화망 연동 옵션 (LiveKit SIP / Twilio)
* 상담원 모니터링·개입 구조 (음성 채널 sniff in)
* 향후 PSTN/전화번호 발급 방안

단, WebRTC/SIP 내부 프로토콜 수준까지 깊게 설명하지 말고,
팀 공유 및 제품 설계 관점으로 설명해줘.

---

## 5. 챗봇 레포 + vox 분석 결과 종합

### 챗봇 레포에서 그대로 재사용 가능

예:

* Clean Architecture 스캐폴딩
* Tenant 모델/도메인 서비스
* Prompt 도메인 (시스템 가드레일, defaults, router)
* LLM 호출 (Vertex AI / Gemini)
* Tool Calling (plugin 패턴)
* RAG (custom + external)
* Webhook 송수신
* Redis 캐시 패턴
* 보안 가이드

### 수정 후 재사용 가능

예:

* Session 관리 (turn → stream)
* Streaming 처리
* Conversation State (partial transcript 마킹)
* Agent Runtime (LangGraph 정교 분기 → 단일 LLM + 스킬 스왑으로 단순화)
* 핸드오버 로직 (텍스트→상담사 → 통화 전환)
* 로그 저장 구조 (timestamp/오디오 참조 추가)

### vox 대체로 신규 개발 필요

예:

* Audio Pipeline (브라우저 AudioWorklet)
* Silero VAD 어댑터
* GCP STT streaming 어댑터
* GCP TTS 어댑터
* Voice Session Orchestrator (상태 머신)
* Skill Loader / Runtime
* Frontdoor 라우팅
* 콜봇 어드민 콘솔
* Tool 런타임 (built-in: end_call, handover_to_human, transfer / API: dynamic)
* 콜 트랜스크립트 저장/조회
* 통화 후 분석(요약/추출)
* 음성 친화 응답 후처리 (URL→문자, 숫자 발음, 마크다운 제거)
* (Phase 2) WebRTC/LiveKit 통합
* (Phase 3) SIP/PSTN 게이트웨이

각 항목을 표로 정리해줘.

---

## 6. B2B 확장성 설계

고객사가 늘어나는 것을 전제로 설계해줘.

반드시 포함:

* Multi-tenant 데이터 모델
* Tenant별 설정 분리
* Bot별 설정 분리
* Knowledge Base 격리
* 통화 로그 격리
* 권한/역할 구조
* 요금제/사용량 측정 가능 구조
* 고객사별 커스터마이징 포인트
* 운영자가 고객사별 상태를 볼 수 있는 구조

---

## 7. 데이터 모델 초안

아래 엔티티 중심으로 데이터 모델을 제안해줘.

* Tenant
* User
* Role
* Bot
* Persona
* Skill
* Knowledge
* Tool
* CallSession
* Transcript
* ToolInvocation
* CallRecording (Phase 2+)
* AnalyticsEvent (Phase 2+)

각 엔티티별로:

* 목적
* 주요 필드
* 관계
* MVP 포함 여부

를 정리해줘.

---

## 8. API 설계 초안

아래 API 그룹을 제안해줘.

* Auth API
* Tenant API
* Bot API
* Persona API
* Skill API
* Knowledge Base API
* Tool API
* Call Session API
* WebSocket Voice API (`/ws/calls/{id}`)
* Transcript API
* Analytics API
* Admin API

각 API 그룹별로 대표 endpoint 예시를 작성해줘.

---

## 9. MVP 개발 범위 제안

처음부터 완성형으로 만들지 말고,
MVP / Phase 2 / Phase 3로 나눠줘.

## MVP

목표:

* 한 고객사가 웹에서 콜봇을 설정하고 **WebSocket으로 마이크 테스트 콜**을 해볼 수 있는 수준
* media plane은 WebSocket + Silero VAD. **LiveKit/SIP 미사용**

포함:

* Bot CRUD (페르소나/시스템 프롬프트/인사말/음성/언어)
* Skill CRUD (markdown content)
* Knowledge CRUD (텍스트 인라인)
* Tool: built-in (end_call, handover_to_human)만
* WebSocket 기반 테스트 콜 (브라우저 AudioWorklet)
* STT/LLM/TTS 연결 (GCP)
* 통화 로그 / Transcript 저장
* 기본 관리자 화면 (대시보드/봇/봇 편집/테스트 콜/통화 로그)
* 시드 데이터 (마이리얼트립 데모 봇)
* Mock 어댑터 fallback (GCP 키 없으면 echo로 동작)

## Phase 2

목표:

* B2B 운영 가능 수준 + media plane 확장 결정

포함:

* Multi-tenant 강화 (User/Role)
* media plane 결정: LiveKit OSS 자체 호스팅 도입 vs WebSocket 스트리밍 강화
* full-duplex / barge-in 정밀화
* pgvector RAG 정식화
* 실시간 모니터링
* 실패 케이스 리뷰
* 통계/리포트
* 권한 관리
* 외부 API Tool 연동 본격화
* 통화 후 분석/요약/추출

## Phase 3

목표:

* 실제 콜센터/전화망 연동 가능 수준

포함:

* SIP/전화망 연동 (LiveKit SIP / Twilio SIP)
* 상담원 개입
* 녹취 관리
* 고급 라우팅 / 캠페인 발신
* SLA/품질 모니터링
* 과금/사용량 관리
* DTMF / 통화 전환

---

## 10. 발표 자료 구성

최종 결과는 문서뿐 아니라 팀 공유용 발표 자료 형태로도 정리해줘.

PPT 구성안은 10~15장 내외로 작성해줘.

각 슬라이드는 아래 형식으로 작성해줘.

Slide N. 제목

* 핵심 메시지
* 설명 포인트
* 추천 시각 자료
* 발표자가 말할 핵심 멘트

포함해야 할 발표 흐름:

1. 왜 콜봇은 챗봇과 다른가
2. 현재 vox 종속 구조와 내재화 이유
3. media plane 선택지 (LiveKit은 옵션)
4. 전체 B2B 콜봇 플랫폼 구조
5. 백엔드 아키텍처
6. 프론트엔드 관리자 콘솔 구조
7. Voice Agent 처리 흐름 (WebSocket + VAD + STT + LLM + TTS)
8. 기존 챗봇 레포 재사용 가능 영역
9. vox 대체로 신규 개발이 필요한 영역
10. Multi-tenant 확장 구조
11. MVP 개발 범위 (WebSocket 기반)
12. 기술 리스크
13. 단계별 개발 로드맵 (MVP / Phase 2 / Phase 3)

---

## 11. 다이어그램

Mermaid로 아래 다이어그램을 작성해줘.

1. 전체 시스템 아키텍처 (media plane 추상화 강조)
2. WebSocket 기반 콜 세션 시퀀스
3. 백엔드 컴포넌트 구조
4. 프론트엔드 관리자 콘솔 구조
5. 데이터 모델 관계도
6. MVP 개발 범위 다이어그램
7. Voice Session Orchestrator 상태 머신 (idle/listening/thinking/speaking)

다이어그램은 발표 슬라이드에 바로 넣을 수 있게,
너무 복잡하지 않고 가독성 있게 작성해줘.

---

# 설명 깊이 제한

이번 자료는 연구용 문서가 아니라 팀 공유 및 제품 설계용 자료다.

따라서 아래는 제외해줘.

* WebRTC 내부 프로토콜 상세
* SIP 상세 스펙
* DSP/오디오 처리 알고리즘
* 네트워크 튜닝 파라미터
* 논문식 수식 설명
* 지나치게 저수준 구현 설명

대신 아래에 집중해줘.

* 제품 구조
* 서비스 아키텍처
* 백엔드/프론트엔드 책임 분리
* 고객사 확장성
* 기존 챗봇 코드 재사용 전략
* media plane 추상화 + 단계별 선택 가이드
* MVP를 어떻게 쪼개서 만들지
* 팀원이 이해할 수 있는 수준의 설명

# 최종 출력 형식

아래 순서로 작성해줘.

1. Executive Summary
2. 목표 제품 정의 (vox 내재화)
3. 전체 아키텍처
4. media plane 선택지 (LiveKit은 옵션)
5. 백엔드 설계
6. 프론트엔드 설계
7. 기존 챗봇 레포 + vox 분석 결과 종합
8. B2B Multi-tenant 설계
9. 데이터 모델 초안
10. API 설계 초안
11. MVP / Phase 2 / Phase 3 개발 범위
12. 기술 리스크
13. Mermaid Diagrams
14. PPT 구성안
15. Action Items

이제 기존 챗봇 레포와 vox docs를 분석해서,
**vox를 대체하는 자체 호스팅 B2B 콜봇 플랫폼** 설계 자료를 작성해줘.
