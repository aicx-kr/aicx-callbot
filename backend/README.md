# backend — FastAPI 콜봇 서버 (port 8765)

Clean Architecture 4층으로 나뉘어 있다. 의존 방향은 **api → application → infrastructure → domain** (안쪽으로만).

```
src/
├── domain/          ① 가장 안쪽 — 비즈니스 규칙
├── application/     ② 협업 흐름·서비스
├── infrastructure/  ③ 외부 시스템 어댑터
├── api/             ④ HTTP·WebSocket 노출
└── core/            설정 (settings)
```

각 층의 자세한 내용은 그 디렉토리의 `README.md` 참조.

---

## 실행

```bash
# 1) 의존성 (uv 또는 pip)
# .env 또는 환경변수로 GCP 키 설정:
#   GOOGLE_SERVICE_ACCOUNT_BASE64=<base64 SA>  또는
#   GOOGLE_APPLICATION_CREDENTIALS=<file path>

# 2) 실행
PORT=8765 ./run.sh
# → uvicorn src.app:create_app --factory --port 8765
# → http://localhost:8765/api/health
# → 응답에 voice_mode_available=true 면 GCP 모드 사용 가능
```

GCP 키 없으면 자동으로 `MockSTT`/`MockTTS`/`MockVAD` 사용 → 텍스트 모드만 가능.

---

## 핵심 흐름 (음성 통화)

```
ws/voice.py (WebSocket)
   ↓
application/voice_session.py (상태 머신 + 오케스트레이션)
   ├─ infrastructure/adapters/silero_vad.py    → speech_start/end 이벤트
   ├─ infrastructure/adapters/google_stt.py    → interim + final
   ├─ application/skill_runtime.build_runtime  → system prompt 합성 (prefetch 가능)
   ├─ infrastructure/adapters/gemini_llm.py    → stream + function calling
   ├─ application/tool_runtime.execute_tool    → REST·Python·MCP·builtin
   └─ infrastructure/adapters/google_tts.py    → 문장 단위 streaming TTS
```

매 trace는 `application/tracer.py`로 DB 저장 → 콘솔 `/bots/N/calls/M` Waterfall에서 시각화.

---

## 테스트

```bash
# 단위 (도메인 invariant)
python tests/test_callbot.py            # CallbotAgent invariant 6개
python tests/test_global_rule.py        # GlobalRule dispatcher 6개
python tests/test_variable_context.py   # VariableContext 변환·resolve

# Smoke (서버 떠 있어야 함)
./scripts/smoke_test.sh                 # 32-point 헬스 체크

# E2E (WebSocket 시뮬레이션)
python scripts/e2e_call_scenario.py
```

---

## 자주 만지는 파일

| 일 | 파일 |
|---|---|
| 통화 흐름 (LLM/도구/TTS) | `application/voice_session.py` |
| 시스템 프롬프트 합성 | `application/skill_runtime.py` + `domain/prompts.py` |
| 새 도구 실행 타입 추가 | `application/tool_runtime.py` |
| 새 도메인 엔티티 | `domain/<name>.py` (+ port, repo, service, router) |
| GCP key 로딩 | `infrastructure/adapters/google_credentials.py` |
| 글로벌 룰 dispatcher | `domain/global_rule.py` + `voice_session._check_global_rules` |
