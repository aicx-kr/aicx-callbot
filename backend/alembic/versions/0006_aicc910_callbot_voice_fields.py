"""AICC-910 — CallbotAgent 음성 동작 필드 확장.

추가 컬럼:
  - greeting_barge_in (Boolean)         — (a) 인사말 중 끼어들기 허용 여부
  - idle_prompt_ms / idle_terminate_ms  — (b) 무응답 자동 종료 (ms)
  - idle_prompt_text (String 500)       — (b) 침묵 시 재안내 멘트
  - tts_pronunciation (JSON)            — (d) TTS 텍스트 치환용 (pronunciation_dict 와 분리)
  - stt_keywords (JSON)                 — (d) STT phrase hint (도메인 키워드 인식률 보정)
  - tts_speaking_rate (Float)           — (e) 발화 속도 0.5~2.0
  - tts_pitch (Float)                   — (e) 피치 -20.0~20.0 semitones
  - llm_thinking_budget (Integer NULL)  — (f2) Gemini ThinkingConfig.thinking_budget
                                          NULL=SDK 기본(dynamic), 0=off, -1=dynamic, N>0=토큰 한도

데이터 이전:
  - 기존 pronunciation_dict (단일 통합) → tts_pronunciation 으로 복사. pronunciation_dict
    컬럼 자체는 레거시 호환을 위해 유지 (drop 안 함).
  - tts_pronunciation 의 잔여 NULL 은 '{}' 로, stt_keywords 는 '[]' 로 백필.
  - 백필 완료 후 두 컬럼 NOT NULL alter — 도메인 default ({} / []) 와 정합.

dtmf_map 스키마 변경 ({"1": "텍스트"} → {"1": {"type":..., "payload":...}}) 은
도메인의 `CallbotAgent.normalized_dtmf_map()` 가 read 시 정규화하므로 Alembic 단계에서는
컬럼 변경 없음. UI/API 는 신규 형태로 read/write 한다.

Revision ID: 0006_aicc910_callbot_voice_fields
Revises: 0005_aicc909
Create Date: 2026-05-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_aicc910_callbot_voice_fields"
down_revision: Union[str, Sequence[str], None] = "0005_aicc909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("callbot_agents") as batch_op:
        batch_op.add_column(sa.Column("greeting_barge_in", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("idle_prompt_ms", sa.Integer(), nullable=False, server_default="7000"))
        batch_op.add_column(sa.Column("idle_terminate_ms", sa.Integer(), nullable=False, server_default="15000"))
        batch_op.add_column(sa.Column("idle_prompt_text", sa.String(500), nullable=False, server_default="여보세요?"))
        batch_op.add_column(sa.Column("tts_pronunciation", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("stt_keywords", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("tts_speaking_rate", sa.Float(), nullable=False, server_default="1.0"))
        batch_op.add_column(sa.Column("tts_pitch", sa.Float(), nullable=False, server_default="0.0"))
        # (f2) NULL 허용 — SDK 기본(dynamic)에 위임하는 봇은 NULL 로 둔다.
        batch_op.add_column(sa.Column("llm_thinking_budget", sa.Integer(), nullable=True))

    # 기존 pronunciation_dict 가 비어 있지 않은 경우 tts_pronunciation 으로 복사.
    # SQLite + Postgres 모두 호환: JSON 컬럼간 단순 대입.
    bind = op.get_bind()
    bind.exec_driver_sql(
        "UPDATE callbot_agents SET tts_pronunciation = pronunciation_dict "
        "WHERE pronunciation_dict IS NOT NULL AND tts_pronunciation IS NULL"
    )
    # 잔여 NULL — pronunciation_dict 자체가 NULL 이거나 두 컬럼 다 NULL 인 row 까지 빈 객체로 채움.
    bind.exec_driver_sql(
        "UPDATE callbot_agents SET tts_pronunciation = '{}' "
        "WHERE tts_pronunciation IS NULL"
    )
    bind.exec_driver_sql(
        "UPDATE callbot_agents SET stt_keywords = '[]' "
        "WHERE stt_keywords IS NULL"
    )

    # 백필 완료 후 NOT NULL alter — 도메인 default ({} / []) 와 정합 강제.
    # JSON 컬럼 server_default 는 dialect 별 cast 이슈가 있어 add_column 시점이 아니라
    # 백필 후 별도 alter 로 처리.
    with op.batch_alter_table("callbot_agents") as batch_op:
        batch_op.alter_column("tts_pronunciation", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("stt_keywords", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("callbot_agents") as batch_op:
        batch_op.drop_column("llm_thinking_budget")
        batch_op.drop_column("tts_pitch")
        batch_op.drop_column("tts_speaking_rate")
        batch_op.drop_column("stt_keywords")
        batch_op.drop_column("tts_pronunciation")
        batch_op.drop_column("idle_prompt_text")
        batch_op.drop_column("idle_terminate_ms")
        batch_op.drop_column("idle_prompt_ms")
        batch_op.drop_column("greeting_barge_in")
