# aicx-callbot 구조 정합성 점검 — `/loop` 메타 프롬프트

> 사용법: `/loop <아래 메타 프롬프트 전체>` (간격 생략 → 모델 자율 페이싱)
> 누적 로그: `aicx-callbot/docs/plans/STRUCTURE_LOG.md` (loop가 자동 생성/append)
> 기준 문서: `VOX_AGENT_STRUCTURE.md`(목표 설계) + 실제 코드

---

## 메타 프롬프트 (이 블록을 그대로 `/loop` 인자로)

```
당신은 aicx-callbot의 데이터 모델·도메인·API·프론트엔드 **구조 정합성**을 점검한다.
한 iteration에 ONE specific 이슈 또는 개선 기회만 찾아 누적 로그에 append.
**코드 수정 절대 금지. 분석/설계 단계.** (memory: feedback_no_premature_build)

참고 기준:
- aicx-callbot/docs/plans/VOX_AGENT_STRUCTURE.md (목표 설계 — Skill·Graph·VariableContext·Dispatcher·Frontdoor·CallbotAgent)
- aicx-callbot/docs/plans/VOX_INSOURCING_DESIGN.md (인소싱 설계)
- 실제 코드:
  - backend/src/domain/ (entities, ports, prompts)
  - backend/src/infrastructure/models.py (SQLAlchemy)
  - backend/src/application/ (skill_runtime, voice_session, post_call, mentions)
  - backend/src/api/routers/ (bots, skills, knowledge, tools, calls)
  - frontend/src/components/ (SkillEditor 관련, BranchesFlowView, Sidebar)

## Step 1 — 누적 로그 읽기
aicx-callbot/docs/plans/STRUCTURE_LOG.md 읽기.
- 없으면 새로 생성 (아래 §템플릿)
- 이미 다룬 area·issue 기억해 중복 금지

## Step 2 — 점검 영역 로테이션
다음 7개 영역 중 ONE 선택. 최근 3개 finding이 같은 area면 스킵.

A. **레이어 정합성** (Domain ↔ DB ↔ API ↔ Frontend)
   - domain/entities.py 객체 vs infrastructure/models.py SQLAlchemy 일치?
   - API schema(Pydantic)가 도메인 그대로인가 별도 DTO인가
   - 프론트 type 정의가 API 응답과 일치?
   - 의존성 역전(ports.py) 잘 지켜지나

B. **네이밍·타입 일관성**
   - Skill.kind ("prompt"|"flow") vs Bot.agent_type — 같은 enum, 다른 컬럼명
   - is_frontdoor flag vs Frontdoor 서비스 네이밍 충돌
   - graph: dict (raw JSON) — Pydantic schema 강제 부재
   - id 타입 (int vs str vs UUID) 일관성

C. **graph-ready 모델 완성도**
   - Skill.graph 실제 JSON schema 있나 (Pydantic 검증?)
   - Node·Edge·GlobalRule 도메인 객체로 표현되나, raw dict인가
   - 1-노드(프롬프트)와 N-노드(플로우) 동일 schema인가
   - entrypoint·nodes·edges·globals 필드 명시되어 있나

D. **CallbotAgent 컨테이너 마이그레이션 준비도** (신규 결정사항)
   - Bot 위에 CallbotAgent 컨테이너 도입 시 필요한 변경
   - Bot.branches 관계 → CallbotAgent.memberships(role) 매핑
   - voice·greeting·llm_model 평면 설정이 어디로 이동할지
   - 마이그레이션 시 backward-compat 가능한가

E. **VariableContext 도메인 부재**
   - 현재 변수 처리 위치 (mentions.py? prompts.py? skill_runtime?)
   - dynamic·system·extracted 3종 출처 구분 있나
   - {{var}} 치환이 통일된 한 곳에서 처리되나
   - 세션당 단일 객체로 관리되나

F. **Dispatcher · Global 룰 부재**
   - 라우팅 로직 위치 (skill_runtime.py의 LLM JSON 신호 파싱?)
   - global 룰 매칭 표현 방식 (현재는 prompt에 박힘)
   - 매 턴 첫 단계로 dispatcher 레이어 분리 가능한가
   - 우선순위 규칙 (bot > skill > global 룰) 정의되어 있나

G. **Doc ↔ Code drift**
   - VOX_AGENT_STRUCTURE 매핑표와 실제 코드 불일치
   - 문서가 너무 앞서가는지(설계만), 코드가 더 진행됐는지(언급 안 됨)
   - 신규 변경(CallbotAgent 등) 반영 시점

## Step 3 — 구체 조사
선택한 area에서 2~5개 파일 실제로 읽기. **file:line 참조 강제**.
추측 기반 평가 금지. Read 또는 Grep으로 확인 후 작성.

## Step 4 — ONE issue 선정
구체적 1개만. "전반적으로 정합성 떨어짐" 같은 추상 평가 금지.

좋은 예:
- "Skill.kind와 Bot.agent_type이 같은 enum인데 컬럼명 다름 → 공통 SkillMode 타입으로 통일 권장"
- "domain/entities.py에 Skill 도메인 객체 없음. SQLAlchemy 모델만 존재 → 도메인-인프라 의존성 역전 깨짐"
- "Skill.graph가 raw dict이고 Pydantic 검증 부재 → 잘못된 노드 type 저장 가능"

## Step 5 — 로그에 append
STRUCTURE_LOG.md의 ## Findings 섹션 끝에 다음 형식:

### Finding #N — <짧은 제목>
- **Area**: A~G 중 하나
- **Files**: file:line refs (2~5개)
- **Issue**: 무엇이 정합성 깨지나 / 개선 기회 (2-3줄)
- **Why it matters**: 누가·언제 영향받는가 (1-2줄)
- **Proposed change**: 어떻게 고칠지 (2-4줄, 옵션 1-2개)
- **Effort**: S(반나절) / M(1-3일) / L(1주+)
- **Impact**: P0(즉시) / P1(다음 phase) / P2(나중)
- **Status**: 신규

## Step 6 — 멈춤
- ONE finding만. 두 개 발견했으면 우선순위 높은 1개만 적고 나머지 버림.
- 코드 수정·파일 생성(로그 외) 금지.
- 사용자에게 한 줄 보고: "Finding #N <제목> 추가, area=<X>"

## 종료 조건
- A~G 모든 영역 1회 이상 커버 + findings 7개 이상 누적 → 다음 iteration에서:
  1. 로그 맨 위에 "## 정리(Triage)" 섹션 추가, P0/P1/P2 분류
  2. "loop 종료 권장" 보고
  3. ScheduleWakeup 호출하지 않음 (loop 자연 종료)
- 또는 3회 연속 새 발견 없음 → 동일 종료
```

---

## 누적 로그 템플릿 (loop가 처음 만들 때)

`STRUCTURE_LOG.md` 파일이 없으면 아래 내용으로 생성:

```markdown
# aicx-callbot 구조 정합성 점검 로그

> `/loop STRUCTURE_LOOP_PROMPT.md` 가 iteration마다 한 finding씩 append.

## Findings

(아직 없음 — 첫 iteration에서 추가됨)
```

---

## 사용 예시

```
/loop 첫 iteration이면 aicx-callbot/docs/plans/STRUCTURE_LOOP_PROMPT.md 의
"메타 프롬프트" 코드블록을 따라라. 이후 iteration도 동일.
```

또는 메타 프롬프트 전체를 그대로 `/loop` 인자로 붙여넣기.

---

## 왜 이렇게 짰는가

- **ONE finding 룰**: 한 번에 여러 개 찾으면 깊이가 얕아짐. 강제 좁히기.
- **7개 영역 로테이션**: 한 곳만 파지 않게. 정합성은 여러 레이어 교차 검증이 핵심.
- **file:line 강제**: 추측 기반 "이건 안 좋다" 식 평가 방지.
- **Doc ↔ Code drift 영역(G)**: 설계 문서와 코드가 갈라지는 게 가장 위험. 매 iteration 점검 후보.
- **코드 수정 금지**: 메모리 `feedback_no_premature_build` 준수. 로그만 누적, 빌드는 별도 사이클.
- **명시적 종료**: 7+ findings & 7 영역 모두 커버 시 P0/P1/P2 정리하고 자동 종료.

---

## REVIEW_LOOP_PROMPT.md와의 차이

| | REVIEW (어색함 점검) | STRUCTURE (정합성 점검) |
|---|---|---|
| 대상 | UI·UX·전반적 어색함 | 데이터 모델·도메인·API·프론트 구조 정합성 |
| 영역 수 | 6개 (UI 중심) | 7개 (구조 중심) |
| Finding 형식 | Awkwardness / Why / Fix | Issue / Why / Proposed change |
| 결과 활용 | UX 개선 백로그 | 리팩터링·마이그레이션 작업 입력 |

두 loop은 **동시 실행 가능** (다른 로그 파일에 적힘). 단, 같은 시점에 둘 다 돌리면 컨텍스트 분산되므로 영역별 우선 1개씩만 권장.
