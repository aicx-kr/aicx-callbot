# docs/plans — 설계·로그 문서 색인

코드만 보고는 파악하기 힘든 *결정의 이유*·*진행 누적*·*검토 메모*가 모이는 곳.

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
