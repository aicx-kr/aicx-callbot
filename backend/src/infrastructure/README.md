# infrastructure — 외부 시스템 어댑터

DB / GCP / Gemini / VAD 같은 외부 의존을 domain port의 구현체로 감싼다.

## 무엇이 있나

```
infrastructure/
├── db.py                 SQLAlchemy engine + SessionLocal (expire_on_commit=False)
├── models.py             ORM 모델 (Tenant·CallbotAgent·Bot·Skill·Knowledge·Tool·MCPServer·CallSession·Transcript·Trace·ToolInvocation)
├── seed.py               초기 데이터 (테스트용 tenant·bot)
├── adapters/             외부 서비스 어댑터
│   ├── factory.py            voice_mode_available 판단 + 어댑터 생성
│   ├── google_credentials.py base64 SA 또는 파일 경로 로딩
│   ├── google_stt.py         GCP Speech-to-Text v1 streaming
│   ├── google_tts.py         GCP TTS Neural2/Wavenet (LINEAR16)
│   ├── gemini_llm.py         Gemini streaming + function calling
│   ├── silero_vad.py         Silero VAD (없으면 MockVAD fallback)
│   └── mock_providers.py     키 없을 때 fallback (텍스트 모드)
└── repositories/         SqlAlchemy 구현체 (domain Repository port)
    ├── tenant_repository.py
    ├── callbot_agent_repository.py
    ├── bot_repository.py
    ├── skill_repository.py
    ├── knowledge_repository.py
    ├── tool_repository.py
    └── mcp_server_repository.py
```

## Repository 패턴

각 repository는 두 함수만:
- `_to_domain(row)` — ORM row → domain entity dataclass 변환
- `_apply_to_row(row, entity)` — domain entity → ORM row 갱신

비즈니스 규칙은 안 가짐. 단순 CRUD.

## 어댑터 패턴

domain port를 구현. 예:
- `LLMPort` ← `GeminiLLM` 또는 `MockLLM`
- `STTPort` ← `GoogleSTT` 또는 `MockSTT`

`factory.py`가 환경에 따라 어느 구현체를 쓸지 결정 (GCP 키 존재 여부 등).

## 룰

- 비즈니스 규칙 절대 X — repository가 "메인 봇은 1명만" 같은 검사 하면 도메인 위반
- ORM 모델은 여기만 — application/api/domain에서 절대 import 금지 (단 application은 service 안에서 repository port만 사용)
- 어댑터는 외부 라이브러리 (google-cloud-speech, google-genai 등)를 *얇게* 감쌈
