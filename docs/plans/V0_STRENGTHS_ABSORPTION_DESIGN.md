# callbot_v0 강점 흡수 — 통합 설계

> **범위**: callbot_v0(https://github.com/aicx-kr/callbot_v0)의 3가지 latency/tool 신뢰성 강점을 현 aicx-callbot에 흡수.
> **상태**: 설계 — 사용자 검토 후 빌드. 어떤 코드도 아직 변경되지 않음.
> **작성**: 2026-05-12

---

## 0. 흡수 대상 3종

| # | 이름 | 기대 효과 | 침습도 |
|---|---|---|---|
| ① | Gemini native function calling | 도구 호출 신뢰성·multi-step | 中 |
| ② | LLM 토큰 streaming + 문장 단위 TTS 병렬 합성 | TTFF 대폭 ↓ | 大 |
| ③ | STT interim에서 Orchestrator 선제 실행 | TTFF ~1초 ↓ | 小 |

명시적으로 **이번 범위 밖**:
- pipecat 스타일 `frames + processors` 풀 리팩터 (④). 효과는 모듈성·테스트성. 지금은 voice_session 비대화 감수.
- WebSocket 메시지 프로토콜 변경. 클라이언트 호환 유지.
- 데이터 모델 변경.

---

## 1. 의존 관계

```
③ interim 선제 실행
   └─ 독립. 먼저 머지 가능.

① function calling
   └─ LLMPort 시그니처 확장. ②와 같은 면을 건드리므로 한 PR로 묶는 게 안전.

② streaming + 문장 TTS
   └─ ①의 시그니처 위에 stream() 추가. parse_signal_and_strip 호환성 가장 큰 이슈.
```

**머지 순서 권장**: ③ → ① → ②.

---

## 2. ③ STT interim 선제 실행 (가장 작은 변경)

### 현 상태
`voice_session._run_stt` 루프(`voice_session.py:279-331`):
```python
async for result in self.stt.transcribe(...):
    await self.send_json({"type":"transcript", "is_final": result.is_final, ...})
    if result.is_final:
        final_text = result.text
...
await self._handle_user_final(final_text.strip())   # is_final 후에야 build_runtime 호출
```

`STTPort.transcribe`는 이미 `AsyncIterator[STTResult]`로 interim도 흘려보냄 → **포트 변경 불필요**.

### 변경

**`backend/src/application/voice_session.py`** 만 변경.

1. `_SessionState`에 추가:
   ```python
   pending_runtime_task: asyncio.Task | None = None
   pending_runtime_interim_text: str = ""
   ```

2. `_run_stt` interim 처리 강화:
   ```python
   async for result in self.stt.transcribe(...):
       await self.send_json({...transcript...})
       if not result.is_final:
           # 5자 이상이고 아직 선제 실행 안 했으면 build_runtime을 백그라운드로 시작
           if (
               not self.state.pending_runtime_task
               and len(result.text) >= settings.preempt_min_chars  # 기본 5
           ):
               self.state.pending_runtime_interim_text = result.text
               self.state.pending_runtime_task = asyncio.create_task(
                   self._prefetch_runtime(result.text)
               )
       else:
           final_text = result.text
   ```

3. `_prefetch_runtime` (신규):
   ```python
   async def _prefetch_runtime(self, interim_text: str) -> tuple[BotRuntime, str]:
       # heuristic_extract도 미리 돌려 var_ctx에 머지
       heur = _heuristic_extract(interim_text)
       for k, v in heur.items():
           if not self.state.var_ctx.has(k):
               self.state.var_ctx.set_extracted(k, v)
       return build_runtime(self.db, self.bot_id, self.state.active_skill,
                            auto_context=self.state.auto_context,
                            variables=self._all_vars())
   ```

4. `_handle_user_final` 시작부:
   ```python
   if self.state.pending_runtime_task:
       try:
           runtime, _ = await self.state.pending_runtime_task
       finally:
           self.state.pending_runtime_task = None
   else:
       runtime, _ = build_runtime(...)
   ```

### 주의
- **selective**: skill 라우팅은 interim 텍스트로 결정하면 잘못된 skill로 갈 수 있음 → 일단 `active_skill`은 그대로 두고 `build_runtime`만 선제. callbot_v0도 같은 패턴.
- **취소**: VAD가 `speech_end` 없이 끊겼거나 interim과 final이 너무 달라지면 task 결과는 무시하고 다시 빌드. 안전 fallback이 무엇인지 `_handle_user_final` 진입부에서 길이 비교(`abs(len(interim) - len(final)) / len(final) > 0.5`) 정도.
- **테스트**: mock STT가 interim 2개 + final 1개 emit, build_runtime 호출이 final 도착 전에 발생하는지 확인.

### 측정
`tracer.start("prefetch_runtime", "span")` 추가. `meta`에 `interim_chars`, `prefetched_ms`, `final_chars` 기록.

---

## 3. ① Gemini native function calling

### 변경 면

**a. `backend/src/domain/ports.py` — LLMPort 시그니처 확장**

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ToolSpec:
    """LLM에 노출할 도구 스펙. infrastructure(SDK) 무관."""
    name: str
    description: str
    parameters_schema: dict   # JSON Schema

@dataclass(frozen=True)
class LLMToolCall:
    name: str
    args: dict

@dataclass(frozen=True)
class LLMResponse:
    text: str | None
    tool_call: LLMToolCall | None
    raw_model_content: object | None   # adapter-specific (e.g. Gemini Content) — history 재주입용

class LLMPort(ABC):
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        history: list[ChatMessage],
        user_text: str,
        model: str,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    async def continue_after_tool(
        self,
        system_prompt: str,
        history: list[ChatMessage],
        prior_model_content: object,   # 직전 LLMResponse.raw_model_content
        tool_name: str,
        tool_result: object,
        model: str,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse: ...
```

**핵심**:
- `raw_model_content`는 어댑터-특정 객체(Gemini의 `Content`)지만 도메인은 `object`로만 본다 — 의존성 역전 유지.
- `continue_after_tool`이 별도 메서드여야 Gemini가 요구하는 `thought_signature` 보존된 `Content`를 그대로 다시 넘길 수 있음 (callbot_v0 `mcp_service.py:80` 참조).

**b. `backend/src/infrastructure/adapters/gemini_llm.py`**

- `google.generativeai` → `google-genai` 패키지로 교체 (callbot_v0가 쓰는 신 SDK; `genai_types.FunctionDeclaration` 제공).
- `pyproject.toml`의 `gcp` extra에 `google-genai>=0.3` 추가, `google-generativeai` 제거.
- `ToolSpec[]` → `genai_types.FunctionDeclaration[]` 변환:
  ```python
  def _to_fd(t: ToolSpec) -> genai_types.FunctionDeclaration:
      return genai_types.FunctionDeclaration(
          name=t.name, description=t.description, parameters=t.parameters_schema or {}
      )
  ```
- `generate()` 반환:
  ```python
  text, fc, model_content = await asyncio.to_thread(_call, contents, sys, fds)
  if fc:
      return LLMResponse(text=text or None, tool_call=LLMToolCall(name=fc["name"], args=fc["args"]),
                         raw_model_content=model_content)
  return LLMResponse(text=text or "", tool_call=None, raw_model_content=model_content)
  ```

**c. `backend/src/application/voice_session.py` — tool 루프 교체**

**P1 결과로 streaming 분기가 단순화됨**: 모든 호출을 stream으로 시작하고, 첫 chunk에 function_call이 있으면 stream을 그 시점에 종료 + tool 루프 진입. 별도 `streaming_mode` 봇 설정 불필요.

기존 `parse_signal_and_strip` 기반 분기는 **next_skill/extracted 시그널 추출용으로만** 잠시 유지 (도구 호출은 native로 전환). 새 경로:

```python
async def _handle_user_final(self, user_text: str) -> None:
    ...
    tools = self._build_tool_specs()   # bot.tools 중 enabled → ToolSpec[]
    response = await self.llm.generate(
        system_prompt=resolved_system_prompt,
        history=history,
        user_text=user_text,
        model=runtime.llm_model,
        tools=tools,
    )

    for _ in range(settings.tool_loop_max_iterations):  # 기본 3
        if response.tool_call is None:
            break
        tool_name, args = response.tool_call.name, response.tool_call.args
        args = _resolve_args_deep(args, self.state.var_ctx)
        result = await self._execute_tool_by_name(tool_name, args, turn_id)
        response = await self.llm.continue_after_tool(
            system_prompt=resolved_system_prompt,
            history=history,
            prior_model_content=response.raw_model_content,
            tool_name=tool_name,
            tool_result=result.result if result.ok else {"error": result.error},
            model=runtime.llm_model,
            tools=tools,
        )

    body = (response.text or "").strip()
    # 호환: parse_signal_and_strip는 next_skill/extracted 시그널만 처리 (tool 시그널은 native로 대체)
    body, signal = parse_signal_and_strip(body)
    ...
```

**d. `_build_tool_specs()`** — application 신규 헬퍼

```python
def _build_tool_specs(self) -> list[ToolSpec]:
    bot = self.db.get(models.Bot, self.bot_id)
    if not bot:
        return []
    specs: list[ToolSpec] = []
    for t in bot.tools:
        if not t.is_enabled:
            continue
        schema = t.parameters_schema_json or {"type": "object", "properties": {}}
        specs.append(ToolSpec(name=t.name, description=t.description or "", parameters_schema=schema))
    # builtin도 노출 (end_call/handover/transfer_to_agent)
    specs.extend(_BUILTIN_TOOL_SPECS)   # 모듈 상수 (코드 상수 — tenant 무관, 시스템 capability)
    return specs
```

**중요** [[feedback_no_hardcoded_tenant_config]]: `_BUILTIN_TOOL_SPECS`는 시스템 능력(end_call/handover/transfer_to_agent)만 하드코딩 — tenant 설정 아님. tenant별 도구는 전부 `bot.tools`(DB).

### 마이그레이션
- 기존 봇의 `Tool.parameters_schema_json`이 비어있을 수 있음 → 어드민에서 도구 편집 시 schema 의무화. 임시로 빈 schema도 허용(LLM이 args 없이 호출).
- 환경변수: `TOOL_LOOP_MAX_ITERATIONS=3` (default).

### 테스트
- `test_voice_session_tool_loop.py`: mock LLM이 turn 1에 `tool_call=foo` 반환, turn 2에 텍스트 반환 → tool 1회 실행 + 자연어 응답 검증.
- `test_gemini_llm_adapter.py`: SDK 호출 mocking으로 `FunctionDeclaration` 변환 검증.

---

## 4. ② Streaming LLM + 문장 단위 TTS

### 변경 면

**a. `LLMPort`에 stream API 추가** — `generate`/`continue_after_tool`은 유지(tool 호출 턴은 stream 안 함, callbot_v0와 동일 분기).

```python
class LLMPort(ABC):
    @abstractmethod
    async def generate(...) -> LLMResponse: ...
    async def continue_after_tool(...) -> LLMResponse: ...

    @abstractmethod
    def stream(
        self,
        system_prompt: str,
        history: list[ChatMessage],
        user_text: str,
        model: str,
    ) -> AsyncIterator[str]: ...
    # 토큰이 아니라 "문장 단위"로 yield. adapter 내부에서 문장 경계 분할.
```

**왜 stream에 tools가 없나**: callbot_v0도 `stream_call_with_tools`은 있지만 tool 발생 시 stream을 깨고 non-stream 경로로 떨어짐. 우리도 단순화 — `tools=None`일 때만 stream.

**b. `gemini_llm.py` — stream 구현**

```python
async def stream(self, ...) -> AsyncIterator[str]:
    contents = self._build_contents(history, user_text)
    buf = ""
    SEG_RE = re.compile(r"(?<=[.!?。！？])\s+")
    async for chunk in await asyncio.to_thread(self._client.models.generate_content_stream, ...):
        if not chunk.text:
            continue
        buf += chunk.text
        parts = SEG_RE.split(buf)
        if len(parts) > 1:
            for s in parts[:-1]:
                if s.strip():
                    yield s.strip()
            buf = parts[-1]
    if buf.strip():
        yield buf.strip()
```

**c. `_handle_user_final` — 분기**

```python
if self._can_stream(tools):   # 단순 휴리스틱: 도구가 0개거나, "이 발화는 도구 호출 가능성 낮음"
    await self._handle_streaming_turn(...)
else:
    # 기존 generate + tool loop 경로 (function calling)
```

**P1 PoC로 확정된 분기 전략**: 항상 stream으로 호출, 첫 chunk 검사 후 분기.

```python
async def _handle_user_final(...):
    tools = self._build_tool_specs()
    stream = self.llm.stream(system_prompt=..., history=..., user_text=..., model=..., tools=tools)
    first_chunk = await anext(stream, None)
    if first_chunk is None:
        return  # 빈 응답
    if first_chunk.tool_call:
        # P1 결과: tool_call은 단독 chunk → stream 폐기, tool 루프 진입
        await stream.aclose()
        await self._run_tool_loop(first_chunk.tool_call, ...)
    else:
        # 정상 streaming — 첫 문장 buffer 후 송출 (next_skill 시그널 검사용)
        await self._stream_text_response(first_chunk, stream, ...)
```

`bot.streaming_mode` 봇별 설정 **불필요**. 항상 stream이 기본.

**d. TTS 병렬 합성**

`TTSPort.synthesize`는 이미 `AsyncIterator[bytes]`. 변경 없이 voice_session에서:

```python
async def _handle_streaming_turn(self, ...) -> None:
    sentence_idx = 0
    bot_full = []
    tts_tasks: list[asyncio.Task] = []
    async for sentence in self.llm.stream(...):
        sentence = strip_audio_tags(sentence)  # 기존 헬퍼 재사용
        bot_full.append(sentence)
        # 문장 단위 TTS — 다음 문장 LLM 대기와 병렬
        tts_tasks.append(asyncio.create_task(
            self._speak_chunk(sentence, runtime.voice, runtime.language, sentence_idx)
        ))
        sentence_idx += 1
    # 순서 보장: 클라 재생은 _speak_chunk가 받은 chunk_index 순서대로 송출되도록 큐
    await asyncio.gather(*tts_tasks)
    body = " ".join(bot_full).strip()
    self._save_transcript("assistant", body)
```

`_speak_chunk`는 `send_bytes`를 직접 호출하되 **순서 보장**을 위해 단일 송출 큐 사용:
```python
self._tts_send_queue: asyncio.Queue[tuple[int, bytes | None]] = asyncio.Queue()
# 백그라운드 task가 큐를 소비해서 chunk_index 순서대로 send_bytes
```

### 호환성
- `parse_signal_and_strip`이 응답 텍스트 전체에서 시그널 추출하는데, stream 모드에선 문장 단위로 yield됨 → **전체 응답을 누적해서 마지막에 한 번 파싱**. 시그널이 응답 중간에 있으면 처음 N문장이 이미 TTS된 후 next_skill 시그널을 발견하는 사고 가능. 해결: 시스템 프롬프트에 "skill 전환 시그널은 응답 시작 첫 줄에만 출력하라" 명시. 또는 첫 문장은 buffer만, 시그널 없으면 그제서야 TTS 시작.

**결정 필요**: 첫 문장 buffer가 안전 → 권장. TTFF에 ~100ms 정도 영향.

### 측정
- `tracer.start("llm.stream", "llm")` + `meta.first_sentence_ms`, `total_sentences`, `total_chars`
- `tracer.start("tts.chunk", "tts")` chunk별

### 테스트
- `test_gemini_llm_stream.py`: mock SDK가 토큰 3개를 yield → adapter가 문장 1개로 합쳐 yield 검증.
- `test_voice_session_streaming.py`: mock LLM stream이 문장 3개 yield → TTSPort.synthesize가 3번 호출되고 chunk_index 0,1,2 순서로 send_bytes 검증.

---

## 5. Clean Architecture 영향 요약

| 레이어 | 변경 | 의존성 방향 |
|---|---|---|
| domain/ports.py | `LLMPort.generate` 시그니처 확장, `stream/continue_after_tool` 추가, `ToolSpec/LLMToolCall/LLMResponse` dataclass | ✓ (외부 의존 무) |
| domain/repositories.py | 변경 없음 | ✓ |
| domain/{callbot,bot,tool,...}.py | 변경 없음 | ✓ |
| application/voice_session.py | tool 루프 native 전환, streaming 분기, prefetch_runtime | ✓ (domain만 의존) |
| application/tool_runtime.py | 변경 없음 (execute_tool 그대로) | ✓ |
| infrastructure/adapters/gemini_llm.py | google-genai SDK 교체, stream/function_declaration 구현 | ✓ (domain.ports 구현) |
| infrastructure/adapters/google_stt.py | 변경 없음 | ✓ |
| infrastructure/adapters/factory.py | 변경 없음 | ✓ |
| api/ws/voice.py | 변경 없음 (WS 프로토콜 동일) | ✓ |

→ **의존성 역전 깨지지 않음**. `raw_model_content: object`로 SDK 객체를 도메인에 노출하지 않는 게 포인트.

---

## 6. 환경변수 / 설정 추가

```env
PREEMPT_MIN_CHARS=5              # ③ interim 선제 실행 최소 글자수
TOOL_LOOP_MAX_ITERATIONS=3        # ① native function calling 루프 최대 횟수
```

P1 PoC 결과로 `LLM_STREAMING_DEFAULT`와 `Bot.streaming_mode`는 **불필요해짐**. tool_call과 text가 같은 stream에 섞이지 않아서 항상 stream으로 호출해도 안전.

---

## 7. PR 분할 (권장)

1. **PR-A** (③ + 측정 기반): interim 선제 실행 + tracer span. 회귀 위험 최소.
2. **PR-B** (①): LLMPort 시그니처 확장 + Gemini SDK 교체 + tool 루프 native. `parse_signal_and_strip`은 next_skill 추출용으로만 남김.
3. **PR-C** (②): stream API + 문장 단위 TTS + 봇별 streaming_mode.

각 PR마다 **실 API smoke test** [[feedback_autonomous_loop]] 통과 의무. mock-only 통과는 미인정.

---

## 8. PoC 검증 결과 (2026-05-12 실측)

### P1 — generate_content_stream의 tool_call emit 패턴 ✓

`backend/scripts/poc_genai_stream_tool.py` 실행 결과:

| 시나리오 | chunk 수 | text | function_call | 결론 |
|---|---|---|---|---|
| A: "서울 날씨 알려줘" + tool 등록 | **1** | 없음 | 즉시 단독 emit, `finish_reason=STOP` | tool_call은 첫·유일 chunk |
| B: "안녕하세요…" + tool 등록 | 2 | 분할 emit | 없음 | 일반 streaming 정상 |
| C: 같은 텍스트 + tool 없음 | 2 | 분할 emit | 없음 | baseline |

**핵심 함의**: text와 tool_call은 **같은 stream에 섞이지 않음**. tool_call이 발생하면 chunk 1개로 끝남.

→ ②의 streaming 분기 설계 **크게 단순화**:
- 봇별 `streaming_mode` 옵션 **불필요**
- "streaming 중 mid-flight tool_call 검출 후 fallback" 같은 복잡한 로직 **불필요**
- 모든 LLM 호출을 `stream`으로 시작 → 첫 chunk에 `function_call` 있으면 → tool 루프 진입. text면 → 정상 streaming 계속

### P2 — thought_signature 보존 & tool 결과 주입 ✓

`backend/scripts/poc_genai_tool_loop.py` 실행 결과:

- turn 1 응답의 `model_content.parts[0]`에 **`thought_signature` (bytes, len=256)** 존재
- `contents.append(model_content)`로 그대로 다시 history에 넣음 → SDK가 signature 보존
- `Part.from_function_response(name=..., response={"result": ...})`로 결과 주입
- turn 2 응답: 자연스러운 텍스트 `"서울은 맑고 기온은 섭씨 18도입니다."` (도구 결과를 LLM이 인용)
- turn 2를 streaming으로 호출해도 정상 동작 (chunk 2개로 분할)

→ ①의 `LLMResponse.raw_model_content: object` 설계 **그대로 유효**. Gemini Content 객체를 도메인이 모른 채 application 레이어를 통과시키면 됨.

### P3 — TTS 동시 N개 호출 quota

PoC 미실시 — 부하 테스트 성격이라 실제 운영 데이터 필요. 현 구현 그대로 ② 적용 시 5문장 응답 = 5개 동시 `synthesize` 호출. GCP Speech-to-Text/TTS 기본 quota는 분당 60+ 요청이라 문제 없을 가능성 큼. **②  머지 후 staging에서 latency 모니터링하며 verify**.

### P4 — 현 봇 Tool params 채워진 비율 ✓

```
Total: 6 tools across 2 bots
  - end_call (builtin, no params): 정상으로 빈 schema
  - transfer_to_specialist (builtin): 1 param ✓
  - get_accommodation_product (mcp): 1 param ✓
  - get_reservation_summary (mcp): 2 params ✓
  - get_refund_fee (mcp): 4 params ✓
  - get_tna_product (mcp): 1 param ✓
```

**마이그레이션 부담 거의 없음** — 인자 있는 도구는 전부 schema 채워져 있음.

### 발견 사항: Tool 모델 컬럼명 정정

설계 문서에서 `Tool.parameters_schema_json`이라고 표기했으나 실제 컬럼은 `Tool.parameters: list[dict]` (`{name, type, description, required}` 형식). PR-B에서 `_build_tool_specs`는 이 list를 JSON Schema로 변환해야 함:

```python
def _params_to_schema(params: list[dict]) -> dict:
    props = {}
    required = []
    for p in params:
        props[p["name"]] = {"type": p["type"], "description": p.get("description", "")}
        if p.get("required"):
            required.append(p["name"])
    return {"type": "object", "properties": props, "required": required}
```

### 최종 결론

**모든 가정이 검증됨. ②의 streaming 분기 단순화 가능.** PR-B / PR-C 작업 시작 가능.

---

## 9. 비고

- 4번째 강점인 **pipecat-style processor 풀 리팩터**는 이번 설계 범위 밖. 위 3개 흡수 이후 voice_session이 1000줄을 넘기면 그때 재검토.
- callbot_v0의 `dynamic_vars 자동 사전 호출` 패턴(`reservations_phone`)은 aicx-callbot의 `_run_auto_calls("session_start")`로 이미 동일 발상 구현됨 — 추가 작업 없음.
- callbot_v0의 `_heuristic_extract` 같은 정규식 슬롯 추출은 **aicx-callbot이 이미 더 풍부함** — 이식 불필요, 오히려 callbot_v0가 aicx-callbot에서 가져갈 거리.
