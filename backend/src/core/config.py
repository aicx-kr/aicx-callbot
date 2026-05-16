"""애플리케이션 설정. .env 또는 환경변수에서 로드."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host: str = "0.0.0.0"
    # 기본 8080 — 회사 EKS 노드 SG 의 ALB inbound rule 이 3000-8080 범위라 그 안의 표준 포트로 통일.
    # frontend/next.config.js 의 API_TARGET 기본값과 일치. 다른 포트로 띄울 땐 PORT 환경변수 override
    # + frontend BACKEND_URL 도 함께 맞춰야 함.
    port: int = 8080
    # Async URL — postgresql+asyncpg://... 또는 sqlite+aiosqlite:///./callbot.db
    database_url: str = "sqlite+aiosqlite:///./callbot.db"

    # Provider selection (google | mock)
    provider_stt: str = "google"
    provider_tts: str = "google"
    provider_llm: str = "google"
    provider_vad: str = "silero"

    # Google
    google_application_credentials: str = ""
    google_cloud_project: str = ""
    # Base64-encoded service account JSON (chatbot-v2 호환). 비어 있으면 ADC fallback.
    google_service_account_base64: str = ""
    # GEMINI_API_KEY 또는 GOOGLE_API_KEY 환경변수 둘 다 인식 (chatbot-v2 호환)
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    gemini_model: str = "gemini-2.5-flash"

    # Speech
    stt_language: str = "ko-KR"
    stt_sample_rate: int = 16000
    tts_language: str = "ko-KR"
    tts_voice: str = "ko-KR-Neural2-A"
    tts_sample_rate: int = 16000

    # VAD
    vad_silence_ms: int = 600
    vad_min_speech_ms: int = 200

    # Preemptive runtime prefetch (callbot_v0 흡수 #3)
    # STT interim 텍스트가 N자 이상이면 build_runtime을 백그라운드로 미리 실행해 TTFF 절감.
    # 0이면 비활성화. 음수 무의미.
    preempt_min_chars: int = 5

    # Native function calling tool loop (callbot_v0 흡수 #1)
    # LLM이 tool_call → 결과 주입 → 다음 응답 루프의 최대 반복 횟수. 무한 루프 방어.
    tool_loop_max_iterations: int = 3

    # callbot_v0 흡수 — document-processor 외부 RAG (Notion 기반 지식 검색)
    # base_url 비어 있으면 비활성. 봇별 external_kb_enabled로도 토글 가능.
    document_processor_base_url: str = ""
    document_processor_tenant_id: int = 0
    # JSON 배열 문자열 (예: '["mypack","accommodation"]'). 빈 문자열은 ["general"] 기본.
    document_processor_inquiry_types: str = ""
    document_processor_top_k: int = 5
    document_processor_timeout_s: float = 5.0

    # AICC-909 — 로깅·관측성 인프라
    # JSON 로그 레벨 (DEBUG/INFO/WARNING/ERROR). uvicorn 의 logging-level 과 별개.
    log_level: str = "INFO"
    # Slack 인시던트 알림 webhook. 비면 Slack 핸들러 미부착 (개발 환경 기본 동작).
    slack_webhook_url: str = ""
    # 같은 (logger, msg_template) 키 윈도우 — 같은 에러 100x burst → Slack 1회.
    slack_rate_limit_window_s: float = 60.0


settings = Settings()
