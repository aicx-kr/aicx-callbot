# docs/plans — 설계·로그 문서 색인

코드만 보고는 파악하기 힘든 *결정의 이유*·*진행 누적*·*검토 메모*가 모이는 곳.

폴더 구조 규칙·새 티켓 추가 절차는 본 문서 **§ 컨벤션** 참조.

---

## 설계 문서

| 파일 | 무엇 |
|---|---|
| **`CALLBOT_STRUCTURE_OVERVIEW.pdf`** | 한 페이지 구조 요약 — 4 핵심(누구·두 방식·통화 흐름·코드 원칙) + 시나리오 + § 7 결정 사항. PM/협업자 공유용 |
| **`VOX_AGENT_STRUCTURE.md`** | vox 매니지드 콜봇 패턴 상세 분석 + 우리 모델 정합화 |
| **`VOX_INSOURCING_DESIGN.md`** | vox 책임 분해 + 자체 구축 컴포넌트 매핑 + API/시퀀스 |
| **`BUILD-PROMPT.md`** / **`BUILD_PROMPT2.md`** | 빌드용 종합 프롬프트 (vox 내재화 프레이밍) |
| **`STRUCTURE_LOG.md`** | 구조 변경 결정 기록 (예: CallbotAgent 도입, 메인 ≡ 콜봇 통합) |
| **`PRODUCTION_READINESS.md`** | 운영 진입 체크리스트 (auth/RBAC, 인프라, 관측성) |

---

## Jira 티켓 계획 (2026-05-13)

상위 인덱스: **`2026-05-13-callbot-tickets-roadmap.md`** — 6개 티켓 한눈에 + 의존 + 결정 24개

| 티켓 | 문서 | 마일스톤 |
|---|---|---|
| AICC-907 | `AICC-907/2026-05-13-plan.md` | M1 |
| AICC-909 | `AICC-909/2026-05-13-plan.md` | M1 |
| AICC-910 | `AICC-910/2026-05-13-plan.md` | M2 |
| AICC-908 | `AICC-908/2026-05-13-plan.md` | M2 |
| AICC-912 | `AICC-912/2026-05-13-plan.md` | M3 |
| AICC-911 | `AICC-911/2026-05-13-plan.md` | M3 |

기존 상세 설계 (907/909 의 base): `2026-05-12-deploy-infra-and-db-design.md`, `2026-05-12-logging-observability-redesign.md`

---

## 자율 개선 로그

| 파일 | 무엇 |
|---|---|
| **`AUTO_LOOP_PROMPT.md`** | 자율 개선 사이클 메타 프롬프트 (270s마다 ONE 사이클, 카테고리 로테이션: 테스트·성능 → UI → 구조) |
| **`AUTO_LOOP_LOG.md`** | 사이클 누적 (#1~#37 + 1시간 자율 loop 정리) |
| **`STRUCTURE_LOOP_PROMPT.md`** | 구조 검토 전용 loop (분석 위주) |
| **`REVIEW_LOOP_PROMPT.md`** | 분석 전용 loop (수정 금지 — AWKWARDNESS_LOG에 P0/P1/P2 우선순위) |

---

## 버그 fix 로그

| 파일 | 무엇 |
|---|---|
| **`FIX_LOOP_PROMPT.md`** | "ONE iter = ONE fix" 룰 — 사용자 보고 Seed 우선 |
| **`FIX_LOG.md`** | fix 누적 (#1~#13 + 종료 정리) |
| **`AWKWARDNESS_LOG.md`** | UI/UX 어색함 진단 (P0/P1/P2) |

---

## 사용 예

새 사람이 들어왔을 때 추천 읽기 순서:

1. 루트 `README.md` — 전체 그림
2. `CALLBOT_STRUCTURE_OVERVIEW.pdf` — 한 페이지 모델
3. `CONTRIBUTING.md` (루트) — Clean Architecture 룰
4. `VOX_AGENT_STRUCTURE.md` — 통화 모델 상세
5. `FIX_LOG.md` + `AUTO_LOOP_LOG.md` 최신 10개 — 최근 변경 맥락

---

## 컨벤션

### 폴더 구조

```
docs/plans/
├── README.md                                  # 본 문서 — 색인 + 컨벤션
│
├── AICC-907/                                  # 티켓별 폴더 (Jira 키 그대로)
│   ├── 2026-05-13-plan.md
│   ├── 2026-05-20-review.md                  # 같은 티켓에 추후 문서 누적
│   └── ...
├── AICC-908/  ...
│
├── 2026-05-13-callbot-tickets-roadmap.md     # 여러 티켓 가로지르는 인덱스/로드맵 (루트)
├── 2026-05-12-deploy-infra-and-db-design.md  # 티켓 진입 전 기반 설계 (루트)
├── 2026-05-12-logging-observability-redesign.md
│
├── CALLBOT_STRUCTURE_OVERVIEW.pdf            # 상시 참조 설계 (대문자/언더스코어)
├── VOX_AGENT_STRUCTURE.md
├── VOX_INSOURCING_DESIGN.md
├── STRUCTURE_LOG.md
├── PRODUCTION_READINESS.md
│
├── AUTO_LOOP_PROMPT.md / AUTO_LOOP_LOG.md    # 자율 개선 (대문자/언더스코어)
├── STRUCTURE_LOOP_PROMPT.md
├── REVIEW_LOOP_PROMPT.md
│
├── FIX_LOOP_PROMPT.md / FIX_LOG.md           # 버그 fix
└── AWKWARDNESS_LOG.md
```

### 폴더 구분 — **티켓 키별 (`AICC-XXX/`)**

- **티켓이 있으면** Jira 키 그대로 폴더: `AICC-907/`, `AICC-1234/`
- **여러 티켓을 가로지르는** 인덱스·로드맵·기반 설계는 `plans/` 루트
- **상시 참조 / 누적 로그** (자율 개선, fix, 구조 변경 등) 도 `plans/` 루트 (대문자 파일명으로 구분)

**왜 티켓별인가** (날짜별 대신):
- 한 티켓에 시간이 지나면서 검토 노트·결정 변경·구현 메모가 쌓임 — 티켓이 자연스러운 작업 단위
- 날짜별이면 같은 티켓 추적할 때 여러 폴더 뒤져야 함
- Jira 와 1:1 매칭 → PR 제목/커밋 메시지에서 키만으로 폴더 추정 가능

### 파일 명명

| 위치 | 형식 | 예 |
|---|---|---|
| 티켓 폴더 안 | `YYYY-MM-DD-역할.md` | `AICC-907/2026-05-13-plan.md`, `AICC-907/2026-05-20-review.md` |
| 여러 티켓 가로지름 | `YYYY-MM-DD-주제.md` | `2026-05-13-callbot-tickets-roadmap.md` |
| 상시 참조 설계 | `대문자_언더스코어.md` | `STRUCTURE_LOG.md`, `PRODUCTION_READINESS.md` |
| 누적 로그 | `대문자_LOG.md` | `FIX_LOG.md`, `AUTO_LOOP_LOG.md` |

**역할 키워드** (티켓 폴더 안):
- `plan` — 초기 계획서
- `review` — 검토·재평가 노트
- `decision` — 사용자 확정 후 결정 사항 기록
- `impl-notes` — 구현 중 발견한 갭·디테일
- `postmortem` — 완료 후 회고

### 새 티켓 추가 절차

1. `docs/plans/AICC-{key}/` 폴더 생성
2. `AICC-{key}/YYYY-MM-DD-plan.md` 작성 — 아래 §템플릿 참조
3. `docs/plans/README.md` 의 "Jira 티켓 계획" 표에 1행 추가
4. 여러 티켓 가로지르는 로드맵이 있으면 거기에도 등록

### 템플릿 (티켓 plan.md 최소 구조)

```markdown
# AICC-XXX — <Jira 제목>

> Jira: <URL>
> 상태: TODO/진행 중/검토중 · 우선순위: · 기한: · 담당:
> 마일스톤: M? · 의존: AICC-YYY, ...
> 작성일: YYYY-MM-DD

## 1. 티켓 원문
배경/목적, 작업 내용, 완료 기준 인용

## 2. 현재 코드 상태
표 형태로 file:line + 상태 (있음/부분/없음)

## 3. 설계 / 잔여 작업

## 4. 결정 필요 항목
| # | 항목 | 옵션 | 권고 |

## 5. 마일스톤 출구 기준

## 6. 의존 관계

## 7. 참조
- 상위 인덱스: `../<roadmap>.md`
- 연관 티켓: `../AICC-YYY/...`
- 메모리: ...
```

### 문서 정리 / 삭제

- **티켓이 Done 처리되어도 폴더는 보존**. postmortem 추가 — 다음 인접 작업의 입력이 됨
- 잘못 만든 문서는 git 로 삭제 (rebase X — 이력 보존)
- 폴더 이동 시 본 README 의 표 + 다른 문서의 상대 경로 링크 모두 갱신

### 메모리 시스템과의 관계

- **메모리** (`~/.claude/.../memory/`) = 향후 대화에서 자동 회수되는 휘발성·짧은 컨텍스트 (사용자 프로필, 운영 룰, 외부 시스템 위치)
- **plans/** = 작업 산출물·결정 근거의 영구 기록
- 룰: 메모리에는 "어디 보면 뭐가 있다" + "왜 그렇게 일하는지", plans/ 에는 "무엇을 어떻게 만들 것인지"
