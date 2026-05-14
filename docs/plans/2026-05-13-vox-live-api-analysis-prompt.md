# vox v3 API 응답 구조 분석 — 메타 프롬프트

> 용도: 이 프롬프트를 새 Claude 세션 또는 subagent에 그대로 붙여 넣으면 vox v3 API를 안전하게 조사해서 **응답 구조 + 인사이트 리포트**를 만든다.
> 작성: 2026-05-13
> 선행 문서: `2026-05-13-vox-api-spec-insights.md` (OpenAPI 스펙 기반 정적 분석)
> 핵심: spec 검증이 아니라 **응답을 1차 자료로 구조를 그려내고 인사이트를 뽑는 것**. spec과의 diff는 부수 산출물.

---

## 0. 작업 의뢰 (이 아래를 그대로 새 세션에 붙여 넣기)

당신은 aicx-callbot 프로젝트의 백엔드 설계 보조 에이전트다. vox.ai v3 API의 **실제 응답을 보고**:

1. 각 리소스의 응답 구조를 누락 없이 매핑 (spec에 없는 필드 포함)
2. 응답을 통해 발견한 모델링 통찰을 도출 — "왜 vox가 이렇게 설계했는가 → 우리 콜봇 도메인에 어떻게 옮길까"

이 두 가지가 산출물이다. 코드 변경·빌드 일체 없다. 단일 markdown 리포트 1개.

---

## 1. 절대 안전 규칙

### 1-1. HTTP 메서드 정책

| 메서드 | 동작 |
|---|---|
| `GET` | ✅ 자유롭게 호출 (read-only) |
| `POST` / `PATCH` / `DELETE` | ❌ **호출 금지** — request body 스펙만 보고 분석 |

**중요**: POST/PATCH/DELETE는 호기심을 이유로도 호출 시도 금지. URL 추측·dry-run 옵션·테스트성 호출 전부 차단. 이들 endpoint는 **OpenAPI의 request schema(`CreateXxxRequest`, `UpdateXxxRequest` 등)**를 분석 자료로 삼는다.

### 1-2. 자격 증명·민감정보

- `VOX_API_KEY` 토큰은 **로그·리포트·터미널 어디에도 출력하지 말 것**. 환경변수로만 참조.
- 응답을 보고서에 옮길 때 마스킹:
  - 전화번호 → 끝 4자리 (`***1234`)
  - `transcript` 본문 → 발화 길이·role 시퀀스·tool_call 메타만, **본문 텍스트 옮기지 않음**
  - `metadata` / `dynamic_variables` 내 인명·주소·이메일 → 키 이름만, 값은 `<redacted>`
  - `summary` / `custom_analysis_data` → 패턴·길이만, 본문 X
- raw JSON 원본은 `docs/plans/.vox-snapshots/`에 timestamped 파일로 저장 (`.gitignore`에 추가). 보고서는 가공본만.

### 1-3. 호출 빈도

- 첫 호출은 `limit=5` 또는 `10`으로.
- 429를 1회라도 받으면 60초 backoff + limit 절반.
- 총 호출 200건 도달 전 사용자에게 보고.

---

## 2. 환경

```bash
export VOX_API_KEY="<사용자가 제공>"
export VOX_BASE_URL="https://client-api.tryvox.co/v3"
```

호출 헬퍼:

```bash
voxget() {
  local path="$1"; shift
  curl -sS -G "${VOX_BASE_URL}${path}" \
    -H "Authorization: Bearer ${VOX_API_KEY}" \
    -H "Accept: application/json" "$@"
}
```

snapshot 저장:

```bash
mkdir -p docs/plans/.vox-snapshots
TS=$(date +%Y%m%d-%H%M%S)
voxget /agents --data-urlencode "limit=5" \
  > docs/plans/.vox-snapshots/${TS}-agents-list.json
```

---

## 3. 두 가지 작업 트랙

### 트랙 A — GET 응답 트랙 (live 호출)

각 GET endpoint마다 **응답 수집 → 구조 매핑 → 인사이트 도출** 3-step 사이클.

#### Step A. 응답 수집
endpoint를 다양한 필터·페이지·리소스 ID 조합으로 호출, snapshot 저장. 최소 3개 샘플 확보 (다양성).

#### Step B. 구조 매핑

응답이 어떤 모양인지 그대로 옮긴다. 형식:

```
GET /calls/{id} (n=5)

CallResponse:
  id: UUID                          [5/5]
  agent: object
    agent_id: UUID                  [5/5]
    agent_version: enum             [관측값: production×3, v2×1, current×1]
  status: enum                      [관측값: ended×4, ongoing×1]
  disconnection_reason: enum|null   [관측값: user_hangup×3, agent_hangup×1, null×1]
  start_at: int (unix ms)           [샘플 범위: 1776... ~ 1776...]
  end_at: int|null                  [4/5 채워짐]
  call_cost: object|null
    total_cost: string (KRW)        [범위: "12.34" ~ "456.78"]
    [hidden] sub_costs: array       # spec에 없음. 실제 응답에 있음
      type: enum                    [관측값: llm, tts, stt, telephony]
      amount: string
  transcript: array|null            [평균 N항, 최대 M항]
    role 분포: agent×60%, user×35%, tool_call_invocation×3%, tool_call_result×2%
    agent/user 항목: {role, content, start_at, end_at}
    tool_call_invocation 항목: {role, tool_name, arguments, ...}
  ...
```

원칙:
- **응답에 있는 모든 키를 누락 없이**. spec에 없으면 `[hidden]` 표시.
- 값 자체는 옮기지 말고 타입·분포·범위·null 빈도만.
- enum 필드는 관측된 값 분포 명시.
- nested object는 indent로 표현.

#### Step C. 인사이트 도출

응답을 보고 떠오른 통찰을 짧은 문단으로:

```
### 인사이트: <한 줄 요약>

관찰: 응답에서 발견한 사실 (어떤 필드가 어떻게 채워져 있더라).
해석: vox가 왜 이렇게 설계했을지 추론.
우리 적용: aicx-callbot DB/도메인/콘솔에 어떻게 옮길지 구체안.
```

예시:

```
### 인사이트: call_cost가 항상 nullable이고 sub-cost로 쪼개져 있다

관찰: GET /calls/{id} 5건 중 ongoing 1건은 call_cost=null, 나머지 4건은
      total_cost 외에 sub_costs[]가 함께 있더라 (llm/tts/stt/telephony 4종).
해석: 통화 종료 즉시 비용이 확정되지 않고 비동기로 채워짐. 비용을 단일 값이
      아니라 항목별로 분해해 운영 분석에 활용.
우리 적용: call_cost 테이블 (call_id, cost_type, amount) row N개 저장,
         total_cost는 view 또는 calculated column. ledger 패턴.
```

### 트랙 B — Mutation Spec 트랙 (호출 없이 분석만)

POST/PATCH/DELETE는 **호출 금지**. 대신 OpenAPI에 정의된 request body 스키마를 분석 자료로 삼는다.

#### Step A. spec 추출
`https://docs.tryvox.co/api-reference/v3/openapi.json`의 `CreateXxxRequest`, `UpdateXxxRequest`, action endpoint(`/publish`, `/pause` 등)의 request schema를 인용. (기존 `2026-05-13-vox-api-spec-insights.md`에 이미 정리된 내용을 1차 자료로 활용)

#### Step B. 구조·의도 매핑

request 스키마에서 다음을 읽어낸다:
- **필수 vs 선택 필드** — 무엇이 최소 입력인지 = 도메인 invariant
- **default 값** — vox가 운영하며 굳힌 기본값 (예: callTimeoutInSeconds=900)
- **enum 값들** — 상태머신·옵션의 전체 집합
- **nested 객체 구조** — 자산 그룹핑의 단서
- **PATCH 시맨틱** — 어떤 필드가 nullable인지 (= 해제 가능 vs 필수 유지)
- **action endpoint의 분리 의도** — POST `/publish`, `/pause`처럼 동사 endpoint가 왜 분리됐는지

#### Step C. 인사이트 도출

GET 트랙과 동일 3단(관찰/해석/우리 적용). 단, "관찰"의 자료원이 응답이 아닌 spec 본문.

예시:

```
### 인사이트: CallTimeWindow가 시각이 아닌 "분 단위 integer"다

관찰: CreateCampaignV3Request.call_time_window.windows[]는
      {start_min: 540, end_min: 1080, days: [Mon..Sun]} 구조. timezone은 IANA string.
해석: 시각·문자열보다 분 단위 정수가 비교·집합 연산이 단순 (DB에서 between도 쉬움).
      auto_resume이 default true인 건 사람이 캠페인 손 안 대게 하려는 의도.
우리 적용: campaign_time_window 테이블 (campaign_id, start_min, end_min, weekday).
         IANA timezone 별도 컬럼. cron worker가 분 단위 평가.
```

---

## 4. 단계별 작업 순서

### Phase 0 — Smoke (트랙 A)

```
GET /agents?limit=1
```

- 200 → 다음 단계로.
- 401/403 → 즉시 중단·보고.
- 빈 조직(`data: []`) → "live 데이터 없음" 보고 후 사용자에게 진행 방식 묻기 (트랙 B만으로 진행할지 등).

### Phase 1 — 인벤토리 (트랙 A)

각 GET 목록을 `limit=10`으로 1회:

```
/agents  /calls  /campaigns  /tools  /knowledges
/organization-telephone-numbers  /alert-rules  /incidents
/models/llms  /models/voices  /schemas
```

목적: 존재 여부 + envelope 형태 + 샘플 1건.

### Phase 2 — Agent (트랙 A + B 혼합)

**트랙 A (호출)**:
```
GET /agents/{id}                    # current
GET /agents/{id}?version=production
GET /agents/{id}?version=v1
GET /agents/{id}/versions
```

가능하면 single_prompt 1개 + flow 1개 모두.

응답에서 매핑할 것:
- `data.*` sub-config 9종(prompt/llm/stt/voice/speech/callSettings/postCall/security/webhookSettings)의 실제 값
- `presetDynamicVariables`의 키 명명 패턴
- `toolIds` vs `builtInTools` 분포
- `current` vs `production` 응답 diff
- flow_data 노드 type 사용 빈도, transition 패턴

**트랙 B (호출 X, spec 분석)**:
- `CreateAgentRequest`: `name`만 필수인 progressive default 패턴
- `UpdateAgentRequest`: PATCH 시맨틱 (omit=유지, null=해제)
- `POST /agents/{id}/versions/{version}/publish`: 응답에 previous_production_version 포함 = 롤백 audit 의도
- `POST /agents/{id}/versions` body: 버전 스냅샷 생성 시 description만 받는다 = 작업 중 data가 통째로 박힘

### Phase 3 — Call (트랙 A + B)

**트랙 A**:
```
GET /calls?limit=50&sort_order=desc
GET /calls?limit=50&status[]=ended
GET /calls?limit=50&status[]=ongoing&status[]=error
GET /calls/{id}    # 다양한 status/type별 최대 5건
```

분포 집계:
- status, disconnection_reason, call_type, agent_version, variant_label, opt_out
- call_analysis 채워진 비율, call_cost 채워진 비율
- transcript 길이·role 분포

상세 매핑:
- transcript 4 role 각각의 sub-schema
- tool_call_invocation/result payload
- call_analysis.custom_analysis_data 모양

페이지네이션 / 시간 필터 동작 확인.

**트랙 B**:
- `CreateCallRequest`: 발신에 최소 필요한 입력
- agent 생략 시 traffic-split 라우팅이 의미하는 도메인 모델 (번호↔봇 매핑이 1:N 가능)

### Phase 4 — Tools / Knowledge / Phone / Alerts (트랙 A + B)

**트랙 A 호출**:
```
GET /tools, /tools/{id}
GET /knowledges, /knowledges/{id}/documents
GET /organization-telephone-numbers, /organization-telephone-numbers/{id}
GET /alert-rules, /alert-rules/{id}, /incidents
```

응답 매핑 포인트:
- tool `input_schema` 실제 JSON Schema 복잡도
- tool `api_configuration.auth_type` 분포
- knowledge document `status` 전이 시간 (created_at vs completed)
- phone number의 inbound/outbound agent 분리 사용 패턴
- alert rule metric_type / threshold 실제 값

**트랙 B (spec 분석)**:
- `CreateToolRequest`: name 패턴 제약(영숫자·하이픈·언더스코어), input_schema가 자유 JSON Schema인 것의 의미
- `CreateKnowledgeRequest`: name만 필수 → 비어있는 KB로 만들고 점진적으로 채우는 lifecycle
- 전화번호 sub-action 분리(`/agent`, `/sip`, `/revoke-cancel`): 번호 lifecycle의 단계별 분리
- `CreateAlertRuleRequest`: notification_channels 최대 10개, threshold_value ≥ 0

### Phase 5 — 모델·스키마 (트랙 A only)

```
GET /models/llms
GET /models/voices
GET /schemas
GET /schemas?category=agent-authoring&include_schema=true
```

매핑: 모델·voice별 capabilities 표. provider 분포. 한국어 voice 카탈로그.

---

## 5. 산출물

### 5-1. raw snapshots
`docs/plans/.vox-snapshots/<timestamp>-<endpoint>.json` (gitignore).

### 5-2. 최종 리포트
`docs/plans/2026-05-13-vox-api-live-analysis.md`

권장 구조:

```markdown
# vox v3 API 응답 구조 + 인사이트 분석

> GET 호출 N건 · Mutation spec 분석 M개 · 작성 <날짜>

## 0. TL;DR — 가장 큰 인사이트 5개
(응답·spec을 본 뒤 우리 도메인 설계가 바뀌어야 한다고 판단한 결정만)

## 1. 환경 한 줄 요약
조직 보유 리소스 개수, 활성 모델/voice 카탈로그.

## 2. 리소스별 응답 구조 + 인사이트

### 2.1 Agent
#### 구조 (응답 기반, n=N)
(Step B 매핑 — 모든 필드, hidden 포함)
#### 관측 분포
(sub-config 값 분포, version 사용 패턴)
#### Mutation spec 분석
(Create/Update/publish request body가 드러내는 의도)
#### 인사이트
(각각 관찰/해석/우리 적용 3단)

### 2.2 Call
### 2.3 Tool / Knowledge / Phone / Alert / Model / Schema
(각 동일 구조)

## 3. 종합 인사이트 — vox 설계 철학 추론
응답·spec 양쪽에서 보이는 횡단 패턴
(예: "비동기 채워지는 필드를 별도 endpoint로 분리하지 않고 같은 응답에 nullable로 둔다",
"상태 전이는 항상 별도 action endpoint",
"리소스의 부분 갱신은 sub-resource PATCH로 쪼갠다")

## 4. 우리 aicx-callbot 도메인 반영안
- DB 스키마 변경 제안 (구체 컬럼/테이블)
- 도메인 entity 변경 제안 (필드 추가/제거)
- 콘솔 UX 변경 제안

## 5. 미해결 질문
응답·spec 어느 쪽으로도 해결 안 된 의문.

## 6. 부록: GET 호출 로그
| 시각 | endpoint | 응답 상태 | snapshot 파일 |
```

### 5-3. 작성 원칙

- **응답이 1차, spec이 2차** 자료. 둘이 다를 때는 응답 fact를 우선 기록.
- **fact + 추론 구분 라벨링** (관찰 / 해석 / 우리 적용).
- **샘플 수 명시** (n=5건, n=37건).
- **PII zero** — §1-2 마스킹 규칙 준수.
- 본문 600줄 이내. 길어지면 부록으로.

---

## 6. 작업 종료 후 사용자에게 보고할 것

1. GET 호출 총수 / 성공 비율 / 429 발생 여부
2. Mutation spec 분석한 endpoint 개수
3. 발견 중 **설계 변경이 필요한 항목 N개** (TL;DR)
4. PII 마스킹 검증 결과
5. snapshot 폴더 경로
6. 추가 조사가 필요한 endpoint·시나리오

---

## 7. 사용자 승인이 필요한 케이스

- POST/PATCH/DELETE를 정말 호출하고 싶을 때 → **default는 금지**, 그래도 필요하면 (a)endpoint·body (b)영향 (c)되돌리는 방법 명시 후 승인 요청
- 한 endpoint에 `limit=50` 초과 호출
- 호출 총수 200건 도달
- 429 2회 이상
- spec에 없는 endpoint URL 추측 시도 (default: 금지)

---

## 8. 프로젝트 컨텍스트 (참고)

- aicx-callbot: vox 인소싱 콜봇, 1인 운영, Clean Architecture, LangSmith 미사용
- 입력 문서: `docs/plans/2026-05-13-vox-api-spec-insights.md`
- 본 분석은 위 문서를 응답값 + mutation spec으로 **검증·보완·확장**
- 빌드는 별도 ticket. 본 작업은 조사 + 리포트만.

---

> **핵심**: GET은 응답을 까서 구조와 분포를 그린다. POST/PATCH/DELETE는 **호출하지 않고** spec request body를 읽어 의도를 추론한다. 양쪽 모두 "왜 이렇게 생겼는가 → 우리 도메인에 어떻게 옮길까" 두 줄을 뽑는 게 본 작업의 가치.
