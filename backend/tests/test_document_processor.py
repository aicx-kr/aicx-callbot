"""callbot_v0 흡수 — document_processor 외부 RAG 회귀 가드.

env 미설정 시 graceful fallback, inquiry_types 파서 동작, 결과 포맷 검증.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.infrastructure.adapters.document_processor import (
    DocSearchResult,
    _parse_inquiry_types,
    format_results_for_prompt,
    search,
)


def test_parse_inquiry_types_json_array():
    assert _parse_inquiry_types('["mypack","accommodation"]') == ["mypack", "accommodation"]


def test_parse_inquiry_types_csv():
    assert _parse_inquiry_types("mypack, accommodation,air_international") == [
        "mypack", "accommodation", "air_international",
    ]


def test_parse_inquiry_types_empty_defaults_to_general():
    assert _parse_inquiry_types("") == ["general"]
    assert _parse_inquiry_types("   ") == ["general"]


def test_parse_inquiry_types_malformed_json_falls_back_to_csv():
    # JSON 파싱 실패하면 comma split
    assert _parse_inquiry_types('[bad json') == ["[bad json"]


def test_search_empty_url_returns_empty(monkeypatch):
    """env 미설정 — 외부 호출 없이 즉시 빈 결과 (graceful fallback).
    실 env가 설정돼 있어도 테스트는 격리 (monkeypatch).
    """
    from src.core.config import settings
    monkeypatch.setattr(settings, "document_processor_base_url", "")
    async def run():
        results = await search(query="hello", inquiry_types=["mypack"])
        return results
    assert asyncio.run(run()) == []


def test_search_empty_query_returns_empty(monkeypatch):
    """빈 query는 호출 안 함."""
    from src.core.config import settings
    monkeypatch.setattr(settings, "document_processor_base_url", "https://example.invalid")
    async def run():
        return await search(query="   ", inquiry_types=["mypack"])
    assert asyncio.run(run()) == []


def test_format_results_empty():
    assert format_results_for_prompt([]) == ""


def test_format_results_basic():
    rs = [
        DocSearchResult(text="환불 정책: 7일 전 전액.", score=0.9, source_title="환불 가이드",
                        section_title="환불", knowledge_type="qa", rerank_score=0.95),
        DocSearchResult(text="고객센터 09~18시.", score=0.7, source_title="고객센터",
                        section_title="", knowledge_type="qa", rerank_score=None),
    ]
    out = format_results_for_prompt(rs)
    assert "외부 지식" in out
    assert "환불 가이드" in out
    assert "환불 정책: 7일 전 전액." in out
    assert "고객센터" in out


def test_format_results_truncates_by_max_chars():
    long = "긴 내용 " * 1000  # ~7000자
    rs = [DocSearchResult(text=long, score=1.0, source_title="big", section_title="",
                          knowledge_type="qa", rerank_score=None)]
    out = format_results_for_prompt(rs, max_chars=200)
    assert len(out) <= 400  # 헤더 + 한 chunk 포함은 가능하지만 두 번째 chunk는 잘림
