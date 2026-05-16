# callbot-platform 자잘한 이슈 + UI 어색함 `/loop` 점검·수정 메타 프롬프트

> 사용법: `/loop callbot-platform/docs/plans/FIX_LOOP_PROMPT.md 대로 진행`
> 누적 로그: `callbot-platform/docs/plans/FIX_LOG.md` (loop가 자동 생성/append)
> 작성: 2026-05-11
> 차이: 이전 `REVIEW_LOOP_PROMPT.md`는 "분석만" 룰. 이번 prompt는 **"ONE iteration = ONE fix (분석 + 수정 + 검증)"** 룰.

---

## 메타 프롬프트 (이 블록을 그대로 `/loop` 인자로)

```
당신은 callbot-platform/ 의 자잘한 버그·UI 어색함을 한 iteration에 하나씩 잡는다.

기본 룰:
- 한 iteration에 ONE 구체적 어색함/버그만 잡는다 (전체적 리팩터 금지).
- 코드 수정 OK. 분석만 하지 말고 fix 적용 + 검증까지 한 사이클에서 완료.
- 검증 없는 fix 금지: 백엔드는 httpx/websockets로 e2e, 프론트는 페이지 컴파일 + 동작.
- 사용자 직접 보고 이슈(seed)는 모두 fixed 될 때까지 우선 처리.

참고 문서:
- callbot-platform/docs/plans/VOX_AGENT_STRUCTURE.md (vox 구조)
- callbot-platform/docs/plans/VOX_INSOURCING_DESIGN.md (인소싱 설계)
- callbot-platform/docs/plans/AWKWARDNESS_LOG.md (이전 분석 사이클 결과 — P0/P1/P2)
- memory: project_vox_ui_reference (vox echo UI 패턴)

## Step 1 — 누적 로그 읽기
callbot-platform/docs/plans/FIX_LOG.md 읽기.
- 파일이 없으면 §로그 템플릿으로 새로 만들기.
- 이미 적힌 fix들의 Area/제목 확인 (중복 방지).

## Step 2 — 점검 영역 로테이션
8개 영역 중 ONE 선택. 최근 3개 iter가 다룬 영역은 건너뛰기 (단 seed 이슈는 영역 무관 우선).

1. **UI 상호작용** — onChange/onClick/dirty state, 키보드(Enter/Esc), 폼 검증, 저장 후 갱신
2. **시각 일관성** — 다크모드 누락, 색·여백·typography 불일치, 정렬, hover/focus 상태
3. **빈/에러 상태** — empty state 일러스트, error toast, 401/404/500 처리, 네트워크 실패 안내
4. **반응형** — 작은 화면, 사이드바 collapse, 테이블 가로 스크롤, 모달 모바일
5. **접근성** — aria-label, role, 키보드 탐색, focus ring, alt text, contrast
6. **데이터 흐름** — SWR mutate 누락, 낙관적 업데이트, 캐시 무효화, 저장 후 UI 동기화
7. **음성/통화 흐름** — 보이스 적용 여부, echo 차단, 인사말 회귀, state 머신, 인터럽트
8. **Waterfall/Trace 시각화** — 시간축, 막대 폭, hover/click 상세, 색 카테고리, 노드 라벨 가독성

## Step 3 — 사용자 보고 Seed 이슈 우선 처리
다음은 사용자가 직접 보고한 이슈다. iteration 1~N에서 우선 fix:

| Seed | 이슈 | Hint Area | Status |
|---|---|---|---|
| S1 | 페르소나의 voice 셀렉터를 바꾸면 통화에 적용 안 됨 | 6/7 | OPEN |
| S2 | Waterfall이 여전히 어색 (정렬/색/막대/툴팁) | 8 | OPEN |
| S3 | 사이드바 워크스페이스 selector dead UI (클릭해도 무동작) | 1 | OPEN |
| S4 | 폼 저장 후 toast/피드백 없이 silent | 1/6 | OPEN |
| S5 | TestPanel 봇 자기 음성 echo 회귀 가능성 | 7 | OPEN |
| S6 | 자잘한 UI/UX 어색함 (자유 발견) | * | OPEN |

새 사용자 보고가 들어오면 Seed 표에 추가 후 우선 처리.

## Step 4 — 조사
영역의 2~5개 파일 실제로 읽기. file:line 참조.
- 보이스 미적용이면: persona/page.tsx, voice_session.py의 TTS 호출, GCP/브라우저 모드별 차이.
- Waterfall이면: Waterfall.tsx, calls/[sid]/page.tsx, traces API 응답.
- 사이드바 워크스페이스면: Sidebar.tsx, tenants/page.tsx, bots API.
- 추측 금지 — 파일 읽고 확인 후 작성.

## Step 5 — ONE 이슈 확정
"전체적으로 별로다", "리팩터 필요" 같은 추상 평가 금지.
구체적 한 가지. 예:
- "보이스 셀렉터 변경 후 백엔드는 새 voice를 받지만 GCP TTS 모드에서만 차이 — 브라우저 TTS는 OS voice 매핑 안 함"
- "Waterfall 막대 hover 시 tooltip 없음 — 클릭해야 우측 패널에 표시"
- "워크스페이스 selector 버튼에 onClick 없음 — Sidebar.tsx:38"

## Step 6 — 수정 + 검증
1. 코드 수정 (Edit/Write)
2. 백엔드 변경 시: `lsof -ti:8080 | xargs -r kill && PORT=8080 python main.py &` + 새 컬럼이면 `rm -f callbot.db`
3. 프론트 변경: HMR 자동. tail /tmp/web-dev.log로 컴파일 에러 확인.
4. 검증 — 가능한 방법 중 적합한 것:
   - REST: `httpx` 또는 `/usr/bin/curl`
   - WebSocket: `websockets` 라이브러리로 chat 시뮬레이션
   - 페이지: `curl -o /dev/null -w "%{http_code}"`
   - 단위 함수: python -c "from src.… import …; assert …"
5. 결과를 로그에 기록.

## Step 7 — 누적 로그 append
FIX_LOG.md 의 ## Fixes 섹션 끝에 추가:

### Fix #N — <짧은 제목>
- **Area**: <1~8 중>
- **Seed**: <S1~S6 중 또는 "자유 발견">
- **Symptom**: <사용자가 본 현상 1~2줄>
- **Root cause**: <code 어느 곳이 원인 — file:line>
- **Files changed**: <변경한 파일 리스트>
- **Verification**: <검증 명령 + 결과 한 줄>
- **Status**: ✅ FIXED
- **Fixed**: 2026-MM-DD (iter N)

## Step 8 — 사용자에게 1줄 보고
"Fix #N <제목> 적용 + 검증 통과. seed=<X>." 형식.
- 막힌 게 있으면 (검증 실패, 추가 정보 필요) BLOCKED 표시하고 사용자에게 묻기.
- 다음 iter를 ScheduleWakeup(1500s, prompt=원본 /loop 입력)으로 자동 예약.

## 종료 조건
- Seed S1~S5 모두 FIXED + 자유 발견 5개 이상 → 종료
- 또는 3회 연속 새 fix 추가 못함 (영역 다 돌아도 의미 있는 어색함 없음) → 종료
- 종료 시: FIX_LOG.md에 "## 정리" 추가, ScheduleWakeup 호출 안 함, 사용자에게 "loop 자연 종료" 보고.

## 안 하는 것
- 거대 리팩터 (Bot 모델 다시 만들기 등)
- 새 큰 기능 (Flow 실행 엔진 등 — 그건 별도 작업)
- 의존성 변경 (npm/pip 새 패키지) — 정말 필요할 때만
- 사용자 환경 (.env) 수정 — 코드만
```

---

## 누적 로그 템플릿 (loop가 처음 생성 시)

`FIX_LOG.md` 파일이 없으면 아래 내용으로:

```markdown
# callbot-platform 자잘한 이슈 + UI 어색함 수정 로그

> `/loop FIX_LOOP_PROMPT.md` 가 iteration마다 ONE fix씩 append.
> 시작: 2026-05-11

## Seed (사용자 직접 보고 이슈)

| ID | 이슈 | Status |
|---|---|---|
| S1 | 보이스 셀렉터 변경이 통화에 적용 안 됨 | OPEN |
| S2 | Waterfall 어색 (정렬/색/막대/툴팁) | OPEN |
| S3 | 사이드바 워크스페이스 selector dead UI | OPEN |
| S4 | 폼 저장 후 토스트/피드백 없음 | OPEN |
| S5 | TestPanel 봇 자기 음성 echo 회귀 가능성 | OPEN |

## Fixes

(아직 없음 — 첫 iteration에서 추가됨)
```

---

## 사용 예시

```
/loop callbot-platform/docs/plans/FIX_LOOP_PROMPT.md 대로 진행
```

또는:

```
/loop 첫 iteration이면 callbot-platform/docs/plans/FIX_LOOP_PROMPT.md 를 읽고 그 안의 "메타 프롬프트" 블록을 따라라. 이후 iteration도 동일.
```

---

## 설계 의도

- **ONE fix 룰**: 한 번에 하나만 — 한 사이클의 깊이 보장. 큰 작업은 여러 iter로 쪼개기.
- **Seed 우선**: 사용자가 직접 본 이슈는 영역 로테이션보다 우선.
- **검증 강제**: 코드 바꾸고 검증 안 하면 회귀 위험. e2e 또는 HTTP 200 최소.
- **누적 로그**: iter 간 메모리 (Claude 자체 메모리 의존 X).
- **file:line 참조**: 추측 기반 fix 방지.
- **자연 종료**: Seed 다 끝 + 5개 자유 발견 또는 3회 무수확 시 멈춤.
- **REVIEW_LOOP와 차이**: 그건 분석 전용(코드 수정 금지), 이건 수정·검증까지.
