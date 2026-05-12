# callbot-platform 어색함 점검 — `/loop` 메타 프롬프트

> 사용법: `/loop <아래 프롬프트 전체>` (간격 생략 → 모델 자율 페이싱)
> 누적 로그: `callbot-platform/docs/plans/AWKWARDNESS_LOG.md` (loop가 자동 생성/append)
> 작성: 2026-05-11

---

## 메타 프롬프트 (이 블록을 그대로 `/loop` 인자로)

```
당신은 callbot-platform/ 을 디자인 관점에서 리뷰한다.
한 iteration에 ONE specific awkwardness만 찾아 누적 로그에 append한다.
**코드 수정 절대 금지. 분석/설계 단계다.** (memory: feedback_no_premature_build)

참고 기준 문서:
- callbot-platform/docs/plans/VOX_AGENT_STRUCTURE.md (vox 에이전트 구조 분석)
- callbot-platform/docs/plans/VOX_INSOURCING_DESIGN.md (인소싱 설계)
- memory: project_vox_ui_reference (vox echo UI 참고 패턴)

## Step 1 — 누적 로그 읽기
callbot-platform/docs/plans/AWKWARDNESS_LOG.md 를 읽는다.
- 파일이 없으면 새로 만든다 (아래 §로그 템플릿 사용)
- 이미 적힌 finding들의 Area를 기억해 두기 (중복 금지)

## Step 2 — 점검 영역 로테이션
다음 6개 영역 중 ONE 만 고른다. 최근 3개 finding이 이미 다룬 영역은 건너뛴다.

A. **프롬프트 ↔ 플로우 에이전트 통합**
   - FlowEditor.tsx ↔ MarkdownEditor.tsx 가 분리되어 있는가
   - 모드 전환 시 데이터 손실/혼란 가능성
   - Skill 도메인 모델이 graph-ready인가 (1-노드 그래프로 프롬프트 모드 표현 가능?)
   - transfer-agent 핸드오프 흐름 표현 여부

B. **프론트엔드 UI/UX**
   - Sidebar.tsx, Header.tsx, Shell.tsx 의 vox echo 패턴 부합도
   - 워크스페이스/봇/버전 셀렉터, 배포 버튼 위치
   - 마크다운/Monaco 에디터 일관성
   - TestPanel.tsx 라이브 채팅의 어색함 (latency/cost 표시, turn 단위 시각화)
   - Waterfall.tsx (호출 시각화) 와의 연계

C. **백엔드 도메인/애플리케이션 레이어**
   - backend/src/domain/, application/ 의 Skill/Persona/Tool/Knowledge 모델
   - graph-ready 여부 (nodes, edges, globals 필드)
   - VariableContext 통합 여부 (dynamic·system·extracted 한 객체?)

D. **테스트 패널 & 라이브 통화 UX**
   - TestPanel.tsx 흐름이 실제 콜봇 테스트(WebSocket 텍스트+음성, turn별 메타) 시나리오와 맞나
   - 인터럽트(global 노드) 발동 시각화

E. **변수 컨텍스트 / 도구 / 지식 통합**
   - 모든 노드/프롬프트에서 {{var}} 치환 가능한 구조인가
   - RestToolEditor.tsx 가 vox API 도구 모델과 정합한가
   - Knowledge 3종(text/webpage/file) 입력 UX

F. **어드민 어포던스**
   - 배포 버튼·버전 스냅샷 UI
   - 멀티테넌트(워크스페이스) 전환
   - 권한·역할 표면

## Step 3 — 구체적으로 조사
선택한 영역에서 2~5개 파일을 실제로 읽는다. 발견한 어색함의 근거로 file:line 형태 참조를 남긴다.
(Read tool 또는 Grep 사용. 추측 금지, 파일 확인 후 작성.)

## Step 4 — ONE specific awkwardness 고르기
"전체적으로 별로다", "리팩터링 필요" 같은 추상 평가 금지.
구체적 한 가지만. 예:
- "FlowEditor와 MarkdownEditor가 별도 라우트라 모드 간 동일 Skill 편집 불가"
- "Sidebar에 워크스페이스 셀렉터 없음 (vox echo 패턴 §1)"
- "Skill 도메인 모델에 globals 필드 없음 — 인터럽트 핸들러 표현 불가"

## Step 5 — 누적 로그에 append
AWKWARDNESS_LOG.md 의 ## Findings 섹션 끝에 아래 형식으로 추가:

### Finding #N — <짧은 제목>
- **Area**: <A~F 중 하나>
- **Files**: <file:line refs>
- **Awkwardness**: <2-3줄 — 무엇이 어색한가>
- **Why it matters**: <1-2줄 — 사용자/개발자에게 어떤 영향>
- **Proposed fix**: <2-4줄 — 어떻게 고치면 되나, 가능하면 옵션 1-2개>
- **Effort**: S / M / L
- **Found**: 2026-05-11 (iteration N)

## Step 6 — 멈추기
- 한 iteration에 ONE finding. 두 개 찾았으면 우선순위 1개만 적고 다른 하나는 버린다.
- 코드 수정·파일 생성(로그 외) 금지.
- 사용자에게 한 줄 요약만 보고: "Finding #N <제목> 추가, area=<X>"

## 종료 조건
- Findings 5개 이상 모이고 모든 영역(A–F) 1회 이상 커버됨 → 다음 iteration 에서 로그 맨 위에 "## 정리(Triage)" 섹션을 추가해 P0/P1/P2로 분류한 뒤, 사용자에게 "loop 종료 권장" 보고하고 ScheduleWakeup 호출하지 않음 (loop 자연 종료).
- 3회 연속 새 finding 없음 (모든 영역에서 의미있는 어색함 추가 없음) → 동일 종료.
```

---

## 누적 로그 템플릿 (loop가 처음 만들 때 사용)

`AWKWARDNESS_LOG.md` 파일이 없으면 아래 내용으로 생성:

```markdown
# callbot-platform 어색함 점검 로그

> `/loop REVIEW_LOOP_PROMPT.md` 가 iteration마다 한 finding씩 append.
> 시작: 2026-05-11

## Findings

(아직 없음 — 첫 iteration에서 추가됨)
```

---

## 사용 예시

```
/loop 아래 메타 프롬프트 …  # 위 코드블록 전체 붙여넣기
```

또는 짧게:

```
/loop 첫 iteration이면 callbot-platform/docs/plans/REVIEW_LOOP_PROMPT.md 를 읽고 그 안의 "메타 프롬프트" 코드블록을 따라라. 이후 iteration도 동일.
```

---

## 왜 이렇게 짰는가

- **ONE finding 룰**: 한 번에 여러 개 찾으면 깊이가 얕아짐. 강제 좁히기.
- **영역 로테이션**: 같은 곳만 파지 않게. 6개 영역 골고루.
- **누적 로그 강제**: iteration 간 메모리 공유 (Claude 자체 메모리 의존 X).
- **코드 수정 금지**: 메모리 `feedback_no_premature_build` 준수.
- **명시적 종료 조건**: loop가 영원히 돌지 않도록 P0/P1/P2 정리 후 자연 종료.
- **file:line 참조 강제**: 추측 기반 평가 방지.
