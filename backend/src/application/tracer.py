"""TraceRecorder — VoiceSession 내부에서 turn/LLM/tool span을 DB에 기록.

프론트엔드 waterfall 뷰가 사용. async DB 세션 기반.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from ..infrastructure import models


class TraceRecorder:
    def __init__(self, db: AsyncSession, session_id: int):
        self.db = db
        self.session_id = session_id
        self._stack: list[int] = []

    async def start(
        self, name: str, kind: str = "span", parent_id: int | None = None, input: dict | None = None
    ) -> tuple[int, float]:
        if parent_id is None and self._stack:
            parent_id = self._stack[-1]
        t = models.Trace(
            session_id=self.session_id,
            parent_id=parent_id,
            name=name,
            kind=kind,
            t_start_ms=int(time.time() * 1000),
            duration_ms=0,
            input_json=input or {},
            output_text="",
            meta_json={},
        )
        self.db.add(t)
        await self.db.commit()
        await self.db.refresh(t)
        self._stack.append(t.id)
        return t.id, time.monotonic()

    async def end(
        self,
        trace_id: int,
        mono_start: float,
        output: str | None = None,
        meta: dict | None = None,
        error: str | None = None,
    ) -> None:
        t = await self.db.get(models.Trace, trace_id)
        if t is None:
            return
        t.duration_ms = int((time.monotonic() - mono_start) * 1000)
        if output is not None:
            t.output_text = str(output)[:10000]
        if meta is not None:
            t.meta_json = meta
        if error is not None:
            t.error_text = str(error)[:2000]
        await self.db.commit()
        if self._stack and self._stack[-1] == trace_id:
            self._stack.pop()

    @asynccontextmanager
    async def span(self, name: str, kind: str = "span", input: dict | None = None):
        tid, ts = await self.start(name, kind, input=input)
        try:
            yield tid
        finally:
            await self.end(tid, ts)
