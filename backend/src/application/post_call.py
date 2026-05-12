"""통화 후 LLM 후처리 — 요약 + 정보 추출.

세션이 ended되면 비동기로 트리거. LLM이 트랜스크립트 전체를 읽고:
- summary: 한 문단 요약
- intent: 사용자 주된 의도
- sentiment: positive/neutral/negative
- resolved: 해결 여부 (true/false/unclear)
- entities: 예약번호, 일정 등 추출 (있는 만큼)
- next_action: 운영자가 해야 할 후속 액션 (있으면)
"""

from __future__ import annotations

import json
import logging
import re

from ..domain.ports import LLMPort
from ..infrastructure import models
from ..infrastructure.db import SessionLocal

logger = logging.getLogger(__name__)


POST_CALL_PROMPT_HEADER = """\
당신은 콜봇 통화 분석 어시스턴트입니다. 아래 통화 트랜스크립트를 읽고 JSON 한 객체만 출력하세요.

# 필수 필드
- summary (string, 1~2문장 한국어 요약)
- intent (string, 사용자 주된 의도. 예: '환불 안내', '예약 변경', 'FAQ', '기타')
- sentiment (string, 'positive' | 'neutral' | 'negative')
- resolved (string, 'true' | 'false' | 'unclear')
- entities (object, 추출한 핵심 정보 키/값. 예약번호 등이 있으면 담아라. 없으면 빈 객체)
- next_action (string, 운영자가 해야 할 후속 액션. 없으면 빈 문자열)

# 트랜스크립트
"""

POST_CALL_PROMPT_FOOTER = "\n\n# 출력\nJSON 외 다른 문자는 절대 출력하지 말 것."


async def analyze_session(session_id: int, llm: LLMPort, model: str = "gemini-3.1-flash-lite") -> None:
    """세션 종료 후 호출. DB를 새로 열어 분석 결과 저장."""
    db = SessionLocal()
    try:
        sess = db.get(models.CallSession, session_id)
        if not sess:
            return
        if not sess.transcripts:
            sess.analysis_status = "failed"
            sess.summary = "트랜스크립트 없음"
            db.commit()
            return

        sess.analysis_status = "pending"
        db.commit()

        transcript = "\n".join(
            f"{t.role}: {t.text}" for t in sess.transcripts if t.is_final
        )
        prompt = POST_CALL_PROMPT_HEADER + transcript[:8000] + POST_CALL_PROMPT_FOOTER

        try:
            resp = await llm.generate(system_prompt="너는 통화 분석 어시스턴트다.", user_text=prompt, model=model)
            data = _extract_json(resp.text or "")
            if not data:
                raise ValueError("JSON 파싱 실패")
            sess.summary = (data.get("summary") or "")[:1000]
            sess.extracted = {
                "intent": data.get("intent", ""),
                "sentiment": data.get("sentiment", ""),
                "resolved": data.get("resolved", ""),
                "entities": data.get("entities", {}) or {},
                "next_action": data.get("next_action", ""),
            }
            sess.analysis_status = "done"
        except Exception as e:
            logger.exception("post-call analysis failed: %s", e)
            sess.analysis_status = "failed"
            sess.summary = f"분석 실패: {e}"
        db.commit()
    finally:
        db.close()


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(s: str) -> dict | None:
    if not s:
        return None
    s = s.strip()
    # ```json ... ``` 제거
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.DOTALL)
    m = _JSON_BLOCK.search(s)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
