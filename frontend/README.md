# frontend — Next.js 콘솔 (port 3000)

Next.js 15 App Router + React 19 + Tailwind + SWR. 백엔드(`port 8080`)가 먼저 떠 있어야 함.

```bash
npm install
npm run dev
# → http://localhost:3000 → 첫 콜봇 메인 페르소나로 자동 redirect
```

---

## IA (Information Architecture)

```
사이드바
└─ 콜봇 (= 메인 에이전트 ─ 클릭 시 메인 페르소나로 직행)
   ├─ 페르소나        /bots/{mainBotId}/persona   ← 첫 화면
   │                   ├─ 워크플로우 그래프 (메인 → 서브 분기, drag/edit)
   │                   ├─ 통화 일관 설정 (voice/언어/LLM/인사말) — CallbotAgent PATCH
   │                   └─ 페르소나/system_prompt
   ├─ 지식 / 스킬 / 도구 / MCP / 환경변수
   ├─ 콜봇 → 에이전트 관리  /callbot-agents/{id}  (서브 추가·트리거 편집)
   └─ 통화 로그 / 고객사
```

서브 봇 클릭 시(에이전트 관리에서) `/bots/{subBotId}/persona` — 거기선 통화 일관 설정 hide (메인을 따름 안내).

---

## 디렉토리

```
src/
├── app/                      App Router 페이지
│   ├── page.tsx              루트 → 첫 콜봇 메인 페르소나 redirect
│   ├── tenants/page.tsx
│   ├── agents/page.tsx       전체 봇 일람 + 새 에이전트 생성
│   ├── callbot-agents/[id]/  에이전트 관리 (서브·트리거·구성도)
│   └── bots/[botId]/
│       ├── layout.tsx        Sidebar + 우측 TestPanel
│       ├── persona/page.tsx  ⭐ 메인 화면
│       ├── skills/  knowledge/  tools/  mcp/  env/  flow/
│       ├── settings/         agent_type 토글 (prompt ↔ flow), RAG 토글
│       └── calls/[sid]/      통화 상세 (Waterfall / 트랜스크립트 / 도구)
├── components/               재사용 UI
│   ├── Sidebar.tsx
│   ├── TestPanel.tsx         우측 통화 시뮬레이션 (GCP/브라우저/텍스트 3모드)
│   ├── Waterfall.tsx         트레이스 시각화 (LangSmith 스타일)
│   ├── BranchesFlowView.tsx  메인→서브 노드 그래프 (drag-to-connect)
│   ├── MarkdownEditor.tsx    @-mention monaco editor
│   └── Toast.tsx             전역 토스트
└── lib/
    ├── api.ts                fetch wrapper + WebSocket URL
    ├── types.ts              Bot·CallbotAgent·Skill·Tool 등 타입
    └── voice-options.ts      KO_VOICES / LANGUAGES / LLM_MODELS (단일 진실)
```

---

## 룰 (자주 놓치는 것)

- **다크모드**: 모든 색상 클래스에 `dark:` 변형. 회귀가 잦으니 새 컴포넌트마다 다크모드에서 한 번 확인
- **SWR mutate**: 저장 후 `mutate()` + 사이드바·다른 페이지 캐시 영향이면 `globalMutate('/api/bots')` 추가
- **Toast 일관**: 모든 save는 `const toast = useToast()` + try/catch + success/error 메시지
- **Voice options**: KO_VOICES/LLM_MODELS 같은 옵션 상수는 `lib/voice-options.ts`에 한 곳만 — 페이지 안에서 다시 정의 X

---

## TestPanel

우측 사이드 통화 시뮬레이션. `voiceModeAvailable` 우선 → 'gcp' 기본, fallback 브라우저 SR → 텍스트.

- VARS 토글로 통화 시작 시 `dynamic_vars` 주입
- 봇 응답 + tool 호출 페어 카드 + 상태 라벨 (대기/고객 발화중/생각 중/말하는 중) 색상 일관
