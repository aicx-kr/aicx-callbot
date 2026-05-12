# vox 콜봇 에이전트 구조 분석 — 노드 인덱스로 역설계

> 출처: `https://docs.tryvox.co/llms.txt` (vox 공식 문서 인덱스)
> 작성: 2026-05-11
> 목적: vox docs 사이드바와 노드 종류만 보고 vox 콜봇 에이전트의 내부 구조를 추론한다. aicx-callbot 인소싱 설계의 입력 자료.

---

## 0. 한 줄 요약

vox 에이전트는 **"두 모드 × 4 자산 × 11 노드"** 로 정리된다.

- **두 모드**: 프롬프트형(단일 LLM) / 플로우형(노드 그래프)
- **4 자산** (재사용 단위): **Persona · Skill · Knowledge · Tool**
- **11 노드**: 플로우 모드에서 조립 가능한 빌딩 블록 (대화·조건·추출·API·도구·전환·SMS·DTMF·시작·종료·글로벌)
- **Bot-level 평면 설정** (자산 아님, 운영 파라미터): voice · greeting · 인터럽트 정책 · 발음 사전 · DTMF 키매핑 · llm_model

> **자산 vs 운영 설정 구분 기준**: 재사용·라이브러리화·CRUD가 의미 있으면 자산, 봇 1개당 보통 1개로 굳어지면 평면 설정. Voice는 후자(MVP 기준).

---

## 1. 큰 그림 — 에이전트가 한 통화에서 하는 일

```
┌──────────────────────────────────────────────────────────────┐
│                         전화 채널                              │
│   (전화번호 / SIP / SDK: JS·React·Flutter·Python)              │
└────────────────────────────┬─────────────────────────────────┘
                             │ 음성 in/out
                ┌────────────▼─────────────┐
                │  음성 계층  STT ◀▶ TTS    │
                │  (발음가이드·인터럽트)     │
                └────────────┬─────────────┘
                             │ 텍스트 turn
                ┌────────────▼─────────────┐
                │      에이전트 두뇌         │
                │  ┌────────────────────┐  │
                │  │ 모드 A: 프롬프트     │  │
                │  │   = 프롬프트 1개     │  │
                │  │   + 지식 + 도구      │  │
                │  └────────────────────┘  │
                │  ┌────────────────────┐  │
                │  │ 모드 B: 플로우       │  │
                │  │   = 노드 그래프      │  │
                │  │   (11종 빌딩블록)    │  │
                │  └────────────────────┘  │
                │   공통: 변수 컨텍스트     │
                │   (dynamic·system·추출)   │
                └────────────┬─────────────┘
                             │ 통화 종료 후
                ┌────────────▼─────────────┐
                │  Post-call: 요약·태그      │
                │  → 웹훅·분석·CSV          │
                └──────────────────────────┘
```

핵심: **음성 ↔ 텍스트 변환은 컨테이너일 뿐**, 진짜 복잡함은 가운데 "두뇌" 레이어다.

---

## 2. 두 가지 에이전트 모드

### 2-1. 비교

|  | **프롬프트 에이전트** | **플로우 에이전트** |
|---|---|---|
| 정의 방법 | 큰 프롬프트 1개 | 노드를 선으로 잇는 그래프 |
| 분기 처리 | LLM이 알아서 | 명시적 condition 노드 |
| 변수/슬롯 | LLM이 자유롭게 | extraction 노드로 명시 |
| 적합 케이스 | "친절한 상담", FAQ | 신청서 받기, 결제, 본인확인 |
| 통제력 | 낮음 (LLM 신뢰) | 높음 (모든 분기 정의) |
| 만들기 | 빠름 | 느림 |
| 디버깅 | 어려움 (블랙박스) | 쉬움 (어느 노드인지 보임) |

### 2-2. 그림으로 비교

**프롬프트 에이전트** — 한 덩어리

```
┌─────────────────────────────────────┐
│  System Prompt                       │
│  "당신은 △△치과의 친절한 안내원…"      │
│                                       │
│  + 지식(RAG): 진료시간, 가격, 위치     │
│  + 도구: 예약등록(API), 통화전환       │
└─────────────────────────────────────┘
            ▲
            │ 매 턴마다 같은 프롬프트
            │ + 대화 history 통째로 LLM에
```

**플로우 에이전트** — 그래프

```
   [begin]
      │
      ▼
   [conversation: 인사·용건 묻기]
      │
      ▼
   [extraction: 의도 추출 → intent="예약"|"문의"]
      │
      ├─ intent=="예약" ─▶ [conversation: 날짜·증상] ─▶ [api: 예약등록] ─▶ [end]
      │
      └─ intent=="문의" ─▶ [conversation: 답변] ─▶ [end]

   ⟦global: 사용자가 "상담사" 말하면 어디서든 → [transfer: 통화전환]⟧
```

---

## 3. 노드 11종 — 카테고리별

플로우 에이전트의 빌딩 블록. 각 노드는 "받는 입력 → 하는 일 → 다음으로 넘기는 것"이 정해져 있다.

### A. 흐름 제어 (3종)

```
┌─────────┐      ┌─────────┐      ┌─────────┐
│ begin   │      │ end     │      │ global  │
│ 시작점   │      │ 종료점   │      │ 어디서든  │
│         │      │         │      │ 발동     │
└─────────┘      └─────────┘      └─────────┘
```

- **begin**: 통화 시작 시 진입. "첫 메시지(인사)" 발화.
- **end**: 통화 종료. 종료 사유 기록.
- **global**: 어떤 상태에 있든 트리거 (예: "상담사 바꿔줘"라는 말을 어느 노드에서든 잡아냄).

### B. 대화 (1종, 가장 중요)

```
┌──────────────────────────────────┐
│ conversation                      │
│   prompt: "날짜와 시간 물어봐"     │
│   transitions:                    │
│     - "날짜 받았으면" → 다음노드    │
│     - "거절했으면"   → end        │
└──────────────────────────────────┘
```

여러 turn을 묶어 하나의 "미니 대화" 단위. 이 노드만 LLM을 직접 호출.

### C. 데이터 처리 (3종)

```
┌────────────┐  ┌────────────┐  ┌────────────┐
│ extraction │  │ condition  │  │ api        │
│ 슬롯 채우기 │  │ 분기 판정   │  │ 외부 호출   │
└────────────┘  └────────────┘  └────────────┘
```

- **extraction**: 발화에서 변수 뽑기 (예: "내일 3시" → `date=2026-05-12, time=15:00`)
- **condition**: 변수 비교로 분기 (예: `age >= 19`)
- **api**: REST 호출, 응답을 변수에 저장

### D. 도구 호출 (1종)

- **tool**: 등록한 도구(API 또는 내장)를 명시적으로 실행

### E. 외부 채널 (4종)

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ transfer │  │ transfer │  │ send-sms │  │ (DTMF)   │
│ -call    │  │ -agent   │  │          │  │ 키패드   │
│ 사람에게  │  │ 다른봇    │  │ 문자발송  │  │ 입력처리 │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

- **transfer-call**: 사람 상담사로 통화 넘김
- **transfer-agent**: **다른 에이전트로 위임** ← 멀티 에이전트의 핵심
- **send-sms**: 문자 발송 (예: 예약 확인 링크)

---

## 4. 구체 예시 — "△△치과 예약봇"

### 시나리오
- 환자가 전화 → 인사 → 예약/문의 분기 → 예약이면 날짜·증상 받고 등록 → 확인 SMS → 종료
- "상담사" 외치면 어디서든 사람으로 연결

### 4-1. 프롬프트 에이전트 버전

```
System Prompt:
  당신은 △△치과 안내원이다. 다음 순서로 진행하라:
  1. 인사하고 예약/문의 의도를 물어라
  2. 예약이면 [날짜, 시간, 증상] 3개를 모두 받아라
  3. 다 받으면 register_appointment 도구를 호출하라
  4. 성공하면 send_sms 도구로 확인 문자를 보내라
  5. 사용자가 "상담사" 말하면 즉시 transfer_call 호출

Tools:
  - register_appointment(date, time, symptom) → bookingId
  - send_sms(phone, text)
  - transfer_call(reason)

Knowledge:
  - 진료시간.pdf, 가격표.pdf, 위치.pdf
```

LLM 한 번 호출에 모든 판단을 맡김. 빠르게 만들 수 있지만, "증상을 안 물어봤네" 같은 누락이 가끔 생김.

### 4-2. 플로우 에이전트 버전

```
                    [begin]
                       │
                       ▼
              [conversation: 인사 + 용건 묻기]
                       │
                       ▼
         [extraction: intent (예약 | 문의 | 기타)]
                       │
            ┌──────────┼──────────────┐
            │          │              │
       intent=예약  intent=문의   intent=기타
            │          │              │
            ▼          ▼              ▼
   [conv: 날짜 묻기]  [conv: 답변]   [conv: 재질문]
            │          │              │
            ▼          ▼              ▼
   [extract: date]   [end]          (loop)
            │
            ▼
   [conv: 시간 묻기]
            │
            ▼
   [extract: time]
            │
            ▼
   [conv: 증상 묻기]
            │
            ▼
   [extract: symptom]
            │
            ▼
   [api: POST /appointments
         body={date,time,symptom,phone}]
            │
            ▼
   [condition: api.status == 200?]
            │
       ┌────┴─────┐
      OK         FAIL
       │           │
       ▼           ▼
  [send-sms:    [conv: 죄송, 다시
   확인링크]     시도하시겠어요?]
       │           │
       ▼           └─▶ (loop or end)
     [end]

   ⟦global: utterance contains "상담사"
            → [transfer-call: reason=user_request]⟧
```

분기·검증·재시도 모두 명시적. 누락 안 생기지만 그리는 시간이 더 듬.

### 4-3. 한 턴이 어떻게 도는가 (플로우, "내일 3시요" 발화 케이스)

```
사용자: "내일 3시요"
    │
    ▼
┌─────────────────────────────────────┐
│ STT → "내일 3시요"                    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 1. global 노드 매칭 체크              │
│    "상담사" 포함? → 아니오. 통과.       │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 2. 현재 노드 = [extract: date]        │
│    LLM(JSON 모드):                   │
│      "내일 3시요" + system_date       │
│      → {"date": "2026-05-12"}        │
│    변수 컨텍스트.date = "2026-05-12"   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 3. transition 평가                   │
│    date != null → [conv: 시간 묻기]   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 4. 다음 노드의 prompt 실행            │
│    "오후 3시군요. 시간을 다시           │
│     정확히 말씀해 주시겠어요?"          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ TTS → 음성 → 사용자                   │
└─────────────────────────────────────┘
```

이 다섯 단계가 **매 turn마다** 반복된다. global 체크 → 노드 실행 → transition → 다음 노드.

---

## 5. 변수 시스템 — 3종 출처

```
┌────────────────────────────────────────────┐
│            변수 컨텍스트 (한 통화)            │
├────────────────────────────────────────────┤
│  ① dynamic   — 통화 시작할 때 주입            │
│      예: customer_name = "홍길동"             │
│          phone        = "010-1234-5678"       │
│      출처: SDK, 웹훅, 아웃바운드 캠페인         │
│                                              │
│  ② system    — 시스템이 자동으로 채움          │
│      예: call_id, started_at, caller_number   │
│                                              │
│  ③ extracted — 대화 중 extraction 노드가 채움 │
│      예: date, time, symptom                  │
└────────────────────────────────────────────┘
       │
       ▼
   모든 prompt/노드에서 {{변수명}}으로 사용
   예: "{{customer_name}}님, 안녕하세요"
```

이 변수 모델이 **핵심 도메인 모델**(별도 자산처럼 다룸)이라는 점이 중요. 프롬프트뿐 아니라 condition·API body·SMS 본문에서도 다 쓰인다.

---

## 6. 멀티 에이전트 위임 — `transfer-agent`

큰 봇 1개가 아니라 작은 전문 봇들을 체인하는 게 vox 스타일이다.

### 6-1. 기본 위임: "메인 안내봇 → 진료예약봇 → 결제봇"

```
   [메인 안내봇]
        │
        │ "예약하실 거에요" 발화
        ▼
   [transfer-agent: appointment_bot]
        │
        │ (변수 컨텍스트 그대로 인계)
        ▼
   [진료예약봇]
        │
        │ 예약 완료 → 결제 단계
        ▼
   [transfer-agent: payment_bot]
        │
        ▼
   [결제봇]
        │
        ▼
      [end]
```

각 봇은 자기 역할만 잘하면 됨. 프롬프트가 짧아지고 디버깅이 쉬워진다.

### 6-2. 한 세션 안에서 프롬프트 ↔ 플로우 자유 전환

`transfer-agent`는 **노드이자 동시에 builtin tool**이다 (`tools/builtin/transfer-agent.md`). 이 점이 핵심:

- **플로우 에이전트**: `transfer-agent` *노드*로 다른 에이전트에 전달
- **프롬프트 에이전트**: `transfer_agent` *툴*을 LLM이 function call로 호출

→ 두 모드 모두 다른 모드 에이전트를 호출 가능. 변수 컨텍스트는 그대로 인계.

#### 허브-앤-스포크 패턴 (실전에서 가장 자주 쓰이는 모양)

```
              ┌──────────────────────────┐
              │  메인 안내봇 (프롬프트)    │
              │  - 친절한 인사·일반 응대   │
              │  - FAQ (지식 RAG)         │
              │  - 의도 파악              │
              │                          │
              │  Tools:                  │
              │   • transfer_agent("…")  │
              └────────────┬─────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
    "예약할게요"      "결제 문제요"        "취소요"
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ 예약봇        │  │ 결제봇        │  │ 취소봇        │
│ (플로우)      │  │ (플로우)      │  │ (프롬프트)    │
│ 노드 8개      │  │ 노드 12개     │  │ 단순 응대     │
│ 슬롯필링 강제 │  │ 본인확인+PG   │  │              │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └────────┬────────┴─────────────────┘
                ▼
            완료 후 메인봇으로 복귀 (또는 종료)

⟦공유: 변수 컨텍스트 (customer_name, phone, …) 모두에서 접근 가능⟧
```

#### 시나리오 — △△치과 한 통화 안에서 모드가 두 번 바뀜

```
사용자: "여보세요"
  → [메인봇: 프롬프트] "안녕하세요, △△치과입니다. 무엇을 도와드릴까요?"

사용자: "내일 예약하려고요"
  → [메인봇] (LLM 판단) intent=예약
  → tool call: transfer_agent("appointment_flow_bot")
  → 변수 {customer_name, phone} 인계

  ━━━━━━ 모드 전환: 프롬프트 → 플로우 ━━━━━━

  → [예약봇: 플로우] "네, 날짜 알려주세요"   ← extract: date 노드
사용자: "내일 3시"
  → extract → date=2026-05-12, time=15:00
  → [예약봇] conv: "증상이 어떠신가요?"
사용자: "충치요"
  → extract → symptom="충치"
  → [예약봇] api: POST /appointments → 성공
  → [예약봇] send-sms: 확인 링크
  → [예약봇] end → transfer-agent 메인봇 복귀

  ━━━━━━ 모드 전환: 플로우 → 프롬프트 ━━━━━━

사용자: "근데 가격이 얼마예요?"
  → [메인봇 복귀: 프롬프트] (지식 RAG → 가격표) 답변
  → end
```

→ **사용자는 모드 차이를 전혀 느끼지 못한다.** 백엔드에서 두 번 핸드오프가 일어났을 뿐.

#### 우리 플랫폼에서 푸는 두 가지 방법

| | **옵션 A: Skill 단위 핸드오프 (vox 방식)** | **옵션 B: 한 Skill 안에서 sub-graph 중첩** |
|---|---|---|
| 모델 | `Skill A → transfer → Skill B` | `Skill 안에 root + sub-graph` 재귀 |
| 변수 | 세션에 1개, Frontdoor가 인계 | 자연스럽게 공유 |
| Latency | 핸드오프 지점에서 약간 (LLM 한 번 더 또는 직렬화) | 0 |
| 모델 복잡도 | 단순 (1-depth) | 복잡 (재귀 그래프) |
| 어드민 UX | Skill 목록·권한·버전관리 자연스러움 | 캔버스 안에 캔버스 |
| vox 마이그레이션 | 1:1 매핑 | 변환 필요 |

**MVP 추천: 옵션 A**
1. vox 사용자의 멘탈 모델 그대로 보존
2. 우리가 이미 `Frontdoor` 라우팅을 설계해뒀음 (재사용)
3. 옵션 B는 나중에 "고급 기능"으로 추가 가능 (반대는 어려움)

---

## 7. aicx-callbot 매핑 (요약)

| vox 개념 | 우리 도메인 | 비고 |
|---|---|---|
| 프롬프트 에이전트 | `Persona` + `Skill(prompt)` | MVP 우선 |
| 플로우 에이전트 | `Skill(graph)` | v2, 단 데이터 모델은 처음부터 graph-ready |
| conversation 노드 | `Skill` 단위 (markdown content) | 1:1 매핑 가능 |
| extraction 노드 | `Variable` 도메인 + LLM JSON 호출 | 슬롯 필링 런타임 |
| condition 노드 | CEL/JSONLogic 평가기 | 외부 라이브러리 후보 |
| api / tool 노드 | `Tool` 엔티티 + invocation 런타임 | chatbot-v2 재사용 |
| transfer-agent | Skill 간 라우팅 (`Frontdoor`) | 이미 설계됨 |
| transfer-call | Phase 3 (SIP refer) | MVP 미포함 |
| global 노드 | 인터럽트 핸들러 dispatcher | 별도 모듈 필요 |
| dynamic / system / extracted 변수 | `VariableContext` 단일 객체 | 첫 버전부터 통합 설계 |
| 지식 (text/web/file) | `Knowledge` + chunker + embedding | 3종 모두 지원 권장 |
| voice / pronunciation / first-message | `Bot` 평면 필드 (`voice`, `greeting`, …) | 자산 아님. Phase 2~3에서 라이브러리 요구 시 분리 |

---

## 8. 설계상 시사점

1. **두 모드는 UI 구분, 런타임은 단일 그래프 실행기**
   수학적으로 프롬프트 에이전트 = `conversation 노드 1개 + global 핸들러` 인 단일 노드 그래프. 따라서:
   - 런타임 코드베이스는 하나(graph executor)로 통일
   - UI만 둘로 분리: 마크다운 에디터(프롬프트 모드) / 노드 캔버스(플로우 모드)
   - 단일 노드 케이스는 LLM 1콜 fast path로 최적화
   - "프롬프트 모드 → 플로우 모드 전환" 버튼이 자동으로 1-노드 그래프를 캔버스에 풀어주면 마이그레이션 비용 0

2. **데이터 모델은 처음부터 graph-ready로**
   MVP가 프롬프트 모드만 쓰더라도 Skill 스키마는 노드/엣지를 담을 수 있어야 한다. 나중에 플로우 모드 붙일 때 마이그레이션 비용이 다르다. (위 1번의 자연스러운 귀결.)

3. **변수 컨텍스트는 핵심 도메인 모델 (별도 자산처럼 다룬다)**
   3종 출처(dynamic·system·extracted)를 한 객체로 통합하고, prompt·condition·api body·sms 모든 곳에서 `{{var}}` 치환이 가능해야 한다. 나중에 끼워 넣으면 피곤.

4. **`global` 핸들러를 위한 dispatcher 분리**
   "어느 상태에서든 상담사 연결"같은 글로벌 인터럽트는 단순 상태머신으로 못 푼다. 메인 그래프 실행기와 별개로 매 turn마다 글로벌 룰을 먼저 체크하는 dispatcher 레이어가 필요.

5. **Skill 단위 핸드오프 + 공유 변수 컨텍스트가 모드 전환을 자연스럽게 만든다**
   `transfer-agent`가 노드이자 builtin tool이라는 vox 설계 덕분에 한 통화 안에서 프롬프트↔플로우가 매끄럽게 섞인다. 우리도 같은 패턴(`Frontdoor` 라우팅 + 세션당 단일 `VariableContext`)으로 가면 됨. §6-2의 옵션 A가 MVP 기본형.

---

## 9. graph-ready Skill 데이터 모델 스케치

핵심 아이디어 한 줄: **"모든 Skill은 그래프다. 프롬프트 모드는 노드 1개짜리 그래프일 뿐."**

### 9-1. 스키마 한 장

```
┌─────────────────────────────────────────────────────────┐
│  Skill                                                    │
│    id, name, version, mode("prompt"|"flow")              │
│                                                           │
│    graph:                                                 │
│      entrypoint: NodeId                                   │
│      nodes: [Node, ...]                                   │
│      edges: [Edge, ...]                                   │
│      globals: [GlobalRule, ...]   ← "어디서든" 핸들러     │
│                                                           │
│    refs:                                                  │
│      persona_id, knowledge_ids[], tool_ids[]             │
└─────────────────────────────────────────────────────────┘

Node {
  id, type, config
  type: begin | conversation | extraction | condition
      | api | tool | transfer-agent | transfer-call
      | send-sms | end
}

Edge { from, to, when? }   ← when은 변수 조건식
```

`mode`는 **UI가 읽는 힌트**일 뿐, 런타임은 무조건 graph executor로 돌린다.

### 9-2. 두 모드가 같은 스키마에 어떻게 담기나

**프롬프트 모드** = 1-노드 그래프
```
[begin] → [conversation: prompt="당신은 △△치과 안내원…"] → [end]
                              + tool_ids, knowledge_ids
                              + globals: ["상담사" → transfer-call]
```

**플로우 모드** = N-노드 그래프
```
[begin] → [conv] → [extract] → [condition] → [api] → [send-sms] → [end]
                                    │
                                    └─▶ ...
        + globals
```

→ 똑같은 JSON 구조. 노드가 1개냐 N개냐의 차이뿐.

### 9-3. 이 설계가 주는 이득

1. **마이그레이션 0** — 프롬프트 → 플로우 전환 = 노드 추가만. 데이터 변환 없음.
2. **런타임 코드 1개** — graph executor 하나만 잘 만들면 됨. 1-노드 케이스는 fast path로 LLM 1콜만.
3. **버전 관리 단순** — Skill 단위 스냅샷. 모드 바뀌어도 같은 스키마라 diff 깔끔.
4. **Frontdoor 핸드오프 통일** — `transfer-agent`는 노드든 tool이든 결국 "Skill ID로 점프 + 변수 인계" 한 줄.

### 9-4. 결정 사항 / 주의

- **transitions vs edges**: 노드 안에 transition을 넣지 말고 **그래프 레벨 `edges`로 통일**. 시각화 라이브러리들이 다 edges 가정.
- **globals는 별도 컬렉션**: 노드/엣지에 끼우지 말 것. 매 턴 dispatcher가 먼저 평가하는 별도 룰 셋.
- **node.config는 type별 다른 스키마**: discriminated union으로 처리 (Pydantic `Field(discriminator="type")`).
- **Edge.when은 표현식 문자열**: CEL 또는 JSONLogic. 자체 파서 만들지 말 것.

---

## 10. aicx-callbot 적용 방향 — 구체 구조

지금까지의 분석을 우리 코드베이스에 어떻게 떨어뜨릴지. **현재 상태 진단 → 목표 구조 → 로드맵** 순.

### 10-1. 현재 상태 진단

| 영역 | 현재 | 목표와의 격차 |
|---|---|---|
| `backend/src/domain/entities.py` | `BotRuntime` 1개 (LLM 호출 직전 합성된 런타임만) | Skill/Persona/Tool/Knowledge/Graph/Node/Edge/VariableContext 모두 부재 |
| `backend/src/application/` | `skill_runtime`, `voice_session`, `tool_runtime`, `post_call` 등 이름만 잡힘 | GraphExecutor·Dispatcher·Frontdoor 명확히 분리 안 됨 |
| `frontend/src/components/FlowEditor.tsx` ↔ `MarkdownEditor.tsx` | 별도 컴포넌트, 별도 라우트 추정 | 같은 Skill을 다른 뷰로 편집하는 통합 SkillEditor 부재 → 모드 전환 시 데이터 손실 위험 |
| 변수 시스템 | 통합된 `VariableContext` 도메인 부재 | dynamic/system/extracted 3종을 한 객체로 모아 모든 노드/프롬프트에서 `{{var}}` 치환 필요 |
| global 핸들러 | 모델·런타임 모두 부재 | "어디서든 트리거"용 dispatcher 레이어 별도 신설 필요 |

### 10-2. 목표 백엔드 도메인 모델 (graph-ready)

```
backend/src/domain/
├── skill/
│   ├── skill.py            # Skill aggregate root (id, name, version, mode, graph, refs)
│   ├── graph.py            # Graph value object (nodes, edges, globals, entrypoint)
│   ├── node.py             # Node + 11 type union (discriminator="type")
│   ├── edge.py             # Edge (from, to, when?)
│   └── global_rule.py      # GlobalRule (pattern, target_node_id)
├── variable/
│   └── context.py          # VariableContext (세션당 1개, 3종 출처 통합)
├── persona/
│   └── persona.py
├── knowledge/
│   └── knowledge.py        # Knowledge (source: text|webpage|file, chunks, embeddings)
├── tool/
│   └── tool.py             # Tool (REST 도구 + builtin)
├── session/
│   └── call_session.py     # CallSession + TurnLog
└── ports.py                # 의존성 역전 인터페이스
```

**핵심 시그니처**

```python
@dataclass(frozen=True)
class Skill:
    id: SkillId
    name: str
    version: str
    mode: Literal["prompt", "flow"]   # UI 힌트
    graph: Graph                       # 런타임은 항상 graph로 실행
    persona_id: PersonaId
    knowledge_ids: list[KnowledgeId]
    tool_ids: list[ToolId]

@dataclass(frozen=True)
class Graph:
    entrypoint: NodeId
    nodes: list[Node]            # 1-노드면 프롬프트 모드
    edges: list[Edge]
    globals: list[GlobalRule]

@dataclass(frozen=True)
class Node:
    id: NodeId
    type: Literal["begin", "conversation", "extraction",
                  "condition", "api", "tool",
                  "transfer-agent", "transfer-call",
                  "send-sms", "end"]
    config: NodeConfig           # type별 다른 스키마 (Pydantic discriminated union)

@dataclass
class VariableContext:
    dynamic: dict[str, Any]      # SDK/웹훅으로 주입
    system: dict[str, Any]       # call_id, started_at, caller_number...
    extracted: dict[str, Any]    # extraction 노드가 채움
    def resolve(self, template: str) -> str: ...   # {{var}} 치환
```

### 10-3. 목표 백엔드 애플리케이션 서비스

```
backend/src/application/
├── graph_executor.py       # 그래프 한 step 실행, 노드 타입별 핸들러 dispatch
├── dispatcher.py           # 매 턴 가장 먼저: global 룰 체크 → executor 호출
├── frontdoor.py            # transfer-agent 라우팅 (Skill 간 이동)
├── extractor.py            # LLM JSON 모드로 slot 채우기 (extraction 노드)
├── evaluator.py            # CEL/JSONLogic 표현식 평가 (condition + edge.when)
├── voice_session.py        # WebSocket 통화 세션 라이프사이클
└── post_call.py            # 통화 종료 후 요약/태깅 잡
```

**한 턴 실행 순서**

```
[WebSocket으로 사용자 발화 도착]
        │
        ▼
VoiceSession.handle_utterance(audio)
   ├─ STT → text
   ├─ Dispatcher.dispatch(text, session.var_ctx, session.current_node)
   │     ├─ 1. global 룰 매칭? → Frontdoor.transfer(target_node) → return
   │     ├─ 2. 현재 노드를 GraphExecutor에 위임
   │     │     ├─ conversation → LLM 호출 (prompt + RAG + tools)
   │     │     ├─ extraction   → Extractor.extract(text, schema)
   │     │     ├─ condition    → Evaluator.eval(expr, var_ctx)
   │     │     ├─ api          → HTTP 호출 + 응답 → var_ctx
   │     │     ├─ tool         → ToolRuntime.invoke
   │     │     ├─ transfer-agent → Frontdoor.handoff(target_skill_id)
   │     │     └─ ...
   │     ├─ 3. transition 평가 → 다음 노드 결정
   │     └─ 4. session.current_node 업데이트
   └─ TTS → 음성 반환
```

### 10-4. 프론트엔드 — 통합 SkillEditor

현재 `FlowEditor.tsx`와 `MarkdownEditor.tsx`가 분리된 구조를 **하나의 `SkillEditor`로 통합**하고 뷰만 토글한다.

```
frontend/src/components/
├── SkillEditor/
│   ├── index.tsx                # 진입점: skill.mode에 따라 뷰 선택
│   ├── PromptView.tsx           # 1-노드 그래프를 마크다운으로
│   ├── FlowView.tsx             # N-노드 그래프를 캔버스로 (react-flow 등)
│   ├── ModeToggle.tsx           # "Flow 모드로 전환" 버튼 → 1-노드를 캔버스로 풀어줌
│   └── NodeConfig/              # 노드 타입별 우측 설정 패널
│       ├── ConversationConfig.tsx
│       ├── ExtractionConfig.tsx
│       ├── ConditionConfig.tsx
│       ├── ApiConfig.tsx
│       ├── TransferAgentConfig.tsx
│       └── ...
├── Sidebar/
│   ├── WorkspaceSelector.tsx    # 워크스페이스 셀렉터 (vox echo 패턴)
│   ├── AnalysisTree.tsx         # 분석 영역: 지표·태그
│   └── BuildTree.tsx            # 빌드 영역: 페르소나·지식·스킬 nested tree
├── Header/
│   ├── BotTitle.tsx
│   ├── VersionDropdown.tsx
│   └── DeployButton.tsx
└── TestPanel/
    ├── LiveChat.tsx             # WebSocket 채팅 (텍스트+음성)
    ├── TurnMeta.tsx             # 턴별 latency/cost/사용 노드
    └── GlobalTrigger.tsx        # global 룰 발동 시각화
```

핵심: **두 뷰가 같은 `Skill` 객체를 본다.** 모드 토글이 데이터 변환 없이 시각화만 바꿈.

### 10-5. 단계별 로드맵

| Phase | 범위 | 백엔드 | 프론트엔드 |
|---|---|---|---|
| **1 — MVP** | 프롬프트 모드 1-Skill, WebSocket 텍스트+음성 | Skill(1-node graph) · Persona · 기본 Tool · GraphExecutor(conv 노드만) · VariableContext | SkillEditor(PromptView) · LiveChat · Sidebar 기본 |
| **2 — Multi-Skill** | Skill 간 핸드오프 + 어드민 어포던스 | Frontdoor · transfer-agent · 버전관리 · 워크스페이스 | 워크스페이스 셀렉터 · BotTree · VersionDropdown · DeployButton |
| **3 — Flow** | 플로우 노드 풀세트 + global | Extractor · Evaluator · Dispatcher · 전 노드 타입 핸들러 · GlobalRule | FlowView 캔버스 · NodeConfig 패널들 · GlobalTrigger 시각화 |
| **4 — Telephony** | SIP 인입 · 아웃바운드 캠페인 | SIP gateway · 캠페인 잡 워커 | 전화번호 관리 · 캠페인 UI |

Phase 1만 만들어도 **데이터 모델은 Phase 3까지 담을 수 있어야** 한다 (graph-ready). 이게 §8 시사점 ②번의 의미.

### 10-6. 깔끔한 구조의 핵심 원칙 (요약)

1. **런타임은 하나, UI는 둘.** `graph executor` 한 곳에 노드 타입별 핸들러를 모은다.
2. **Skill = Graph + refs.** 모든 Skill이 Graph 필드를 가진다. 프롬프트 모드는 1-노드 그래프.
3. **VariableContext는 세션당 1개 객체.** 3종 출처를 합치고, 모든 노드·프롬프트·식에서 동일하게 참조.
4. **Dispatcher가 매 턴 첫 단계.** global 룰 평가가 executor 진입보다 먼저.
5. **Frontdoor가 핸드오프 단일 진입점.** transfer-agent는 노드든 tool이든 결국 같은 호출.
6. **프론트는 같은 Skill을 두 시각으로.** 모드 토글이 데이터 변환 없이 뷰만 전환.

---

## 11. 부록 — vox docs 노드/구성요소 인덱스 (출처)

### 노드 (`/docs/build/flow/nodes/*`)
overview · begin · conversation · condition · extraction · api · tool · transfer · transfer-agent · send-sms · end · (advanced/global-node)

### 빌드 영역
single-prompt(overview, prompt-writing) · voice(voice-select, pronunciation-guide) · knowledge(text, webpage, file) · tools(api + builtin: end-call, send-sms, send-dtmf, transfer-call, transfer-agent) · variables(dynamic, system) · conversation(call-settings, speech-settings, first-message, dtmf) · versioning · post-call/extraction

### 배포 / 모니터링
SDK(JS, React, Flutter, Python) · 전화번호 · 아웃바운드(단건/대량) · SIP / 통화기록 · 분석 · 알림 · post-call · 웹훅 · export
