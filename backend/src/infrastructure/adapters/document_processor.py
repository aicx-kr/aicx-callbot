"""document-processor 외부 RAG 클라이언트 (callbot_v0 흡수).

POST /search/filtered → tenant/inquiry_types 필터로 Notion 문서 검색.
base_url 비어 있으면 [] 반환 (graceful fallback — dev/test 친화).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass

import httpx

from ...core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocSearchResult:
    text: str
    score: float
    source_title: str
    section_title: str
    knowledge_type: str
    rerank_score: float | None


def _parse_inquiry_types(raw: str) -> list[str]:
    """env 문자열 → list. JSON 배열 또는 comma-separated 둘 다 허용."""
    raw = (raw or "").strip()
    if not raw:
        return ["general"]
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except json.JSONDecodeError:
            pass
    return [s.strip() for s in raw.split(",") if s.strip()]


async def search(
    *,
    query: str,
    inquiry_types: Iterable[str] | None = None,
    knowledge_types: Iterable[str] | None = None,
    top_k: int | None = None,
) -> list[DocSearchResult]:
    """document-processor /search/filtered 호출. 실패 시 빈 리스트.

    callbot_v0 패턴 그대로 — query/inquiry_types/knowledge_types/max_context_chunks.
    """
    base_url = (settings.document_processor_base_url or "").rstrip("/")
    if not base_url:
        return []
    if not query or not query.strip():
        return []

    inq = list(inquiry_types) if inquiry_types is not None else _parse_inquiry_types(settings.document_processor_inquiry_types)
    knw = list(knowledge_types) if knowledge_types is not None else ["qa"]
    k = top_k or settings.document_processor_top_k

    payload = {
        "q": query,
        "tenant_id": settings.document_processor_tenant_id,
        "facets": [{"name": "knowledge_type", "values": knw}],
        "filters": {"inquiry_types": inq},
        "max_context_chunks": k,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.document_processor_timeout_s) as client:
            resp = await client.post(f"{base_url}/search/filtered", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("document_processor HTTP %s: %s", e.response.status_code, e)
        return []
    except Exception as e:  # noqa: BLE001
        logger.warning("document_processor request failed: %s", e)
        return []

    out: list[DocSearchResult] = []
    for item in (data.get("data") or {}).get("results") or []:
        meta = item.get("metadata") or {}
        out.append(DocSearchResult(
            text=item.get("text", ""),
            score=float(item.get("score", 0.0)),
            source_title=meta.get("source_title", ""),
            section_title=meta.get("section_title", ""),
            knowledge_type=meta.get("knowledge_type", ""),
            rerank_score=meta.get("rerank_score"),
        ))
    return out


def format_results_for_prompt(results: list[DocSearchResult], max_chars: int = 4000) -> str:
    """검색 결과를 system_prompt에 붙일 [참고 지식] 섹션으로 포맷.

    토큰 폭증 방지를 위해 max_chars 상한.
    """
    if not results:
        return ""
    lines = ["# 외부 지식 (현재 발화 관련 검색 결과)"]
    total = 0
    for r in results:
        header = f"\n## {r.source_title or r.section_title or '(unnamed)'}"
        body = r.text.strip()
        chunk = f"{header}\n{body}"
        if total + len(chunk) > max_chars:
            break
        lines.append(chunk)
        total += len(chunk)
    return "\n".join(lines).strip()
