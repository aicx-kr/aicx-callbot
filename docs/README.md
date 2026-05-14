# docs/ — 진입점

코드만 보고는 알기 어려운 **결정의 이유** · **진행 누적** · **검토 메모** · **티켓별 계획서** 가 모이는 곳.

| 디렉토리 | 무엇 |
|---|---|
| [`plans/`](./plans/) | 모든 설계·계획·로그·티켓 문서. 자세한 분류와 컨벤션은 [`plans/README.md`](./plans/README.md) 참조 |

---

## 한 줄 운영 룰

- 코드와 git history 로 알 수 있는 것은 여기 쓰지 않는다 (CLAUDE.md 메모리 시스템도 같은 룰)
- 여기에 모이는 건 **왜 그렇게 했는지**, **어떤 결정을 미뤘는지**, **다음에 무엇을 할지** 같은 휘발성 컨텍스트
- 빌드/구현은 별도 — 본 디렉토리 문서는 **계획·기록**만, 코드 변경은 PR 로 ([[feedback_no_premature_build]])

## 새로 들어온 사람 추천 순서

1. 루트 [`README.md`](../README.md) · [`CONTRIBUTING.md`](../CONTRIBUTING.md) (Clean Architecture 룰)
2. [`plans/CALLBOT_STRUCTURE_OVERVIEW.pdf`](./plans/CALLBOT_STRUCTURE_OVERVIEW.pdf) — 한 페이지 모델
3. [`plans/VOX_AGENT_STRUCTURE.md`](./plans/VOX_AGENT_STRUCTURE.md) — 통화 모델 상세
4. [`plans/2026-05-13-callbot-tickets-roadmap.md`](./plans/2026-05-13-callbot-tickets-roadmap.md) — 현재 진행 중인 티켓 인덱스
5. [`plans/FIX_LOG.md`](./plans/FIX_LOG.md) + [`plans/AUTO_LOOP_LOG.md`](./plans/AUTO_LOOP_LOG.md) 최신 — 최근 변경 맥락
