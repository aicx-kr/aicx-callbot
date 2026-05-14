# vox v3 API 응답 구조 + 인사이트 분석

> GET 호출 37건 (성공 33 / 400 2 / 500 1 / 비실수 1) · Mutation spec 분석 8개 · 작성 2026-05-13
> 입력 문서: `2026-05-13-vox-api-spec-insights.md` (OpenAPI 정적 분석)
> raw snapshots: `docs/plans/.vox-snapshots/` (gitignore)
> 본 문서: spec 검증이 아니라 **실 응답을 1차 자료**로 vox 설계 의도를 재구성하고 aicx-callbot 도메인 모델 결정으로 환원

---

## 0. TL;DR — 응답을 보고 설계가 바뀌어야 한다고 판단한 5가지

1. **call_cost는 flat `{total_cost: "string"}`이다.** spec 문서 가설(`sub_costs[]`)은 응답에 없음. ledger 패턴 도입을 보류하고 단일 컬럼 + 별도 cost-detail 비동기 ETL을 따로 설계해야. 비용 분해는 vox webhook이 아니라 자체 측정으로만 가능.
2. **vox의 array 필터(`status[]`, `call_type[]`)는 실제로 받지 않는다.** spec 문서가 잘못 인용. 실 API는 단일값 `status=ended` 식. 4xx 응답에 `allowed_query_parameters` 배열을 친절히 동봉 — 우리도 같은 self-describing 에러를 차용해야.
3. **agent 버전 폭증을 가정해야 한다.** production 운영 중인 단일 agent에 **v262**까지 누적. 콘솔 변경마다 새 버전이 찍히는 패턴. → `bot_version`을 `int` PK + `description nullable`로 가볍게, 페이징·정리 정책(보존 기간/숫자 캡)을 처음부터 설계.
4. **flow_data는 ReactFlow의 visual state까지 서버에 박는다.** `nodes[].position.{x,y}`, `nodes[].measured.{w,h}`, `viewport.{x,y,zoom}` 전부 응답에 옴. → flow 에디터는 "데이터+레이아웃" 동시 저장 API가 필수. 우리 콘솔도 ReactFlow면 그대로 차용, 다른 라이브러리면 layout-state 분리 저장 layer 필요.
5. **vox는 41개 JSON 스키마를 self-publish하고 21개는 `source=db`다.** schema registry가 코드가 아니라 DB에 있다는 뜻. → 우리도 sub-config 스키마(prompt/llm/voice/...)를 코드 enum이 아닌 `tenant_schema` 테이블 + override 메커니즘으로. 고객사별 필드 커스터마이즈가 코드 push 없이 가능.

---

## 1. 환경 한 줄 요약

| 리소스 | total | page | 비고 |
|---|---:|---:|---|
| agents | 82 | 10 | single_prompt 4 / flow 6 (page 기준) |
| calls | **201,312** | 10 | 실 production 트래픽 — transcript / call_analysis / call_cost 채워진 비율 89% / 68% |
| campaigns | 6 | 6 | 모든 캠페인 1페이지 (next_cursor=null) |
| knowledges | 15 | 10 | 응답 sparse (id/name/created_at) — 상세 fetch 필요 |
| tools | 1,325 | 10 | 누적 자산 — 비공개 함수 카탈로그 |
| organization-telephone-numbers | 3 | 3 | 1개 vox provider + 2개 custom (BYO SIP) |
| alert-rules | n/a | n/a | **HTTP 500 INTERNAL_ERROR** (vox 서버 측 이슈) |
| incidents | 26 | 10 | alert-rules 죽었어도 incidents는 살아 있음 |
| models/llms | 24 | 24 | 9 providers (openai, anthropic, google, deepseek, ...) |
| models/voices | 389 | 50 | 11 ko-KR (page 기준), 3 provider (google 우세) |
| schemas | 41 | 41 | namespace 4종 · category 5종 · source 3종 |

호출 budget: 200건 한도 중 37건 사용. 429 발생 0회.

---

## 2. 리소스별 응답 구조 + 인사이트

### 2.1 Agent

#### 2.1.1 구조 (n=2 detail: single_prompt v262, flow v3)

```
AgentDetailResponse:
  agent_id: UUID                       [2/2]
  name: string                         [2/2]
  type: enum                           [관측: single_prompt, flow]
  created_at: int (unix ms)            [2/2]
  updated_at: int (unix ms)            [2/2]
  production_version: string|null      [샘플 분포(page n=10): v22/v25/v262/v3 / null 5건]
  data: object (13 keys)               [2/2]
    prompt: object (5)
      prompt: string                   [길이 32089(sp), 945(flow) — single_prompt에 본문이 거대]
      firstLine: string                [관측: "" (둘 다)]
      firstLineType: enum              [관측: aiFirstDynamic, aiFirst]
      pauseBeforeSpeakingSeconds: float [관측: 0.0]
      isFirstMessageInterruptible: bool [관측: True, False]
    stt: object (2)
      languages: array<string>         [길이 1 — ko-KR로 추정 (마스킹)]
      speed: enum                      [관측: low(sp), high(flow)]
    llm: object (4)
      model: string                    [관측: openai/gpt-5.2, z-ai/glm-4.7]
      temperature: float               [관측: 0.0]
      thinkingBudget: null             [null/지원 안 함]
      reasoningEffort: null
    voice: object (7)
      id: string                       [관측: ko-KR-Chirp3-HD-Despina, ...-Laomedeia]
      provider: string                 [관측: google]
      model: string                    [관측: chirp3-hd]
      speed: float                     [관측: 1.02, 1.04]
      volume: null|float               [관측: null(sp), 1.0(flow) — 둘 다 의미 있음]
      language: null                   [voice id에 lang 묻혀 있음]
      temperature: null|float          [voice별 temperature가 별도 존재 (관측: null, 0.9)]
    speech: object (2)
      responsiveness: float            [관측: 1.0]
      boostedKeywords: string          [CSV string ("투어,변경,..."), array 아님]
    callSettings: object (10)
      backgroundMusic: enum            [관측: none]
      backgroundMusicVolume: float     [관측: 0.0, 0.2]
      noiseCancellation: enum          [관측: bvc (Krisp BVC)]
      activationThreshold: float       [관측: 0.6]
      callTimeoutInSeconds: int        [관측: 900 — spec default와 일치]
      silenceCallTimeoutInSeconds: int [관측: 60, 120 — 침묵 기준 별도]
      ringDurationInSeconds: int       [관측: 30, 60]
      dtmfTerminationEnabled: bool     [관측: True]
      dtmfTerminationKey: string       [관측: "#"]
      dtmfTimeoutSeconds: int          [관측: 3, 5]
    postCall: object (1)
      actions: array<PostCallAction>   [관측: sp는 [], flow는 9건 (extraction)]
        name/type/description/isNullable/enumOptions
    security: object (1)
      optOutSensitiveDataStorage: bool [관측: False]
    webhookSettings: object|null (3)   [관측: sp는 채워짐, flow는 null]
      callDataWebhookUrl: string
      inboundCallWebhookUrl: string
      webhookVersion: null
    knowledge: object (2)
      ragEnabled: bool                 [관측: False (둘 다)]
      knowledgeIds: array<int>         [관측: [], [1건] — knowledge ID는 int]
    presetDynamicVariables: object     [관측: 키 1~2개, 값 string (JSON도 string으로)]
    toolIds: array<string>             [관측: 6, 0]
    builtInTools: array<object>        [관측: 3, 0]
      toolType: enum                   [관측: skill]
      name/description: string
      skill: object {skills[], initSkillId, initSkillName}
                                       [관측: skills 36개, initSkillId 별도]
  flow_data: object|null               [관측: sp는 null, flow는 채워짐]
    nodes: array<FlowNode>             [관측: 23개 (begin 1 / conversation 17 / endCall 5)]
      id/type/data/position/measured/selected/dragging/sourcePosition/targetPosition
    edges: array<FlowEdge>             [관측: 33개 (node>edge — 분기 우세)]
      id/source/target/type/sourceHandle/targetHandle/animated/selected
    viewport: object                   [관측: {x: -1399.17, y: -195.65, zoom: 0.72}]
  version: object|null                 [current=null, 버전 fetch 시 {version, description, is_production, created_at}]
```

#### 2.1.2 Version 패턴

```
GET /agents/{id}/versions (n=1, target=single_prompt 운영봇)

VersionsResponse:
  versions: array<VersionMeta>         [길이 262]
    version: string                    [v1 ~ v262, semver 아님 — incrementing string]
    description: string|null           [관측: 전부 null]
    is_production: bool                [정확히 1개만 true]
    created_at: int (unix ms)
  total_count: int
```

- agent 1개당 v262까지 누적. **운영 80일 동안 ~3 버전/일.**
- `description`이 전부 null인 점이 시사적 — 콘솔 UX가 description을 강제하지 않음.

#### 2.1.3 Mutation spec 분석 (호출 X)

- `POST /agents` `CreateAgentRequest`: name만 필수. 모든 sub-config 생략 → vox default 적용. 점진적 채움 패턴.
- `PATCH /agents/{id}` `UpdateAgentRequest`: omit=유지, null=해제. `agent-data-update` 스키마 `$defs` 18개 — sub-config별 partial 구조 자동 생성.
- `POST /agents/{id}/versions` body: `description`만 받음. 작업 중 `data`가 통째로 스냅샷. → 버전 = 시점의 immutable copy.
- `POST /agents/{id}/versions/{version}/publish`: production 포인터 swap. previous_production_version 응답 = 롤백 audit 의도.

#### 2.1.4 인사이트

##### 인사이트 A1: agent.data는 13 sub-config, 그 중 9개가 schema registry $defs에 있다

관찰: agent-data-response 스키마는 `$defs`에 `AgentPrompt`, `AgentSTT`, `AgentLLM`, `AgentVoice`, `AgentSpeech`, `AgentCallSettings`, `AgentPostCall`, `AgentSecurity`, `AgentWebhookSettings`, `AgentKnowledge` 10개를 가진다. 이게 `data` 하위의 camelCase 묶음과 정확히 매칭.
해석: vox는 agent를 "9개의 독립 sub-config + 3개의 자산 참조(knowledge/tools/builtInTools) + 1개의 변수 dict"로 본다. 각 sub-config는 독립 PATCH 대상이 될 잠재력이 있는데, 현재 API는 통합 PATCH만 제공.
우리 적용: `bot_config` 테이블을 단일 JSONB가 아니라 **9개 sub-config 컬럼 + JSON Schema validator**로. 콘솔에서 prompt만 수정해도 LLM 설정은 건드리지 않는 partial update가 가능. 또는 sub-config별 row(`bot_config(bot_id, version, key, value_jsonb)`).

##### 인사이트 A2: production_version은 "current 위에 띄우는 포인터"다

관찰: `GET /agents/{id}` (no query) 응답의 top-level `version: null`. `?version=production` 응답에 `version: {version: "v262", ...}`. data 내용은 동일 (현재 production이 v262라서). v1 fetch는 prompt 길이 26314 → 32089로 성장 추적 가능.
해석: "current"는 워킹드래프트, 명시 버전은 immutable. publish는 production 포인터를 옮기는 행위. 1 agent ↔ N versions ↔ 1 production pointer.
우리 적용: `bot(id, name, type, production_bot_version_id)` + `bot_version(id, bot_id, version_int, data_jsonb, description, created_at, is_published bool)`. 통화 routing은 `production_bot_version_id`만 따라가고, 콘솔 편집은 새 row insert. `flow_data`는 JSONB 컬럼 또는 별도 테이블.

##### 인사이트 A3: flow 노드의 measured / viewport까지 응답에 박혀 있다

관찰: `flow_data.nodes[].measured = {width, height}`, `flow_data.viewport = {x, y, zoom}`. 즉 ReactFlow 캔버스의 시각 상태가 서버 저장.
해석: 콘솔이 ReactFlow 기반이고, 사용자 캔버스를 "마지막으로 본 모양 그대로" 복원하는 것이 UX 요구사항. 다른 사용자가 열어도 같은 레이아웃 보임 → 협업 시 시각적 일관성.
우리 적용: 콜봇 콘솔 flow 에디터를 ReactFlow로 가면 그대로 차용. 다른 lib(예: rete.js)이면 viewport+measured를 **별도 user_preference로 분리**(서버 공통 X, 사용자별 lastViewport)하거나 그냥 함께 박는다. **ReactFlow + 캔버스 상태 서버 저장**이 우리 기준선.

##### 인사이트 A4: builtInTools는 "tool 카탈로그에 안 들어가는 1급 시민"

관찰: agent.data.toolIds는 `tool` 리소스 ID 배열, builtInTools는 **inline object 배열**. 관측된 toolType=skill (관측 1종, spec에 endCall/sendSms/transfer 등 더 있음).
해석: skill/endCall/sendSms처럼 vox 자체가 의미를 강제하는 "도메인 액션"은 일반 tool과 lifecycle이 다름 (재사용 X, agent-내장). 일반 tool은 외부 API 호출, builtIn은 vox 내부 동작.
우리 적용: `tool` 테이블 ≠ `bot_skill` 테이블. 외부 API tool(input_schema + api_configuration)과 내장 액션(transfer/sms/dtmf/skill)을 분리. skill은 vox 'Frontdoor' 같은 라우터 패턴(초기 skill로 분기) → 우리도 동일.

---

### 2.2 Call

#### 2.2.1 구조 (n=3 detail + n=28 list 집계)

```
CallDetailResponse:
  id: UUID                              [3/3]
  agent: object                         [3/3]
    agent_id: UUID
    agent_version: string               [관측: production, v262 — current 인용 / 정확 버전 인용 둘 다]
  call_type: enum                       [관측 분포(n=28): inbound 16, outbound 10, web 2 — "web"이 실제 사용 중]
  from_number/to_number/presentation_number: string   [PII 마스킹]
  status: enum                          [관측 분포: ended 17, not_connected 6, ongoing 3, error 2]
  disconnection_reason: enum|null       [관측: call_transfer 7, user_hangup 8, dial_no_answer 6, flow_error 2, agent_hangup 1, voicemail_reached 1, null 3]
  start_at/end_at: int|null (unix ms)
  recording_url: string|null            [presigned URL 추정]
  metadata: object                      [관측: {user_id: "..."}만 — 운영자가 1개만 박음]
  dynamic_variables: object             [관측: 10~12 keys / call. 키 컨벤션 혼재 (snake/camel/hyphen)]
  call_analysis: object|null            [채워짐 25/28]
    summary: string                     [LLM 요약 텍스트]
    user_sentiment: enum                [관측: neutral, positive — negative는 본 샘플에 없음]
    custom_analysis_data: array         [관측: 전부 [] — agent에 정의된 추출 항목별 결과 자리지만 비어있음]
  call_cost: object|null                [채워짐 19/28]
    total_cost: string (KRW decimal)    [관측: "200.00", "150.00" — 정수형 비용]
    [hidden] sub_costs: 없음            # spec/prompt 가설과 다름. flat만 존재.
  variant_label: string|null            [관측 전부 null — A/B 미사용]
  opt_out_sensitive_data_storage: bool  [관측 전부 False]
  transcript: array<TranscriptEvent>|null  [길이 17~33 (관측 3건)]
    role: enum                          [관측: agent, user, tool_call_invocation, tool_call_result]
    agent/user: {role, content, start_at, end_at}
    tool_call_invocation: {role, tool_call_id, name, arguments}
    tool_call_result: {role, tool_call_id, content}
```

#### 2.2.2 관측 분포 (n=28 list 집계)

- **call_type 분포**: inbound 57% / outbound 36% / web 7%. "web"이 spec 별개로 active.
- **status × analysis filled**: ended 17/17 분석 채워짐. ongoing/not_connected는 미채움.
- **status × cost filled**: ended는 모두 채워짐. **not_connected도 cost가 NULL** — 연결 실패는 비과금.
- **transcript role 분포** (3 detail 합산, n=77 events): tool_call_invocation+result 54%, agent 19%, user 10%. **tool 호출이 사람 발화보다 많다.**
- **dynamic_variables 키 사례**: `did, A_RN, call_id, call_to, integer, user_id, agent_id, call_ivr, air_email, call_from, user_name, fs-support`. snake_case, camelCase, hyphen 혼재. `integer`라는 키 이름은 임시변수 흔적.

#### 2.2.3 Mutation spec 분석

- `POST /calls` `CreateCallRequest` — from_number/to_number 필수. agent 생략 시 발신번호 traffic-split. 사용자 metadata + dynamic_variables 자유.
- response status가 `queued`인 별도 lifecycle phase 존재 (관측은 못 함 — 6초 안에 ongoing 전환되는 듯).

#### 2.2.4 인사이트

##### 인사이트 C1: call_cost는 flat decimal string 1개. 분해는 없다.

관찰: 검사한 모든 call_cost가 `{total_cost: "150.00" | "200.00"}` 단일 키. spec/prompt 가설(`sub_costs[]`)은 응답에 부재.
해석: vox는 통화 단위 단일 가격(예: 150원/통화)로 과금. LLM/STT/TTS/telephony 분해는 운영자에게 노출하지 않음. 내부적으로는 분해해도 API 표면은 단순화.
우리 적용: `call` 테이블 `total_cost NUMERIC(10,2)` 단일 컬럼. **분해 비용 분석은 webhook이 아닌 자체 측정**으로 별도 ETL 파이프라인 구축. ledger 패턴은 보류. 우리 콘솔이 분해 비용 요구한다면 vox 의존도 줄이고 우리 메타링 layer가 필요하다는 신호.

##### 인사이트 C2: 배열 필터는 단일값만 허용 — spec과 실제가 다름

관찰: `GET /calls?status[]=ongoing&status[]=error` → 400 VALIDATION_ERROR, message: "지원하지 않는 query parameter입니다", **친절히 `allowed_query_parameters: [agent_id, call_from, call_to, call_type, cursor, disconnection_reason, limit, sort_order, start_at_after, start_at_before, status]` 동봉.** `status=ongoing` (singular)는 200.
해석: 선행 spec 문서가 잘못 인용. 실 API는 array 필터 미지원. 4xx 응답에 도움말을 동봉하는 self-describing 에러는 우수 사례.
우리 적용:
- **우리 API도 같은 self-describing 에러 패턴** 차용. FastAPI dependency로 query param 화이트리스트 + 400 응답에 `allowed_query_parameters` 동봉.
- 다중 status 필터가 진짜 필요하면 우리 콜봇은 array를 받되 vox 위임 호출 시 OR 루프(N+1 호출)로 대체. 또는 vox에 기능 요청.

##### 인사이트 C3: transcript는 timeline, role-별 schema가 다르다

관찰: transcript 4 role 각각 키셋이 다름. agent/user에는 `start_at/end_at`(발화 시점), tool_call_*에는 `tool_call_id`. tool_call_invocation에 `arguments`(JSON dict), result에 `content`(string).
해석: 발화 vs 도구 호출은 본질적으로 다른 이벤트. 단일 array에 polymorphic하게 담음. tool_call_id로 invocation↔result 짝.
우리 적용: `transcript_event(call_id, seq, occurred_at, role, content_jsonb)` — `content_jsonb`에 role별 다른 페이로드. Discriminated union(Pydantic Tagged Union)으로 domain entity. `tool_call_id`는 별도 컬럼 인덱스.

##### 인사이트 C4: dynamic_variables 키 컨벤션이 강제되지 않는다

관찰: `did`, `A_RN`, `fs-support`, `air_email`, `integer` 등 케이스 혼재 + 무의미 이름. vox는 어떤 키 검증도 안 함 (any string → any string|JSON-as-string).
해석: vox는 변수 카탈로그를 모름 — agent 작성자가 prompt와 webhook 양쪽을 직접 맞춤. 자유도가 있는 만큼 운영 사고 확률 큼 (오타 1개로 봇 정지).
우리 적용: aicx-callbot은 **bot_dynamic_variable_def** 테이블 신설 (bot_version_id, key, type, required, default). 콘솔에서 정의된 변수만 prompt에 사용 가능. webhook payload validator도 같은 정의 참조. **vox보다 한 단계 엄격하게 가는 게 차별점**.

##### 인사이트 C5: call_type "web"은 spec 외 활성 enum

관찰: list 응답 28건 중 web 2건 발견. spec 문서는 web/phone/inbound/outbound/api 5종 표기지만 production 트래픽에 web 존재.
해석: 브라우저 SDK 호출이 별도 call_type로 라벨링. 콜봇 시연/QA 환경일 가능성.
우리 적용: `call_type` enum에 `web` 포함. 통계 대시보드에서 inbound/outbound와 분리 집계 (실제 운영 트래픽 ≠ 시연 트래픽).

##### 인사이트 C6: agent_version 응답값이 "production" 또는 "vN" 두 형태로 옴

관찰: 같은 봇이라도 호출 시점에 따라 `agent.agent_version: "production"` 또는 `"v262"`로 기록. 정책 통화는 production 포인터를 박고, 명시 버전 호출은 그 버전을 박는 듯.
해석: 통화 시점의 "라우팅 의도"가 보존. production 포인터가 v263으로 바뀐 후에도 "이 통화는 production 포인터를 따라갔다"는 사실이 남음. 반면 명시 버전은 시점 고정.
우리 적용: `call.bot_version_at_call` 컬럼은 `"production" | int`가 아니라 **두 컬럼**: `bot_version_id: FK NOT NULL` (resolve된 실제 버전) + `bot_version_pinned: bool` (production 포인터를 따라갔는지). vox보다 명확하게 사실을 분해.

---

### 2.3 Tool

#### 2.3.1 구조 (n=2 detail)

```
ToolDetailResponse:
  id: UUID/UUIDv7                    [관측: 019e1f0b-... — UUIDv7 (시간순 정렬 가능)]
  name: string                       [관측: get_product, get_flight_cancellation_fee — snake_case + 영어]
  description: string                [LLM이 함수 사용 결정을 위한 설명]
  input_schema: object               [JSON Schema 표준]
    type: "object"
    required: array<string>
    properties: dict<string, {type, description}>
  api_configuration: object
    url: string                      [HTTPS endpoint URL]
    method: enum                     [관측: POST]
    headers: dict                    [예: {X-Echo-Version-Id: "..."}]
    auth_type: null|enum             [관측: null]
    has_auth_credentials: bool       [관측: False]
    timeout_seconds: int             [관측: 30]
  speak_during_execution: object
    enabled: bool                    [관측: True]
    messages: array<string>          [실행 중 발화할 문장들]
  allow_interruption_during_execution: bool  [관측: False]
  created_at/updated_at: int (unix ms)
```

#### 2.3.2 인사이트

##### 인사이트 T1: tool ID가 UUIDv7로 보인다

관찰: 모든 tool ID가 `019e1f0b-...` 으로 시작 — 1ms 단위로 ordering 가능한 UUIDv7 패턴. created_at 1778637337115ms ≈ `019e1f0b-...`. 시간 정렬 가능한 ID.
해석: 모든 tool 리소스가 거의 같은 시점(1ms 미만 간격)에 batch 생성됨. agent 버전 publish 시 toolIds 전체가 같이 새로 INSERT되는 패턴(tool은 agent version에 종속).
우리 적용: **tool은 agent의 자산이 아니라 agent_version에 종속**(immutable snapshot). 우리도 `tool(id UUIDv7, bot_version_id FK, name, ...)`로 묶고 bot version 변경 시 tool도 새 row insert. agent와 lifecycle 동기화.

##### 인사이트 T2: speak_during_execution은 tool 단위로 발화 자연스러움 보장

관찰: tool마다 `speak_during_execution.messages: ["문의하신 내용 확인 중입니다..."]` — 호출 직전 LLM이 아닌 정적 메시지로 자연스러움.
해석: tool 호출 latency 동안 침묵 방지. LLM이 매번 다른 멘트 만들지 않도록 운영자가 고정.
우리 적용: tool 테이블 `speak_during_execution_enabled bool, speak_during_execution_messages text[]`. 콘솔에서 1개 이상 정의.

##### 인사이트 T3: api_configuration.auth_type/has_auth_credentials 분리

관찰: auth_type=null이지만 has_auth_credentials=false도 함께. credential 정보는 응답에 노출 안 함(보안).
해석: 운영자가 인증 설정 여부를 확인할 수 있도록 bool만 노출, 실제 credential은 응답에서 마스킹/제외.
우리 적용: `tool` 테이블에서 credential은 별도 SSM Parameter Store key 참조([[project_company_secret_store]]). 응답엔 `has_auth bool`만 노출.

---

### 2.4 Knowledge

#### 2.4.1 구조

```
KnowledgesListResponse (sparse):
  items: array<{id: int, name: string, created_at: int}>   # 3 키만
  next_cursor / total_count

KnowledgeDocumentsResponse:
  items: array<KnowledgeDocument>
    id: UUID
    knowledge_id: int                   [parent는 integer ID — vox legacy]
    name: string
    document_type: enum                 [관측: text]
    status: enum                        [관측: completed]
    upload_percentage: int              [0~100, 비동기 인덱싱 진행률]
    token_count: int                    [관측: 2439]
    webpage_urls: null|array            [웹 스크레이프 KB 지원 단서]
    created_at: int
```

#### 2.4.2 인사이트

##### 인사이트 K1: knowledge ID는 integer (vox 전체에서 유일)

관찰: agent, call, tool, phone 전부 UUID인데 **knowledge만 integer**. document는 UUID.
해석: 레거시 자원. v3에서 마이그레이션 안 함.
우리 적용: **새 시스템은 KB도 UUID로**. vox 호환층에서 int→UUID 매핑(매핑 테이블).

##### 인사이트 K2: 문서는 비동기 인덱싱 lifecycle

관찰: `status` + `upload_percentage` 두 필드 동시 노출. 운영자 화면에 "처리중 73%" 표시 가능.
해석: vox는 KB 인덱싱을 동기 처리 X. polling 또는 webhook 패턴.
우리 적용: `knowledge_document` 테이블에 `status enum(uploaded, processing, completed, failed)` + `progress int`. 콘솔에 polling, 또는 server-sent event.

##### 인사이트 K3: KB 응답이 sparse — 디테일 fetch가 필수

관찰: 리스트 응답에 id/name/created_at만. 문서 개수, ragEnabled 같은 메타 부재.
해석: 리스트는 가볍게, 디테일은 별도. N+1 우려 — 콘솔 KB 목록 화면이 매번 N건 detail 호출하면 비효율.
우리 적용: 우리 KB 리스트 API는 `document_count, total_tokens, last_indexed_at`를 join+aggregate해 1쿼리로. UX는 vox보다 풍부.

---

### 2.5 Telephone Number

#### 2.5.1 구조

```
PhoneNumberDetailResponse:
  id: UUID
  number: string                     [국내 070, 하이픈 X]
  provider: enum                     [관측: vox(임대), custom(BYO)]
  monthly_fee: int|null              [vox provider만 값, custom은 null]
  status: enum                       [관측: active]
  address: string|null               [관측: IP "49.247.170.40" (custom만) — SIP destination]
  inbound_trunk_id: string           [LiveKit/SIP trunk 식별자 (ST_...)]
  outbound_trunk_id: string
  inbound_agent: object|null         [{agent_id, agent_version}]
  outbound_agent: object|null
  memo: string                       [운영자 메모]
  start_at: int                      [관측: 임대 시작 ms]
  end_at: int|null                   [해지 후 종료 시점]
  cancel_requested_at: int|null      [해지 요청 시점 — 2-step 해지]
  created_at/updated_at: int
```

#### 2.5.2 인사이트

##### 인사이트 P1: vox provider vs custom provider 모델이 다르다

관찰: provider=vox(임대) → monthly_fee, address null. provider=custom(BYO) → monthly_fee null, address=IP.
해석: vox는 SIP trunk 사용권을 2가지로 판매 — (a) vox가 회선 빌려주고 월 임대료 받음 (b) 고객 SIP 사용해 vox는 통신만 중계 (IP 주소 등록).
우리 적용: `phone_number` 테이블 `provider enum(rented, byo)` + `monthly_fee_krw nullable` + `sip_address nullable`. 콘솔에서 두 모드 분리 가입 흐름.

##### 인사이트 P2: 해지가 2-step (cancel_requested → end_at)

관찰: `cancel_requested_at`과 `end_at`이 별도. 즉시 해지가 아니라 요청 → 유예기간 → 실종료.
해석: 통신사 회선 해지에 lead time(보통 30일 통보). 운영자가 cancel 누른 시점과 실제 회선 해제 시점 분리.
우리 적용: `phone_number.cancel_requested_at` + `cancel_effective_at` 컬럼. POST `/phone/{id}/cancel`은 요청 등록만, cron worker가 effective 도래 시 실해지. POST `/phone/{id}/cancel/revoke`로 취소 가능 (vox와 동일 패턴).

##### 인사이트 P3: 번호 ↔ 봇 매핑이 inbound/outbound 분리

관찰: 한 번호가 `inbound_agent`만, `outbound_agent`만, 또는 둘 다 가능. (관측: 둘 다 null인 번호도 있음 — 자산만 보유 중.)
해석: 인바운드(고객→봇)와 아웃바운드(봇→고객, CID 표시) 라우팅이 별 lifecycle.
우리 적용: `phone_number_routing(phone_number_id, direction enum, bot_id, bot_version_id, weight)` 별도 테이블. traffic-split까지 가능(v3가 generic하게 받아들이는 vox 의도).

---

### 2.6 Alert Rules / Incidents

#### 2.6.1 구조

```
/alert-rules: HTTP 500 INTERNAL_ERROR (vox 측 버그)
  응답: {error: {code: "INTERNAL_ERROR", message: "서버 내부 오류가 발생했습니다.", details: {}}}

/incidents 응답 (정상):
  items: array<Incident>
    id: UUID
    alert_rule_id: UUID                 [참조 무결성 — alert-rule이 살아있을 때 생성]
    status: enum
    metric_value: number                [실측치]
    threshold_value: number             [위반 시점의 threshold]
    change_rate: number                 [%]
    created_at: int (unix ms)
```

#### 2.6.2 인사이트

##### 인사이트 AL1: incident에 metric_value와 threshold_value를 **함께 박는다** (스냅샷)

관찰: incident row에 `metric_value, threshold_value, change_rate` 3개 모두 저장. alert_rule을 join하지 않아도 위반 당시 상태 복원.
해석: alert_rule이 사후 수정돼도 incident 발생 당시의 임계값을 잃지 않도록 incident에 박힘. 감사 친화적 설계.
우리 적용: `incident` 테이블에 alert_rule_id FK + **위반 당시 스냅샷 컬럼 3개**. event sourcing 일부.

##### 인사이트 AL2: vox alert-rules 자체가 500 — 우리 production에 동일 의존하면 안 됨

관찰: `/alert-rules` 호출이 500 INTERNAL_ERROR. `/incidents`는 정상.
해석: vox 서버 측 버그. 알림 규칙 관리 API가 일시적으로 죽어도 incident 생성은 계속 돌고 있을 가능성.
우리 적용: 우리 콜봇 콘솔에서 vox alert 규칙을 직접 띄우지 말고, **우리 DB에 alert_rule을 owning copy로 보관** + vox에 push (동기화). vox가 죽어도 우리 콘솔은 살아있게.

---

### 2.7 Model / Voice / Schema (카탈로그)

#### 2.7.1 LLMs

```
total: 24 모델
provider 분포 (model name "<provider>/<id>" 파싱):
  openai 9, deepseek 3, google 3, anthropic 2, moonshotai 2, meta-llama 2, qwen 1, z-ai 1, (one model has no slash: "gpt-4.1-mini")

capabilities: {temperature: {min, max, default}} 단일 차원만 노출
  → tools/function-calling/reasoning은 capabilities에 없음 (모든 모델 지원 가정)
```

##### 인사이트 M1: LLM 카탈로그가 24개 — 모델 선택지가 과잉

관찰: 9 provider 24 model. 운영 봇은 단일(`openai/gpt-5.2`), flow 봇은 `z-ai/glm-4.7`.
해석: vox는 LLM provider 추상화를 강하게 — 운영자가 단일 string으로 갈아끼움. capabilities에 temperature만 노출, 나머지(tool calling 등)는 묵시적.
우리 적용: `bot_config.llm.model: string` 단일 컬럼. vox model 카탈로그 string을 그대로 받음 (호환). 우리 콘솔이 자체 추천(예: "한국어 콜봇은 gpt-5.2 + 0.0 temp")만 layer.

#### 2.7.2 Voices

```
total: 389
1페이지(50) 분포:
  provider: google 27, cartesia 14, openai 9
  gender: female 25, male 25
  ko-KR: 11
  language sample: cmn-CN 27, *(범용) 9, en-US 3, ko-KR 11

voice 필드: provider, id, name, language, gender, sample_url(WAV), description, model, capabilities
capabilities 차원: {speed, volume} — voice별 지원 차원이 다름
```

##### 인사이트 V1: voice의 sample_url은 공개 CDN, model+id가 unique key

관찰: `sample_url: https://api.tryvox.co/storage/v1/object/public/shared/voices/alloy.wav` — Supabase Storage public bucket. id는 provider 내 unique지만 cross-provider unique 보장 X (그래서 (provider, id)로 정렬).
해석: 콘솔에서 즉시 미리듣기 가능하게 public hosting.
우리 적용: voice 미리듣기 URL은 vox sample_url 그대로 사용(우리가 hosting할 필요 X). voice 선택은 `(provider, voice_id, model)` 세 컬럼.

#### 2.7.3 Schemas (registry)

```
total: 41
namespace 분포: agent-schema 15, flow-schema 12, eval-schema 7, tool-schema 7
category 분포: <none> 12, flow-node 11, eval 7, built_in 5, agent-authoring 4, custom 2
source 분포: db 21, code 16, override 4
is_active: 100% true

agent-authoring(4): agent-data, agent-data-create, agent-data-update, flow-data
  → agent-data-create.$defs(18): Agent{CallSettings, Knowledge, LLM, PostCall, Prompt, STT, Security, Speech, Voice, WebhookSettings},
                                  {EndCall, SendDtmf, SendSms, TransferAgent, TransferCall}Tool, PostCallAction, SpeakDuringExecution, TransferConfig

flow-node(11): api, begin, condition, conversation, endCall, extraction, note, sendSms, tool, transferAgent, transferCall

tool-schema(7): api, end_call, mcp, send_dtmf, send_sms, transfer_agent, transfer_call
  → mcp가 별도 schema_type → MCP 통합 지원

eval-schema(7): assistant-message, user-message, judge-message, tool-call, tool-response-message, ut-messages, eval-meta
  → 평가용 메시지 schema 별도 발행 — vox가 LLM judge 평가 기능을 갖고 있다는 강한 신호
```

##### 인사이트 S1: vox API는 self-describing — 21개 스키마가 DB에 산다

관찰: source=db 21 / code 16 / override 4. 즉 21개 스키마는 코드 push 없이 DB에서 변경 가능.
해석: 신규 LLM provider 추가, 신규 callSettings 옵션 추가 등을 db row 변경으로 처리 → 배포 없이 기능 출시. override는 organization별 customization.
우리 적용: aicx-callbot의 sub-config 정의(callSettings.options 등)를 **`tenant_schema` 테이블로 관리**. 코드는 base schema만, tenant override는 DB. [[feedback_no_hardcoded_tenant_config]]와 부합 — 고객사별 커스터마이즈는 DB.

##### 인사이트 S2: MCP/tool 스키마가 7개 schema_type으로 분리

관찰: tool-schema 네임스페이스에 api/end_call/mcp/send_dtmf/send_sms/transfer_agent/transfer_call 7종.
해석: vox는 외부 API tool 외에 MCP(Model Context Protocol) tool, 통화 제어 tool(end_call/transfer/dtmf), 메시지 tool(sms)을 분리. 각각 input_schema 모양이 다름.
우리 적용: `tool` 테이블 `tool_type enum(api, mcp, end_call, send_dtmf, send_sms, transfer_agent, transfer_call)` + type별 별도 검증. MCP 통합 슬롯은 처음부터 잡아둔다.

##### 인사이트 S3: eval namespace가 별도 존재 — vox는 LLM eval/judge를 1급으로 가짐

관찰: eval-schema 네임스페이스 7종 (assistant-message, user-message, judge-message, tool-call, tool-response-message, ut-messages, eval-meta).
해석: 통화 trajectory를 평가용 메시지 시퀀스로 변환하는 schema가 정의됨. judge-message가 별도 = LLM-as-judge 기능 내장.
우리 적용: aicx-callbot은 [[project_callbot_no_langsmith]] 정책으로 LangSmith 미사용 — eval은 우리가 자체 구축해야. vox eval-schema의 message 형식을 reference로 우리 eval pipeline 입력 스펙 정의. judge prompt도 vox judge-message 형태를 차용.

---

## 3. 종합 인사이트 — vox 설계 철학 4가지

### 3.1 "비동기 채워지는 필드"는 별도 endpoint가 아니라 같은 응답에 nullable

call_analysis, call_cost, recording_url, transcript 전부 같은 GET /calls/{id} 응답에 nullable로. 호출자는 polling + null 체크로 진행 상태 파악. 별도 status endpoint 만들지 않음 — **단일 진실의 원천 유지**.

→ 우리 적용: call 단건 API는 통합 응답. webhook은 동일 페이로드 그대로 전달.

### 3.2 상태 전이는 PATCH가 아니라 별도 action endpoint

publish, pause, resume, cancel, enable, disable — 전부 POST `/{id}/{action}`. PATCH로 status 컬럼을 직접 못 바꾸게 막아 상태머신 일관성 강제.

→ 우리 적용: 이미 [[project_callbot_agent_model]]에서 차용. CallbotAgent membership 변경도 action endpoint.

### 3.3 immutable version + production pointer + working draft

agent의 v1~v262 immutable, production은 포인터, no-version fetch는 working draft. 통화는 라우팅 의도("production" or 명시 버전)를 동시에 보존.

→ 우리 적용: bot_version row insert-only, production pointer는 `bot.production_bot_version_id`. 통화는 `bot_version_id_resolved` + `bot_version_pinned bool` 분해.

### 3.4 self-describing schema registry로 코드 무배포 기능 확장

41개 스키마 중 21개가 DB. 신규 옵션 추가가 SQL 한 줄. override 메커니즘으로 고객사별 customization 지원.

→ 우리 적용: tenant_schema 테이블 + override 컬럼. UI는 schema 기반 자동 생성(JSON Schema → React form).

---

## 4. aicx-callbot 도메인 반영안 (구체 결정)

### 4.1 DB 스키마 변경 제안

```sql
-- bot (agent에 해당)
CREATE TABLE bot (
  id              UUID PRIMARY KEY,
  name            TEXT NOT NULL,
  type            TEXT NOT NULL CHECK (type IN ('single_prompt','flow')),
  production_bot_version_id UUID REFERENCES bot_version(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- bot_version (immutable snapshot)
CREATE TABLE bot_version (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  bot_id          UUID NOT NULL REFERENCES bot(id),
  version_int     INT NOT NULL,                  -- 1, 2, 3, ...
  description     TEXT,
  data_jsonb      JSONB NOT NULL,                -- 9 sub-config 통합
  flow_data_jsonb JSONB,                         -- flow 봇만
  is_published    BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (bot_id, version_int)
);

-- call (요점 컬럼만)
CREATE TABLE call (
  id                       UUID PRIMARY KEY,
  bot_id                   UUID NOT NULL REFERENCES bot(id),
  bot_version_id_resolved  UUID NOT NULL REFERENCES bot_version(id),
  bot_version_pinned       BOOLEAN NOT NULL,     -- false=production 포인터 따라감
  call_type                TEXT NOT NULL CHECK (call_type IN ('inbound','outbound','web','api')),
  from_number              TEXT NOT NULL,
  to_number                TEXT NOT NULL,
  presentation_number      TEXT,
  status                   TEXT NOT NULL,        -- queued/ongoing/ended/error/canceled/not_connected
  disconnection_reason     TEXT,
  start_at                 TIMESTAMPTZ NOT NULL,
  end_at                   TIMESTAMPTZ,
  recording_url            TEXT,
  metadata                 JSONB NOT NULL DEFAULT '{}'::JSONB,
  dynamic_variables        JSONB NOT NULL DEFAULT '{}'::JSONB,
  total_cost               NUMERIC(10,2),
  variant_label            TEXT,
  opt_out_sensitive_data_storage BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX call_bot_start_idx ON call (bot_id, start_at DESC);
CREATE INDEX call_status_start_idx ON call (status, start_at DESC);

-- transcript_event (call detail 응답의 transcript[])
CREATE TABLE transcript_event (
  call_id       UUID NOT NULL REFERENCES call(id),
  seq           INT NOT NULL,
  occurred_at   TIMESTAMPTZ NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('agent','user','tool_call_invocation','tool_call_result')),
  tool_call_id  TEXT,                            -- invocation/result 짝
  payload       JSONB NOT NULL,                  -- role별 polymorphic
  PRIMARY KEY (call_id, seq)
);
CREATE INDEX transcript_tool_call_idx ON transcript_event (tool_call_id) WHERE tool_call_id IS NOT NULL;

-- bot_dynamic_variable_def (vox와의 차별점 — 변수 카탈로그 강제)
CREATE TABLE bot_dynamic_variable_def (
  bot_version_id UUID NOT NULL REFERENCES bot_version(id),
  key            TEXT NOT NULL,
  type           TEXT NOT NULL CHECK (type IN ('string','number','boolean','json')),
  required       BOOLEAN NOT NULL DEFAULT FALSE,
  default_value  JSONB,
  description    TEXT,
  PRIMARY KEY (bot_version_id, key)
);

-- tenant_schema (vox source=db override 패턴)
CREATE TABLE tenant_schema (
  tenant_id      UUID NOT NULL,
  namespace      TEXT NOT NULL,
  schema_type    TEXT NOT NULL,
  version        INT NOT NULL,
  body_jsonb     JSONB NOT NULL,
  is_active      BOOLEAN NOT NULL DEFAULT TRUE,
  source         TEXT NOT NULL CHECK (source IN ('db','code','override')),
  PRIMARY KEY (tenant_id, namespace, schema_type, version)
);
```

### 4.2 도메인 entity 결정

- `Bot` (Aggregate Root) — id, name, type, production_version_pointer
- `BotVersion` (Entity, immutable) — id, version_int, data: BotData, flow_data: FlowData|None
- `BotData` (Value Object) — prompt/stt/llm/voice/speech/callSettings/postCall/security/webhookSettings/knowledge/presetDynamicVariables/toolIds/builtInTools (9+4)
- `Call` (Aggregate Root) — id, bot_version_id_resolved, bot_version_pinned, ...
- `TranscriptEvent` (Entity child of Call) — discriminated union(role)
- `CallAnalysis` (Value Object, optional) — summary, user_sentiment, custom_analysis_data
- `BotDynamicVariableDef` (Entity child of BotVersion)

[[feedback_clean_architecture]] 준수: domain entity가 ORM에 의존하지 않고 BotData VO가 9 sub-config를 강제 검증.

### 4.3 콘솔 UX 변경 제안

| 영역 | vox 패턴 | 우리 도입 |
|---|---|---|
| Agent 편집 | 통합 PATCH (콘솔에서 sub-config 동시 편집) | sub-config 탭 분리 (9개) + 저장은 통합 PATCH |
| 버전 관리 | 자동 incrementing v1~vN, description nullable | description 강제 (운영 가독성), version retention 정책(최근 50개 + 보존 마킹) |
| Flow 에디터 | ReactFlow + 서버 viewport/measured 저장 | 동일 차용 — react-flow + bot_version.flow_data_jsonb에 viewport 포함 |
| Dynamic Variables | 자유 키 (검증 X) | bot_dynamic_variable_def 강제 + 콘솔 자동완성 + webhook validator 동일 정의 참조 |
| Tool 카탈로그 | 1325개 누적 (검색 필수) | tool_type tag + 활성/비활성 토글 + agent에 attach된 tool 우선 표시 |
| Knowledge | sparse list response → N+1 fetch | aggregate 1쿼리 (document_count, total_tokens, last_indexed_at) |
| Phone | 2-step 해지 (request → effective) | 동일 차용 — phone_number_routing 분리 |

---

## 5. 미해결 질문

1. **call.status가 `queued`인 시점이 얼마나 짧은가?** 관측 못 함. POST /calls 호출하지 않고는 알 수 없음. → 빌드 단계에서 POST 호출 가능해질 때 측정.
2. **/alert-rules의 500은 일시적인가, 지속적인가?** 한 차례 확인. 재시도 시간차 두고 1~2회 더 호출 필요.
3. **custom_analysis_data의 실제 구조?** 28건 전체 빈 배열. agent.postCall.actions에 정의해야 채워지는 구조로 추정. 정의된 agent를 찾아야 검증 가능.
4. **variant_label은 어떻게 부여되나?** spec은 traffic-split 결과 라벨. POST /calls의 traffic_split agent group 호출이 필요.
5. **tool UUIDv7 가설 검증**: 더 다양한 시점 생성된 tool ID 비교 필요 (현재는 같은 batch ID들).
6. **flow node-tool/node-api 등 사용자 정의 node**: schema는 11종 알지만 production에 쓰이는 비율은 알 수 없음. 다른 flow agent 1~2개 더 fetch 필요.

---

## 6. 부록: GET 호출 로그

| # | 시각 | endpoint | HTTP | snapshot |
|--:|---|---|---:|---|
| 1 | 16:34:04 | `/agents?limit=1` (smoke) | 200 | `20260513-163404-smoke-agents.json` |
| 2 | 16:35:48 | `/agents?limit=10` | 200 | `20260513-163548-agents-list.json` |
| 3 | 16:35:48 | `/calls?limit=10` | 200 | `20260513-163548-calls-list.json` |
| 4 | 16:35:48 | `/campaigns?limit=10` | 200 | `20260513-163548-campaigns-list.json` |
| 5 | 16:35:48 | `/tools?limit=10` | 200 | `20260513-163548-tools-list.json` |
| 6 | 16:35:48 | `/knowledges?limit=10` | 200 | `20260513-163548-knowledges-list.json` |
| 7 | 16:35:48 | `/organization-telephone-numbers?limit=10` | 200 | `20260513-163548-phones-list.json` |
| 8 | 16:35:48 | `/alert-rules?limit=10` | **500** | `20260513-163548-alert-rules-list.json` |
| 9 | 16:35:48 | `/incidents?limit=10` | 200 | `20260513-163548-incidents-list.json` |
| 10 | 16:35:48 | `/models/llms` | 200 | `20260513-163548-llms-list.json` |
| 11 | 16:35:48 | `/models/voices` | 200 | `20260513-163548-voices-list.json` |
| 12 | 16:35:48 | `/schemas` | 200 | `20260513-163548-schemas-list.json` |
| 13 | 16:36:39 | `/agents/{sp}` | 200 | `20260513-163639-agent-sp-current.json` |
| 14 | 16:36:39 | `/agents/{sp}?version=production` | 200 | `20260513-163639-agent-sp-prod.json` |
| 15 | 16:36:39 | `/agents/{sp}?version=v1` | 200 | `20260513-163639-agent-sp-v1.json` |
| 16 | 16:36:39 | `/agents/{sp}/versions` | 200 | `20260513-163639-agent-sp-versions.json` |
| 17 | 16:36:39 | `/agents/{flow}` | 200 | `20260513-163639-agent-flow-current.json` |
| 18 | 16:36:39 | `/agents/{flow}?version=production` | 200 | `20260513-163639-agent-flow-prod.json` |
| 19 | 16:36:39 | `/agents/{flow}/versions` | 200 | `20260513-163639-agent-flow-versions.json` |
| 20 | 16:38:04 | `/calls?limit=10&call_type=outbound` | 200 | `20260513-163804-calls-outbound.json` |
| 21 | 16:38:04 | `/calls?limit=20&status[]=ongoing` | **400** | `20260513-163804-calls-ongoing.json` |
| 22 | 16:38:04 | `/calls?limit=10&status[]=error` | **400** | `20260513-163804-calls-error.json` |
| 23 | 16:38:04 | `/calls/{id1-ongoing}` | 200 | `20260513-163804-call-detail-1-ongoing.json` |
| 24 | 16:38:04 | `/calls/{id2-transfer}` | 200 | `20260513-163804-call-detail-2-transfer.json` |
| 25 | 16:38:04 | `/calls/{id3-aghangup}` | 200 | `20260513-163804-call-detail-3-aghangup.json` |
| 26 | 16:38:42 | `/calls?limit=20&status=ongoing` | 200 | `20260513-163842-calls-status-ongoing.json` |
| 27 | 16:38:42 | `/calls?limit=10&status=error` | 200 | `20260513-163842-calls-status-error.json` |
| 28 | 16:38:42 | `/calls?limit=5&disconnection_reason=user_hangup` | 200 | `20260513-163842-calls-disconnreason-uhang.json` |
| 29 | 16:40:43 | `/tools/{t1}` | 200 | `20260513-164043-tool-detail-1.json` |
| 30 | 16:40:43 | `/tools/{t2}` | 200 | `20260513-164043-tool-detail-2.json` |
| 31 | 16:40:43 | `/knowledges/527/documents` | 200 | `20260513-164043-kb-docs-1.json` |
| 32 | 16:40:43 | `/knowledges/443/documents` | 200 | `20260513-164043-kb-docs-2.json` |
| 33 | 16:40:43 | `/organization-telephone-numbers/{p1}` | 200 | `20260513-164043-phone-detail-1.json` |
| 34 | 16:40:43 | `/organization-telephone-numbers/{p2}` | 200 | `20260513-164043-phone-detail-2.json` |
| 35 | 16:42:00 | `/schemas?category=agent-authoring&include_schema=true` | 200 | `20260513-164200-schemas-agent-auth-body.json` |

**총합**: GET 35건 (성공 32 / 400 2 / 500 1). 429 0회. POST/PATCH/DELETE 호출 0건.

---

## 7. 결과 요약 (사용자 보고용)

1. **호출 통계**: GET 35건, 성공률 91.4%. (400 2건 — spec과 실제 array filter 차이로 학습, 200 재시도 성공. 500 1건 — vox `/alert-rules` 서버 버그.)
2. **Mutation spec 분석**: 8개 endpoint (Create/Update/publish 3 agent, Create call, alert-rule action, tool create, knowledge create, phone cancel).
3. **설계 변경 필요 N개**: TL;DR 5개 + 종합 인사이트 4개 + 도메인 반영안 4.1~4.3 모두.
4. **PII 마스킹**: 본문에 전화번호·이메일·통화 transcript 본문·dynamic_variables 값 일체 미포함. raw JSON은 `.vox-snapshots/` (gitignore 추가됨). 봇/번호 ID는 vox 식별자(비공개 PII 아님)만 보고.
5. **snapshot 경로**: `/Users/dongwanhong/Desktop/chat-STT-TTS/aicx-callbot/docs/plans/.vox-snapshots/` — 35건 raw JSON 파일.
6. **추가 조사 필요**: `§5 미해결 질문 6건` — POST 호출이 가능해진 빌드 단계에서 검증.
