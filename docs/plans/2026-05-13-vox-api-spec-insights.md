# vox v3 API 명세 기반 인사이트 — DB·도메인·콘솔 설계 입력

> 출처: `https://docs.tryvox.co/api-reference/v3/openapi.json` (vox v3 OpenAPI 원본, 815KB)
> 보조: `https://docs.tryvox.co/api-reference/v3/calls/통화-조회` (Call 단건 조회 문서)
> 작성: 2026-05-13
> 선행 문서: `VOX_AGENT_STRUCTURE.md` (2026-05-11, llms.txt 기반 사이드바 역설계)
> 본 문서의 차이점: 사이드바가 아니라 **OpenAPI 스펙 원본**을 직접 읽고 추출한 스키마/enum/필드/상태머신을 기반으로, aicx-callbot의 DB·도메인 엔티티·콘솔 설계에 옮겨야 할 결정사항을 도출한다.

---

## 0. 한 줄 결론

> **vox v3는 "Call(통화)이 최상위, Agent(자산)는 버전 참조로 nested, 모든 lifecycle 변경은 별도 endpoint(pause/resume/cancel/publish)로 분리, PATCH는 omit=유지·null=해제, 시간은 epoch ms, 페이지네이션은 cursor"** — 이 다섯 가지를 우리 콜봇도 그대로 차용한다.

---

## 1. v3 endpoint 전체 카탈로그 (54개)

| 영역 | 개수 | 핵심 엔드포인트 |
|---|---|---|
| Calls | 3 | `POST /calls`, `GET /calls`, `GET /calls/{id}` |
| Campaigns | 7 | CRUD + pause/resume/cancel |
| Telephone Numbers | 9 | available / purchase / register(SIP) / 조직보유 CRUD / agent 매핑 / SIP 설정 / 해지·해지취소 |
| Alert Rules | 13 | CRUD + condition/channels/schedule 부분 PATCH + enable/disable/pause/resume + test-notification + incidents 조회 |
| Incidents | 1 | `GET /incidents` |
| Tools | 5 | CRUD + 목록 |
| Schemas | 2 | `GET /schemas`, `GET /schemas/{ns}/{type}` (레지스트리) |
| Knowledges | 6 | knowledge CRUD + 문서 CRUD |
| Agents | 8 | CRUD + 버전 생성·목록·publish |
| Models | 2 | `GET /models/llms`, `GET /models/voices` |

**숨겨진 함의:**
- **action endpoint 분리 패턴**: 상태 전환(`/pause`, `/resume`, `/cancel`, `/publish`, `/enable`, `/disable`)은 별도 POST endpoint로 분리. PATCH로 status 필드를 직접 못 바꾸게 막아 상태머신 일관성 보장.
- **부분 PATCH 분리 패턴**: alert-rule만 봐도 `PATCH /alert-rules/{id}` 외에 `/condition`, `/channels`, `/schedule` 3개 sub-PATCH가 있음. 큰 도메인 객체의 일부만 갱신하는 작업이 자주 일어나면 sub-resource로 분리.
- **schema registry**: `/schemas` endpoint가 별도로 있음. 레지스트리 URI (`voxai://agent-schema/prompt/v1` 같은) 패턴으로 스키마 자체를 버전 관리 — 향후 다언어 SDK 자동 생성에 대비.

→ **우리 적용**: Bot pause/resume, 캠페인 status 변경, Agent 버전 publish 같은 **상태 전이는 PATCH가 아니라 별도 action endpoint**로. 도메인 entity의 invariant를 application service에서 강제하기 쉬워짐.

---

## 2. 공통 컨벤션 (전 endpoint 공통)

| 항목 | 규칙 | 우리 적용 |
|---|---|---|
| 인증 | `Authorization: Bearer <조직 API key>` | tenant별 발급, scope는 organization 단위 |
| 시간 | `*_at`은 **unix milliseconds(integer)**, 10·11자리 unix sec도 자동 정규화 | DB는 `TIMESTAMPTZ`, API 경계에서 ms로 직렬화 |
| 페이지네이션 | **cursor 기반**: `limit`(1~100, 기본 50) + `cursor` + `sort_order` | offset 금지. 응답에 `next_cursor` |
| 필드 케이스 | 기본 `snake_case`, **단** `agent.data` 하위(`callSettings`, `toolIds`, `presetDynamicVariables`, `webhookSettings`, `postCall`, `builtInTools`)는 **레지스트리 호환성**을 위해 `camelCase` 유지 | 우리는 일관성 우선 → 전부 snake_case 권장 (vox 호환층만 매핑) |
| PATCH 의미론 | **omit=기존값 유지**, **null=해제(nullable column)**, **빈 `{}`=400** | minProperties=1 검증, partial update entity 사용 |
| 배열 필터 | `agent_id[]`, `status[]` 등 **반복 가능 query param** | FastAPI `List[X] = Query(None)` |
| 에러 모델 | `{error: {code, message, details: {field, reason}}}` | 도메인 에러 → HTTP 매핑 미들웨어 단일화 |
| 리소스 ID | 대부분 UUID, **knowledge만 integer**(public ID), tool은 string | 우리는 전부 UUID 권장 (knowledge integer는 vox legacy) |

→ **우리 적용**: 위 표를 `docs/plans/2026-05-12-deploy-infra-and-db-design.md`의 "API convention" 절로 흡수.

---

## 3. Call (통화) — `CreateCallRequest` / `CallResponse`

### 3-1. 필드 구조

```python
CreateCallRequest:
    from_number: str          # required, 국내 번호, 하이픈 X (libphonenumber 검증)
    to_number: str            # required
    agent: AgentMapping|null  # {agent_id, agent_version="current"} — 생략 시 발신번호의 traffic-split 라우팅
    metadata: object          # 자유, 응답에 그대로 echo
    dynamic_variables: object # 프롬프트 {{변수}} 치환
    presentation_number: str|null  # 조직 사전 승인 번호

CallResponse:
    id: UUID
    agent: AgentMapping       # {agent_id, agent_version}
    call_type: enum           # web | phone | inbound | outbound | api
    from_number/to_number/presentation_number: str|null
    status: enum              # queued | ongoing | ended | error | canceled | not_connected
    disconnection_reason: enum|null  # 17개 사유 (user_hangup, agent_hangup, dial_no_answer, ...)
    start_at/end_at: int|null # unix ms
    recording_url: str|null
    metadata/dynamic_variables: object
    call_analysis: {summary, user_sentiment, custom_analysis_data}|null  # 분석 완료 전 null
    call_cost: {total_cost: "KRW decimal string"}|null                   # 계산 완료 전 null
    variant_label: str|null   # traffic split 라벨
    opt_out_sensitive_data_storage: bool  # true면 transcript/recording/analysis 일괄 null
    transcript: array|null    # role 3종(agent/user, tool_call_invocation, tool_call_result) 통합 timeline
```

### 3-2. 도출 인사이트 (DB·도메인)

1. **Call은 Agent를 "소유"하지 않고 "참조"한다 (`{agent_id, agent_version}` nested).** 우리 `CallbotAgent` 모델([[project_callbot_agent_model]])과 일치. 단 vox는 1통화=1agent, 우리는 main+sub 멀티 봇 → 확장 시 `agents: [{bot_id, bot_version, role}]` 배열.
2. **분석/비용은 비동기 채워짐.** `call_analysis: null`, `call_cost: null` 허용. 통화 lifecycle ≠ 분석 lifecycle. → `call` 테이블과 `call_analysis` 테이블 분리, 후처리 큐.
3. **녹취/STT/분석 일괄 마스킹은 단일 플래그.** `opt_out_sensitive_data_storage: true` → 3개 필드 동시 null. → 단순 boolean으로 PII 처리 일원화. 마스킹보다 비저장이 깔끔.
4. **decimal은 string 직렬화.** `call_cost.total_cost: "123.45"`. JS Number 정밀도 회피. → 우리도 `Money` VO + string 직렬화.
5. **상태머신은 좁게(6), 종료사유는 풍부하게(17).** `status`와 `disconnection_reason`을 **별도 컬럼**으로. 운영 분석은 사유에서 나온다.
6. **`variant_label`로 A/B 실험 라벨링.** 컬럼 하나로 GROUP BY 분석 가능. → MVP 단계부터 컬럼 잡아두면 비용 거의 0, 효용 큼.
7. **전화번호 3종.** `from_number`(실발신), `to_number`(수신), `presentation_number`(CID 표시) 분리. 발신 콜봇에서 대표번호 표시 필수.
8. **`metadata` vs `dynamic_variables` 분리.** 정적 메타(테넌트 부착) vs 런타임 변수(프롬프트 슬롯). → JSONB 2컬럼 분리. 합치면 디버깅 지옥.
9. **transcript는 통합 timeline.** 발화 + tool 호출 + tool 응답이 한 array. → `transcript_event(call_id, seq, occurred_at, type, role, content jsonb)` 단일 테이블.

### 3-3. 목록 조회 query 파라미터

```
GET /calls
  ?agent_id[]=...
  &status[]=ongoing&status[]=ended
  &call_type[]=phone
  &disconnection_reason[]=user_hangup
  &call_from[]=07011112222
  &call_to[]=01012345678
  &start_at_after=1776000000000   # unix ms 포함
  &start_at_before=1776999999999
  &sort_order=desc                # 기본 desc
  &cursor=...&limit=50
```

→ **우리 적용**: 거의 그대로 차용. SQL 인덱스는 `(agent_id, start_at DESC)`, `(status, start_at DESC)` 복합 인덱스.

---

## 4. Agent — 자산 모델의 결정판

### 4-1. CRUD + 버전 endpoint

```
POST   /agents                              # 생성
GET    /agents                              # 목록
GET    /agents/{id}?version=current|production|v3  # 단건 (버전 스냅샷 가능)
PATCH  /agents/{id}                         # 수정 (current 변경)
DELETE /agents/{id}                         # 삭제
POST   /agents/{id}/versions                # 버전 스냅샷 생성
GET    /agents/{id}/versions                # 버전 목록
POST   /agents/{id}/versions/{version}/publish  # production 게시
```

### 4-2. Agent.data 구조 (`AgentDataCreate` / `AgentDataResponse`)

```
agent.data
├─ prompt:        {prompt, firstLine, firstLineType, pauseBeforeSpeakingSeconds, isFirstMessageInterruptible}
├─ stt:           {languages[], speed: low|medium|high}
├─ llm:           {model, temperature, thinkingBudget, reasoningEffort}
├─ voice:         {id, provider, model, speed, volume, language, temperature}
├─ speech:        {responsiveness, boostedKeywords}
├─ callSettings:  {backgroundMusic, backgroundMusicVolume, noiseCancellation,
│                  activationThreshold, callTimeoutInSeconds=900,
│                  silenceCallTimeoutInSeconds=30, ringDurationInSeconds=30,
│                  dtmfTerminationEnabled, dtmfTerminationKey, dtmfTimeoutSeconds}
├─ postCall:      {actions: [{name, type, isNullable, description, enumOptions}]}
├─ security:      {optOutSensitiveDataStorage}
├─ webhookSettings: {callDataWebhookUrl, inboundCallWebhookUrl, webhookVersion: v1|v2}
├─ knowledge:     {ragEnabled, knowledgeIds[]}
├─ presetDynamicVariables: {key: string, ...}  # 사전 정의 변수
├─ toolIds:       [UUID]                       # 연결된 custom tool
└─ builtInTools:  [oneOf: EndCall|TransferCall|TransferAgent|SendSms|SendDtmf]
```

추가로 최상위에:
- `type: single_prompt | flow` — flow면 `flow_data`(그래프) 필수
- `production_version: "v3"|null` — 현재 게시 버전
- `version: AgentVersionMeta|null` — 스냅샷 조회 시만 populated

### 4-3. 도출 인사이트 (도메인 엔티티)

#### A. 자산 vs 운영 설정의 경계가 명확

vox가 `agent.data` 안에 묶은 것:
- **자산 후보** (재사용·라이브러리화 가능): `prompt`, `knowledge.knowledgeIds`, `toolIds`, `builtInTools`
- **운영 파라미터** (봇당 1세트로 굳음): `llm`, `voice`, `stt`, `speech`, `callSettings`, `webhookSettings`, `security`, `postCall`

→ **우리 적용**: `VOX_AGENT_STRUCTURE.md`의 "4 자산 + 평면 설정" 분류와 정확히 맞물림. 자산은 별도 테이블(prompt, knowledge, tool), 운영 설정은 bot row의 JSONB 컬럼 또는 1:1 자식 테이블.

#### B. 버전(version) 시맨틱은 단순한 게 답

- 식별자: `current | production | v{n}` (정규식 `^(current|production|v[1-9][0-9]*)$`)
- `current`: 작업중인 latest
- `production`: 현재 운영 게시본
- `v{n}`: 불변 스냅샷

→ **우리 적용**: 같은 enum 그대로 차용. `bot_version` 테이블: `(bot_id, version_label, snapshot_data jsonb, is_production, created_at)`. 통화 row는 `(bot_id, bot_version)` 쌍 FK.

#### C. publish는 별도 action + 이전 버전 audit 남김

```
POST /agents/{id}/versions/{version}/publish
→ {agent_id, production_version, previous_production_version}  # 롤백/감사 용
```

→ **우리 적용**: `publish_bot_version()` use case에서 이전 production을 응답에 같이 반환. 롤백 UX 핵심.

#### D. PATCH 시맨틱이 일관됨

- 빈 body 거부 (400)
- 필드 omit = 기존값 유지
- 필드 null = 해제 (nullable만)

→ **우리 적용**: Pydantic `model_dump(exclude_unset=True)` + `None` sentinel 패턴. **반드시** 빈 body는 400으로 거부 (실수 방지).

#### E. tools = custom(=API webhook) + built-in(=5종 시스템 액션)

| Tool 종류 | 정의 | 구조 |
|---|---|---|
| custom | `POST /tools`로 생성, agent에서 `toolIds[]`로 연결 | `{name, description, input_schema(JSON Schema), api_configuration(url/method/auth), speak_during_execution, allow_interruption_during_execution}` |
| built-in | 코드 레벨 도구, `builtInTools[]`에 inline | `EndCallTool / TransferCallTool / TransferAgentTool / SendSmsTool / SendDtmfTool` |

→ **우리 적용**:
- custom tool은 결국 **에이전트에서 호출하는 외부 HTTP API**. 명세를 JSON Schema(`input_schema`)로 받아 LLM function calling으로 그대로 노출.
- built-in tool은 **콜봇 코어의 시스템 액션**(통화 종료/전환/SMS/DTMF). 코드에 박혀 있어야 함, 콘솔에서는 enable/disable만.
- 이 구분이 우리 `ToolType` enum의 핵심: `custom_api | end_call | transfer_call | transfer_agent | send_sms | send_dtmf`

#### F. callSettings의 10개 운영 파라미터는 거의 기성 산업표준

특히 다음 값들은 vox가 운영하며 튜닝한 합리적 기본값으로 보임:
- `callTimeoutInSeconds: 900` (15분 통화 최대치)
- `silenceCallTimeoutInSeconds: 30` (무음 30초면 종료)
- `ringDurationInSeconds: 30` (응답없음 30초)
- `activationThreshold: 0.55` (VAD 임계값)
- `noiseCancellation: "bvc"` (background voice cancellation)

→ **우리 적용**: MVP 기본값으로 그대로 채택. 콘솔에서 봇별 override 가능하도록만.

#### G. firstLineType — 첫 발화 정책 3종

```
userFirst        - 사용자 발화 대기 (inbound 통화 자연스러움)
aiFirstStatic    - 고정 문장 (firstLine 필드 필수)
aiFirstDynamic   - LLM이 생성 (default)
```

→ **우리 적용**: 인바운드/아웃바운드별로 기본값 달리. 아웃바운드는 `aiFirstStatic`이 무난 (스크립트 통제).

#### H. `postCall.actions` = 구조화 추출 + 후속 처리

```
PostCallAction:
    name: str           # "주문번호", "고객의도"
    type: "string"|"enum"|"boolean"|"number"
    isNullable: bool
    enumOptions: [str]|null  # type=enum일 때
    description: str    # LLM에게 줄 추출 지시
```

→ **우리 적용**: 통화 종료 후 LLM이 transcript에서 정해진 스키마로 변수 추출. `call_extracted_variables` 테이블 또는 `call_analysis.custom_analysis_data` JSONB.

---

## 4-bis. 에이전트 "생성" 흐름의 깊은 인사이트 (추가)

여기까지가 agent CRUD의 전반이고, 이번 절은 **"새 봇이 어떻게 태어나는가"**에 집중해 우리 콘솔/도메인 service 설계에 직접 옮길 결정을 뽑는다.

### 4-bis-1. Progressive defaults — 최소 입력으로 동작하는 봇이 만들어진다

```bash
# 가능한 최소 요청
POST /v3/agents
{ "name": "테스트봇" }
```

위 요청만 보내면 vox는:
- `type`을 `single_prompt`로 (default)
- `data.prompt.firstLineType`을 `aiFirstDynamic`으로
- `data.callSettings.callTimeoutInSeconds`를 `900`으로
- `data.callSettings.silenceCallTimeoutInSeconds`를 `30`으로
- `data.callSettings.activationThreshold`를 `0.55`로
- `data.security.optOutSensitiveDataStorage`를 `false`로
- ... 나머지 모든 sub-config를 서버 기본값으로 **자동 채움**

> 누락되거나 일부만 전달된 값은 서버 기본값과 병합됩니다. (`AgentDataCreate` description)

**왜 중요한가**:
- 콘솔 UX에서 [+ 새 봇] 한 번 누르면 **이미 동작하는 봇이 생긴다** (이름만 받고 즉시 통화 가능).
- 사용자는 점진적으로(progressive) `data.prompt`, `data.voice` 같은 카테고리를 채워가면 됨.
- 빈 봇이 아니라 **default-equipped 봇**.

**우리 적용**:
- 도메인 service: `BotFactory.create_default(name, tenant_id) -> Bot` — 모든 sub-config에 default 적용한 entity 반환.
- API: 콘솔 first-create는 `{name}` 또는 `{name, type}`만 받음. 나머지는 PATCH로 채워나감.
- DB: 컬럼별 DEFAULT를 두지 말고, **application layer의 default builder에 단일화** (versioning 가능, 테스트 가능).

### 4-bis-2. type은 mutually exclusive, 그리고 (사실상) immutable

```python
CreateAgentRequest.type: "single_prompt" | "flow"  # default: single_prompt

# type=single_prompt:  data를 사용, flow_data 무시
# type=flow:           flow_data 필수, data는 default만 채워짐
```

vox spec에서 명시되진 않지만, 정황상:
- `single_prompt → flow` 전환은 위험: 프롬프트 자산이 flow 노드로 자동 매핑되지 않음.
- `flow → single_prompt` 전환은 손실: flow_data를 어떻게 1개 프롬프트로 합칠지 모호함.
- → 운영 안전을 위해 **type은 immutable**로 두는 게 합리적. 변경 필요 시 새 봇 생성.

**우리 적용**:
- `bot` 테이블의 `kind` 컬럼은 CHECK constraint로 변경 차단.
- 콘솔에서 봇 생성 시 type 선택은 **첫 화면에서만 노출**, 이후엔 비활성.

### 4-bis-3. agent.data가 9개 카테고리로 잘려 있는 이유 = sub-schema 독립 버전

OpenAPI에 명시된 레지스트리 URI를 모으면:

| sub-config | 레지스트리 URI | 현재 버전 |
|---|---|---|
| prompt | `voxai://agent-schema/prompt/v1` | v1 |
| llm | `voxai://agent-schema/llm/v2` | **v2** |
| stt | `voxai://agent-schema/stt/v2` | **v2** |
| voice | `voxai://agent-schema/voice/v1` | v1 |
| speech | `voxai://agent-schema/speech/v1` | v1 |
| callSettings | `voxai://agent-schema/call-settings/v1` | v1 |
| postCall | `voxai://agent-schema/post-call/v1` | v1 |
| security | `voxai://agent-schema/security/v1` | v1 |
| webhookSettings | `voxai://agent-schema/webhook-settings/v1` | v1 |

**관찰**: llm과 stt만 v2. 나머지는 v1. 즉 vox는 **sub-config 단위로 schema migration**을 한다. agent 전체 스키마 버전을 한꺼번에 올리지 않음.

**왜 이렇게 했는가**:
- LLM 모델 옵션이 새로 추가됐을 때(thinkingBudget, reasoningEffort) — LLM 카테고리만 v2로 올림.
- 다른 카테고리(voice, callSettings)는 영향 없음.
- 호환성 부담을 sub-config 단위로 격리.

**우리 적용**:
- `bot_config` JSONB 안에 `schema_versions: {prompt: "v1", llm: "v1", voice: "v1", ...}` 같은 메타필드 보관.
- 우리 LLM 모듈에 옵션 추가 시 `llm.schema_version`만 올리고 마이그레이션 함수 작성.
- 전체 봇을 한 버전으로 묶지 말 것.

### 4-bis-4. snake_case 통일 vs camelCase 유지 — 우리는 통일

vox가 `agent.data`만 camelCase를 유지하는 이유는 **"플로우 빌더 프론트엔드 코드 호환"**.

```
백엔드 입출력은 snake_case
  ↓
agent.data, flow_data 만 camelCase 예외
  ↑
프론트엔드 flow builder가 직접 JSON 다룸 → 변환 없이 사용
```

우리는 **자체 서비스, 자체 콘솔, 자체 플로우 빌더**라 호환 부담이 없음. → 전 필드 snake_case 통일.

**단**, vox 호환층을 만들 일이 있다면(예: 마이그레이션 import) 그 때 매핑 어댑터를 두면 됨.

### 4-bis-5. tools 슬롯 2개 — custom과 built-in의 책임 분리

```python
agent.data.toolIds: [UUID]           # custom tool: 외부 webhook 호출
agent.data.builtInTools: [oneOf]     # built-in tool: 시스템 액션 (5종)
    EndCallTool           - 통화 종료
    TransferCallTool      - 전화번호/SIP로 전환
    TransferAgentTool     - 다른 에이전트로 전환 (targetAgentId)
    SendSmsTool           - SMS 전송 (static/dynamic)
    SendDtmfTool          - DTMF 키 송출
```

**왜 두 슬롯으로 나뉘었는가**:
- custom tool은 **테넌트가 정의** (외부 API webhook). lifecycle: 사용자가 생성/수정/삭제.
- built-in tool은 **vox 코어가 제공** (전화 제어 액션). lifecycle: 봇별 enable/disable + 설정만.

이게 우리 `ToolType` enum 설계의 핵심.

**우리 적용**:

```python
# domain enum
class ToolKind(StrEnum):
    CUSTOM_API     = "custom_api"      # 외부 webhook
    END_CALL       = "end_call"
    TRANSFER_CALL  = "transfer_call"
    TRANSFER_AGENT = "transfer_agent"
    SEND_SMS       = "send_sms"
    SEND_DTMF      = "send_dtmf"

# DB
tool                  # custom only (id, tenant_id, name, input_schema, api_config)
bot_custom_tool_link  # (bot_id, tool_id, position)
bot_built_in_tool     # (bot_id, kind, config jsonb)  -- 5 row max per bot
```

콘솔도 두 화면 분리: "내 도구 라이브러리"(custom) vs "봇 액션 설정"(built-in).

### 4-bis-6. presetDynamicVariables — 2층 변수 모델

```python
# 봇 정의에서 preset
agent.data.presetDynamicVariables = {
    "customer_name": "고객님",
    "company_name": "AICX",
    "support_phone": "1588-0000",
}

# 통화 생성 시 override
POST /v3/calls
{
    "agent": {"agent_id": "..."},
    "dynamic_variables": {
        "customer_name": "홍길동"   # preset의 customer_name을 덮어씀
        # company_name, support_phone은 preset 값 그대로 사용
    }
}
```

프롬프트 안에서 `안녕하세요 {{customer_name}}님, {{company_name}}입니다` 같이 치환.

**왜 두 레이어로 두는가**:
- 자주 안 바뀌는 값(회사명, 대표번호)을 봇 정의에 박아두고,
- 통화마다 바뀌는 값(고객명, 잔액)만 통화 생성 시 보낸다.
- 캠페인 task별로도 override 가능 (`CampaignTaskV3.dynamic_variables`).

**3층 override 체계**:
```
bot.presetDynamicVariables (default)
    ↓
campaign.task.dynamic_variables (있으면 우선)
    ↓
call.dynamic_variables (최종)
```

**우리 적용**: 위 3층 체계 그대로. 도메인 service에 `resolve_dynamic_variables(bot, campaign_task, call_request) -> dict` 단일 함수로 머지 로직 일원화.

### 4-bis-7. firstLineType — 인바운드/아웃바운드별 default 다르게

```python
firstLineType:
    "userFirst"        # 사용자가 먼저 말함 (인바운드 자연스러움)
    "aiFirstStatic"    # firstLine 필드의 고정 문장 발화
    "aiFirstDynamic"   # LLM이 첫 문장 생성 (default)
```

**아웃바운드 통화 (우리가 거는 전화)**:
- 사용자가 받자마자 침묵 → 어색함.
- `aiFirstStatic` 권장 ("안녕하세요, AICX 콜봇입니다. 잠시 통화 가능하신가요?")

**인바운드 통화 (고객이 우리에게 거는 전화)**:
- 콜봇이 "안녕하세요" 말하는 게 자연스러움.
- `aiFirstDynamic` 또는 `aiFirstStatic` 둘 다 가능. `userFirst`는 안 어울림.

**우리 적용**: `BotFactory.create_default(kind: inbound|outbound)`에서 firstLineType의 default를 다르게.

### 4-bis-8. 생성 응답은 두 종류 — `AgentMutationResponse` (validator 메시지 포함)

스키마 description에서 발견:
> create/update 응답은 `AgentMutationResponse` (validator 메시지 포함).
> 단건 조회 응답은 `AgentResponse`.

**의미**: 생성/수정 시 server-side validator가 잡은 **경고성 메시지**(예: "이 voice는 이 language를 지원하지 않을 수 있습니다", "tool ID가 다른 봇에서도 사용 중입니다")를 응답에 같이 실어 보냄.

**우리 적용**:
- 생성/수정 응답 DTO에 `warnings: [{field, code, message}]` 배열 추가.
- 콘솔에서 저장 직후 토스트로 노출.
- 에러가 아니므로 200/201 그대로, body에 메타정보로.

### 4-bis-9. 생성 직후의 권장 워크플로

vox 컨벤션을 종합하면 "새 봇 → 운영 게시"까지의 권장 흐름:

```
1. POST /v3/agents { name: "X" }
   → 봇 생성 (current 상태, default values)

2. PATCH /v3/agents/{id}
   → data.prompt.prompt, data.voice.id 등 채움
   (여러 번 가능, 부분 저장)

3. (선택) 실제 호출 테스트:
   POST /v3/calls { agent: { agent_id: X, agent_version: "current" } }
   → "current" 버전으로 통화 — 작업 중인 변경사항 즉시 반영

4. POST /v3/agents/{id}/versions { description: "..." }
   → current를 v1으로 스냅샷

5. POST /v3/agents/{id}/versions/v1/publish
   → v1을 production으로 게시
   응답: { production_version: "v1", previous_production_version: null }

6. 운영 호출:
   POST /v3/calls { agent: { agent_id: X, agent_version: "production" } }
   → production 버전(v1) 사용

7. 수정 시:
   PATCH /v3/agents/{id} → current만 바뀜, production은 그대로 v1
   POST .../versions → v2 스냅샷
   POST .../versions/v2/publish → 응답에 previous_production_version: "v1"
   → 운영 호출은 자동으로 v2 사용
```

**핵심 의미**:
- `current`는 **샌드박스**, `production`은 **운영**, `v{n}`은 **불변 스냅샷**.
- 운영 통화는 `agent_version: "production"`으로 보내야 안전. `"current"`로 보내면 작업 중 변경이 그대로 노출.
- 통화 record에 `agent_version: "v1"`처럼 박혀 있어, 추후 "이 통화는 어떤 봇 정의로 처리됐는가" 정확히 추적 가능.

**우리 적용**:
- 콘솔에 **3가지 호출 버튼**:
  - "이 봇으로 테스트 통화" (current)
  - "운영 버전으로 통화" (production)
  - "특정 버전으로 재현" (v{n}, 디버깅용)
- 캠페인 생성 시 default는 `production`.
- API 미지정 시 default `current`인 점은 vox 컨벤션. 우리도 동일이지만, 실수 방지를 위해 **콘솔에서 호출할 땐 명시 강제**.

### 4-bis-10. 한눈에 보는 결정사항 (생성 구조 한정)

| 결정 | 우리 채택 |
|---|---|
| type 종류 | `single_prompt` `flow` 2개 (vox와 동일) |
| type 변경 | **immutable** (vox 정황 + 안전) |
| 최소 생성 | `{name}` 또는 `{name, type}`만 받음, 나머지 default |
| sub-config 카테고리 | 9개 (prompt/llm/stt/voice/speech/callSettings/postCall/security/webhookSettings + knowledge + variables + tools) |
| sub-config 버전 | **카테고리별 독립 버전** (`schema_versions` 메타) |
| 필드 케이스 | **전 필드 snake_case 통일** (vox의 camelCase 호환 부담 없음) |
| tool 슬롯 | **2슬롯** (custom_tool_ids + built_in_tools), built-in 5종 enum |
| 변수 모델 | **3층 override**: bot preset → campaign task → call |
| 첫 발화 정책 | inbound default `aiFirstDynamic`, outbound default `aiFirstStatic` |
| 생성/수정 응답 | `warnings: []` 배열 포함 (non-blocking) |
| 권장 워크플로 | current 작업 → 버전 스냅샷 → publish → production 호출 |
| 통화에 박힌 버전 | `(bot_id, version_label)` 쌍 — 사후 재현 가능 |

---

## 5. Flow 에이전트 — 노드 그래프 모델

### 5-1. 10종 노드 + edge + transition

```
Nodes (discriminator: data.type):
  begin           - 시작점 (BeginData)
  conversation    - LLM 대화 턴 (ConversationData)
  condition       - 분기 (ConditionData)
  extraction      - 변수 추출 (ExtractionData + variables[])
  tool            - custom tool 호출 (ToolData, toolId 참조)
  api             - 외부 API 직접 호출 (ApiData, ApiConfiguration)
  endCall         - 통화 종료
  transferCall    - 전화 전환 (phone/SIP)
  transferAgent   - 다른 에이전트로 전환 (targetAgentId)
  sendSms         - SMS 전송 (static/dynamic)
  note            - 주석 (실행 X)

Edges:
  {id, source, target, sourceHandle, targetHandle, type="custom"}

Transitions (node.data 안에 저장):
  transitions: LLM/자연어 또는 fallback 경로
    - condition: 자연어 문구 ("긍정 응답일 때")
    - isFallback: bool (실패 경로, transferCall/transferAgent 필수)
    - isSkipUserResponse: bool (extraction, conversation 일부)
    - isGlobalTransition: bool
  logicalTransitions: 변수 기반 분기
    - condition: LogicalCondition (and/or + SingleCondition[])
    - SingleCondition: {variable, operator, value}
      operator: equals | not_equals | contains | does_not_contain
              | greater_than | greater_than_or_equal
              | less_than | less_than_or_equal
              | exists | does_not_exist
```

### 5-2. 도출 인사이트

#### A. transition을 LLM 분기와 변수 분기로 **분리**

vox는 한 노드에서 두 종류의 분기를 함께 정의:
- `transitions`: 자연어 조건 → LLM이 판단
- `logicalTransitions`: 변수 조건 → 결정론적

→ **우리 적용**: 우리 flow 엔진도 같은 이중 구조. **logical 먼저 평가, 매치 없으면 LLM transition**. 디버깅에 유리.

#### B. fallback 경로의 의무화

- `transferCall`/`transferAgent`는 `isFallback=true` transition 필수
- `api`/`tool`/`sendSms`는 권장

→ **우리 적용**: 외부 호출 노드는 fallback edge 없으면 flow validator에서 reject. 통화 중 dead-end 방지.

#### C. global transition = 어디서든 가는 비상구

- `isGlobalTransition: true` + `GlobalNodeSettings.transitionCondition`
- 예: "취소하고 싶다고 말하면 어디서든 종료 노드로"

→ **우리 적용**: 콜봇에서 매우 유용. "상담사 연결해주세요" 같은 universal escape hatch는 global transition으로.

#### D. SkipUserResponse 패턴

extraction 노드와 일부 conversation 노드는 사용자 응답을 기다리지 않고 다음으로 흐름.

→ **우리 적용**: turn-taking 모델에서 "노드 진입=무조건 turn 소비"가 아니라, 노드 메타데이터로 turn skip 여부를 표현. STT 대기 시간 절약.

#### E. `api` 노드 vs `tool` 노드의 미묘한 차이

| | tool 노드 | api 노드 |
|---|---|---|
| 정의 | tool registry(`POST /tools`)에서 만들고 ID로 참조 | flow 안에 inline 설정 |
| 재사용 | 여러 flow/agent에서 재사용 | 그 flow 한정 |
| 파라미터 | LLM이 input_schema 따라 생성 | template body, static + 변수 치환 |
| 인증 | tool 정의에 박힘 | 노드에 박힘 |

→ **우리 적용**: 같은 외부 API라도 **공용=tool, 일회성=api node**로 분리. 콘솔 UX도 이 두 화면을 분리하면 사용자가 헷갈리지 않음.

---

## 6. Campaign — 배치 발신 상태머신

### 6-1. 상태 7개

```
draft     - 예약 대기 (scheduled_at 미래)
pending   - 실행 대기
ongoing   - 진행 중
paused    - 일시정지 (paused_by: user | system)
success   - 완료
fail      - 실패
canceled  - 취소
```

### 6-2. action endpoint 3종

```
POST /campaigns/{id}/pause   - paused_by=user
POST /campaigns/{id}/resume
POST /campaigns/{id}/cancel  - 대기 중 task 중단
```

### 6-3. CallTimeWindow — 통화 허용 시간대

```python
CallTimeWindowV3:
    windows: [{start_min: 540, end_min: 1080, days: [Mon..Sun]}]  # 분 단위!
    timezone: "Asia/Seoul"
    auto_resume: True   # 시간대 진입 시 자동 재개
```

→ **우리 적용**:
1. **시간을 "분 단위 integer"로 표현** (`start_min=540` = 9시). DB에서 시각 비교가 단순해짐.
2. **auto-resume 패턴**: 시간대 벗어나면 시스템이 자동으로 `paused_by=system`으로 일시정지, 시간대 복귀 시 자동 재개. 사람이 매번 손 안 댐. → 우리도 동일 로직 (cron으로 분 단위 평가).

### 6-4. 동시성 제어

- `concurrency: 5` (default, 1~100)
- `active_concurrency: int` (현재 진행 중)

→ **우리 적용**: 캠페인 단위 + 조직 단위(`MetricType.concurrency`) 2단 동시성 제한. Redis로 counter 관리.

---

## 7. Telephone Number 도메인

### 7-1. 9개 endpoint 구조

```
GET    /telephone-numbers/available           - 마켓플레이스 (구매 가능)
POST   /telephone-numbers/purchase            - 구매
POST   /telephone-numbers/register            - SIP 직접 등록 (자체 회선)
GET    /organization-telephone-numbers        - 보유 목록
GET    /organization-telephone-numbers/{id}   - 상세
PATCH  /organization-telephone-numbers/{id}   - 수정
DELETE /organization-telephone-numbers/{id}   - 해지
POST   /organization-telephone-numbers/{id}/revoke-cancel  - 해지 취소
PATCH  /organization-telephone-numbers/{id}/agent  - 에이전트 매핑
PATCH  /organization-telephone-numbers/{id}/sip    - SIP 설정
```

### 7-2. 도출 인사이트

1. **번호 ↔ 에이전트 매핑은 별도 sub-resource.** 번호의 다른 속성과 lifecycle이 다르기 때문. → 우리도 `bot ↔ phone_number` 매핑 테이블 분리.
2. **인바운드/아웃바운드 매핑 분리.** `UpdateAgentMappingRequest`: `{inbound_agent, outbound_agent}`. 같은 번호로 들어올 때 받을 봇 ≠ 나갈 때 쓸 봇.
3. **해지 취소 endpoint 존재** (`/revoke-cancel`). 번호 해지는 즉시 X, **유예 기간 동안 revoke 가능**한 2단계 상태머신. → 통신사 연동 시 동일 패턴 가능성 높음. 도메인에 `revocation_pending_until` 컬럼.

---

## 8. Knowledge Base

### 8-1. 구조

```
POST   /knowledges                             - 생성 (name만)
GET    /knowledges                             - 목록
DELETE /knowledges/{id}
GET    /knowledges/{id}/documents              - 문서 목록
POST   /knowledges/{id}/documents              - 문서 추가
DELETE /knowledges/{id}/documents/{doc_id}
```

```python
KnowledgeDocumentSummary:
    id: UUID
    knowledge_id: integer        # ← knowledge는 integer ID(legacy)
    name: str
    document_type: "file" | "text" | "webpage"
    status: "uploading" | "completed" | "failed"
    upload_percentage: int|null  # status=uploading일 때만
    token_count: int|null        # 완료 후
    webpage_urls: [str]|null     # webpage 타입만
```

### 8-2. 도출 인사이트

1. **문서 상태머신 3단계로 단순.** uploading → completed | failed. 우리 RAG 인덱싱도 똑같이.
2. **`token_count`를 응답에 노출.** 비용 산정/한도 관리에 필수. 우리도 같이 노출.
3. **`upload_percentage`는 uploading 동안만 의미.** UI 진행률 표시용. polling 또는 SSE.
4. **`webpage` 문서 타입**으로 크롤링 결과 보관. file/text/webpage 3종 충분. PDF는 file에 포섭.
5. **knowledge는 integer ID (legacy).** 새로 만들면 UUID 권장. vox도 이걸 굳이 안 바꾸는 건 외부 호환성 이유.

---

## 9. Alert Rules — 운영 가시성의 모범

### 9-1. 메트릭 4종

```
call_count       - 시간창 내 통화 건수
concurrency      - 동시 진행 통화 peak
tool_call_count  - 시간창 내 tool 호출 건수
api_call_count   - 시간창 내 API 호출 건수
```

### 9-2. 비교 패턴

```
threshold_type: "absolute" | "relative"   # 절대값 vs 직전 같은 시간창 대비 변화율(%)
comparison_op:  gt | gte | lt | lte
threshold_value: number
time_window:    {hours/minutes/days}
evaluation_frequency: "5m" | "1h" 등        # time_window보다 짧으면 rolling
```

### 9-3. Incident lifecycle

```
triggered → active → resolved
```

### 9-4. 채널 3종

email | slack | webhook (각각 별도 스키마, recipients 형식만 다름)

### 9-5. lifecycle action 4종

```
POST /alert-rules/{id}/enable     - 활성화
POST /alert-rules/{id}/disable    - 비활성화
POST /alert-rules/{id}/pause      - 일시정지 (paused_until)
POST /alert-rules/{id}/resume
```

### 9-6. 도출 인사이트

1. **4종 메트릭이 콜봇 운영 모니터링의 핵심.** 우리도 같은 4개로 시작. 추가는 운영하며 필요한 것만.
2. **threshold relative는 "전주 동시간 대비 30% 증가" 같은 조건 가능.** 야간 트래픽 적은 시간대도 의미 있는 임계값 설정 가능.
3. **rule status는 `enabled` + `paused` 2개 boolean에서 파생.** UI에는 `active/disabled/paused` 단일 enum으로 노출. **derived field 패턴**.
4. **test-notification endpoint.** 알림 채널 설정 직후 dry-run으로 도달 확인. 우리도 콘솔에 "테스트 알림 보내기" 버튼 필수.
5. **incidents는 rule 하위.** `/alert-rules/{id}/incidents` + 전역 `/incidents` 둘 다 제공. 양쪽 UX 다 필요.

→ 1인 운영([[project_solo_operation]]) 관점: 4메트릭 + 3채널(email/slack/webhook)이면 대부분 케이스 커버. 처음부터 ramp up할 가치 큼.

---

## 10. 우리 콜봇에 직접 반영할 결정 (체크리스트)

### DB 스키마

- [ ] `call` 테이블: vox CallResponse를 거의 그대로 (id, agent_id+bot_version, call_type, status, disconnection_reason, *_at, from/to/presentation_number, metadata jsonb, dynamic_variables jsonb, variant_label, opt_out_sensitive_data_storage)
- [ ] `call_analysis` 테이블 분리 (1:1, 비동기 INSERT)
- [ ] `call_cost` 테이블 분리 또는 컬럼 (decimal 저장, string 직렬화)
- [ ] `transcript_event` 단일 테이블 (role/type discriminator)
- [ ] `bot` + `bot_version` 분리, version_label은 `^(current|production|v[1-9][0-9]*)$`
- [ ] `tool` 테이블 (custom) + `bot_built_in_tool` (built-in enable 매핑)
- [ ] `knowledge` + `knowledge_document` (status enum: uploading/completed/failed)
- [ ] `phone_number` + `phone_number_agent_mapping` (inbound_bot_id, outbound_bot_id)
- [ ] `campaign` + `campaign_task` (분 단위 time_window, auto_resume)
- [ ] `alert_rule` + `alert_incident` + `notification_channel`
- [ ] flow 그래프는 `bot_version`의 `flow_data jsonb`로 통째 저장 (vox와 동일, PATCH 시 전체 교체)

### 도메인 엔티티 ([[feedback_clean_architecture]])

- [ ] `Call`, `CallStatus`, `DisconnectionReason` (StrEnum, vox와 동일값)
- [ ] `BotReference(bot_id, version)` VO
- [ ] `PhoneNumber` VO (from/to/presentation)
- [ ] `Money` VO (decimal + currency, string 직렬화)
- [ ] `TranscriptEvent` (4 role 통합)
- [ ] `Tool` + `BuiltInToolKind` enum (end_call/transfer_call/transfer_agent/send_sms/send_dtmf)
- [ ] `FlowGraph` + 10 노드 타입 (discriminator union)
- [ ] `Transition` (LLM) + `LogicalCondition` (변수, 10 operator)
- [ ] `Campaign` + `CampaignStatus` (7개) + `CallTimeWindow`
- [ ] `AlertRule` + `AlertRuleStatus` (derived from enabled+paused)

### API 컨벤션

- [ ] 인증: Bearer token (tenant 단위)
- [ ] 페이지네이션: cursor + limit (offset 금지)
- [ ] 시간: epoch ms 직렬화
- [ ] 상태 전이: 별도 action endpoint (`/publish`, `/pause`, `/resume`, `/cancel`, `/enable`, `/disable`)
- [ ] PATCH: omit=유지, null=해제, 빈={}는 400 (minProperties=1)
- [ ] 배열 필터: `?field[]=v1&field[]=v2`
- [ ] 에러: `{error: {code, message, details}}`

### 콘솔 UX ([[project_vox_ui_reference]], [[feedback_no_hardcoded_tenant_config]])

- [ ] Bot 편집: data 카테고리 8개(prompt/llm/voice/stt/speech/callSettings/postCall/security/webhook) 좌측 탭
- [ ] Bot 버전: current 작업 + "버전 저장" 액션 + 버전 목록 + production 게시 버튼 + 이전 production 표시(롤백)
- [ ] Tool 라이브러리 + flow 안 api 노드 inline 설정 분리
- [ ] 번호 매핑: inbound/outbound 별도 슬롯
- [ ] 캠페인: time window 시각화 (분→시각 변환), auto_resume 토글
- [ ] 알림: 4메트릭 + 3채널 + test-notification 버튼

### 1인 운영 우선순위 ([[project_solo_operation]])

처음 6개월 안 만들 것 (vox에는 있지만 우리는 미룸):
- flow의 `note` 노드 (UI 편의용, 데이터 X)
- `relative` threshold (절대값 먼저)
- DTMF 종료 키 커스터마이즈 (default `#` 고정)
- 배경음악(`backgroundMusic`) 5종 — 일단 `none` 고정
- `thinkingBudget`, `reasoningEffort` (LLM 고급 옵션)

처음부터 꼭 만들 것:
- bot version + publish (운영 안전성)
- variant_label (분석 비용 0)
- opt_out_sensitive_data_storage (compliance)
- alert rule 4메트릭 (1인 운영 = 알람 의존)
- auto_resume time window (사람이 캠페인 손 안 대게)

---

## 11. 메모리 갱신 후보

이번 분석에서 새로 굳어진 결정사항. 사용자 확인 후 memory로 옮길 수 있는 것들:

1. **API 컨벤션 5종** (cursor 페이지네이션, epoch ms, action endpoint 분리, PATCH 시맨틱, 배열 필터)는 `feedback_api_conventions.md`로 격상 후보.
2. **bot version 시맨틱** (`current/production/v{n}`)은 `project_callbot_agent_model`에 합치는 게 자연스러움.
3. **vox 4메트릭 알림**이 1인 운영 default라는 결정은 `project_solo_operation`에 추가.

---

## 12. 참고: vox 스펙에 있지만 우리 도메인에 직접 없는 것

- **SIP 직접 등록** (`/telephone-numbers/register`): 우리 MVP는 PSTN 통신사 연동. SIP 직등록은 후순위.
- **번호 마켓플레이스** (`/telephone-numbers/available`): 우리는 번호 풀 직접 운영 X. 통신사 위임.
- **schema registry** (`/schemas`): vox는 SDK 자동 생성용. 우리는 단일 백엔드 + 단일 프론트라 불필요.

---

> 본 문서는 빌드 산출물이 아닌 **설계 입력 자료**. 빌드 진입은 사용자 검토 후 별도 ticket으로 ([[feedback_no_premature_build]]).
