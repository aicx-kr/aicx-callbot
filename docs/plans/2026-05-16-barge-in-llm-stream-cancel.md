# barge-in 시 LLM 스트림까지 완전 취소

> 작성일: 2026-05-16
> 상태: **TODO** · 우선순위: **High** · 담당: 홍동완
> 관련: 본 문서는 별도 PR. [[2026-05-16-playback-ack-idle-baseline]] 와 voice_session.py 동시 편집 충돌 가능 — 머지 순서 주의.
>
> **문서 성격**: 설계 산출물. 사용자 검토 후 빌드.

---

## 1. 증상

고객이 봇 발화 도중 말을 시작하면 STT 는 인식되지만 봇이 멈추지 않고 LLM 이 만들어둔 다음 문장이 연달아 발화됨.

## 2. 근본 원인

원인은 두 갈래.

**(i) LLM 스트림 루프 미취소.**
`_on_speech_start` (voice_session.py:717-772) 가 cancel 하는 것은 **현재 재생 중인 `speech_task` 1개뿐**. LLM 응답은 sentence 단위 스트리밍 — `_run_streaming_turn` (voice_session.py:1194-1235) 안의 `async for chunk in stream_iter` 루프가 살아있어서, 한 문장의 TTS 가 cancel 되면 **루프 다음 iteration 이 새 sentence 를 `_send_and_speak_sentence` → `_speak` 로 보내며 새 `speech_task` 를 만든다**. cancel-emit race 도 존재 — cancel 한 직후 다음 sentence emit 까지 한 cycle 새는 경우 있음.

**(ii) 부분 발화 sentence 가 컨텍스트에 그대로 저장됨.**
voice_session.py:1234 `sentences.append(chunk.text)` 는 `_speak` 의 결과와 무관하게 chunk 도착 즉시 리스트에 추가. 1085-1089 의 turn 종료 시 `full_body = " ".join(sentences)` → `_save_transcript("assistant", full_body)` 는 **TTS 가 절반 컷된 sentence 까지 컨텍스트에 넣음**. 고객이 듣지 못한 부분이 LLM 다음 턴의 history 로 들어가 "이미 말했음" 으로 오인됨.

## 3. 변경 범위

| 파일 | 변경 |
|---|---|
| `backend/src/application/voice_session.py` | `_speak` 가 outer task cancel 을 propagate 하도록 수정 + `_send_and_speak_sentence` / `_speak` 가 commit 여부 bool 반환 / `_run_streaming_turn` 루프에 state 가드 + commit-aware 누적 / `_handle_user_final` 의 try/except CancelledError + shield save / `_SessionState.streaming_sentences` 인스턴스 누적 / `_run_tool_loop_after_stream` 의 save 순서 commit 후로 이동 |

이 외 파일 수정 없음. 프로토콜 / 클라 / DB 변경 없음.

## 4. 구현 단계

### (a) cancel 전파 — `_speak` 패턴 수정

기존 `_speak` 의 `except asyncio.CancelledError: pass` 는 외부 task (`_stt_task`) cancellation 까지 삼켜서 LLM 스트림 루프가 다음 sentence 를 계속 emit 하는 게 진짜 원인. 수정:

```python
completed = True
try:
    await self.state.speech_task
except asyncio.CancelledError:
    completed = False
    # 외부 task 가 cancel 중이면 신호 propagate — 호출자가 partial save 후 raise.
    current = asyncio.current_task()
    if getattr(current, "cancelling", lambda: 0)() > 0:
        raise
finally:
    ...
return completed
```

`asyncio.current_task().cancelling()` 은 Python 3.11+. 환경 확인 후 적용 (현 프로젝트 3.11).

별도 `llm_task` 필드는 도입하지 않음 — 기존 `_on_speech_start:759` 의 `self._stt_task.cancel()` 이 이미 `_handle_user_final` 의 task 를 cancel 하므로 중복.

### (b) 루프 내 race 가드

`_run_streaming_turn` (voice_session.py:1194-1235) 의 `async for chunk in stream_iter:` 첫 줄에:

```python
if self.state.state == "listening":
    break
```

cancel 신호가 도착하기 전 한 iter 새는 경우 방지. `state == "listening"` 는 barge-in 으로 `_on_speech_start` 가 set 한 상태.

### (c) commit-aware `_send_and_speak_sentence`

`_send_and_speak_sentence` (voice_session.py:1277-1316) 가 PCM 송출 완료 여부를 반환하도록 변경:

```python
async def _send_and_speak_sentence(self, sentence, ...) -> bool:
    await self.send_json({"type": "transcript", "role": "assistant", "text": sentence})
    ...
    try:
        await self._speak(sentence, runtime.voice, runtime.language)
    except asyncio.CancelledError:
        return False   # PCM 송출 중간 컷 — 고객이 끝까지 못 들음
    ...
    return True        # 끝까지 송출 — 거의 다 들렸다고 간주
```

`_run_streaming_turn` 루프에서 commit 된 경우만 `sentences` 에 누적:

```python
async for chunk in stream_iter:
    if self.state.state == "listening":
        break
    ...
    if chunk.text and not self._looks_like_signal_chunk(chunk.text):
        committed = await self._send_and_speak_sentence(chunk.text, ...)
        if not committed:
            break
        sentences.append(chunk.text)
```

기존 `sentences.append(chunk.text)` (voice_session.py:1234) 줄은 위 위치로 이동 — `_send_and_speak_sentence` 호출 **이후** 로.

### (d) turn 종료 후 partial transcript 저장 보장

`_stt_task.cancel()` 로 외부 cancel 이 `_speak` 를 거쳐 propagate 하면 호출자(`_handle_user_final`, voice_session.py:1085-1089) 의 `_save_transcript` 도 못 도착. **commit 된 sentence 들 까지 통째로 버려진다.**

→ `_SessionState.streaming_sentences: list[str]` 인스턴스 속성으로 누적 (같은 list 참조를 `_run_streaming_turn` 의 local `sentences` 도 공유). `_handle_user_final` 의 `_run_streaming_turn` 호출을 `try/except CancelledError` 로 감싸고, cancel 발생 시:

```python
except asyncio.CancelledError:
    committed = list(self.state.streaming_sentences)
    if committed:
        full_body = " ".join(committed).strip()
        if full_body:
            await asyncio.shield(self._save_transcript("assistant", full_body))
    raise
```

`asyncio.shield` — save 가 cancel 영향 받지 않게. 그 뒤 raise 로 cancel 정상 전파 (`_run_stt` task 가 정상 종료).

### (e) 빈 transcript row 방지

기존 normal-path save (voice_session.py:1085-1089) 는 `full_body=""` 인 경우에도 row 를 저장. commit-aware 로 sentences 가 비는 케이스 (예: LLM 첫 chunk 도착 전 barge-in) 가 자연스럽게 발생하므로 `if full_body: save` 가드 추가.

### (f) `_run_tool_loop_after_stream` 의 비-stream TTS

voice_session.py:1366-1376 의 tool followup 경로는 `_save_transcript("assistant", body)` 를 `_speak` 호출 **이전** 에 함. 본 PR 의 commit 원칙과 어긋남. `committed = await _speak(...)` 후 `if committed: save` 로 변경. transcript JSON (UI 표시) 은 변함 없이 _speak 전에 보냄.

## 5. 확정된 결정 사항

- **partial transcript 처리**: `_speak` 가 끝까지 PCM 을 송출한 sentence (서버 입장 정상 종료) 만 컨텍스트에 commit. `_speak` cancel 된 sentence (PCM 중간 컷) 는 컨텍스트 폐기. 사용자가 듣지 못한 내용을 LLM history 에 넣지 않기 위해서.
- **prefetch_runtime task**: `_on_speech_start:763` 에서 이미 cancel 함. 추가 작업 없음.

## 6. 알려진 한계 (edge case)

서버 `_speak` 가 PCM 을 끝까지 emit 한 sentence 라도, 클라이언트가 그걸 재생 시작 직후 사용자가 즉시 끼어든 경우, 고객은 sentence 앞부분만 듣게 됨. 본 구현은 그 sentence 를 commit 하므로 LLM 컨텍스트엔 전체 sentence 가 들어감.

이 edge case 를 100% 정확히 풀려면 sentence 단위 playback ack 가 필요하며, [[2026-05-16-playback-ack-idle-baseline]] 의 옵션 B (turn-end marker 1개) 를 옵션 A (매 sentence 마다 marker) 로 회귀시켜야 함. 양쪽 코드 복잡도가 늘어남.

1인 운영 단계 ([[feedback_review_pre_production]]) 의 trade-off 로 본 PR 은 99% 정확한 서버 cancel 기준만 적용. 실 운영에서 위 edge case 가 누적되면 sentence-별 ack 로 업그레이드.

## 7. 테스트 계획

1. **단위 시나리오 — barge-in 즉시 cut**: 봇 발화 1초 시점에 mic 입력 → 200ms 안에 PCM 송출 중단 + `barge_in` JSON 송신 확인. **다음 sentence 가 절대 송출되지 않음** 검증.
2. **thinking 중 barge-in**: LLM stream 시작 후 첫 sentence TTS 들어가기 전 (서버 상태 `thinking`) 사용자가 말함 → llm_task cancel 되고 어떤 TTS 도 안 나감.
3. **partial sentence 컨텍스트 폐기**: 봇이 sentence A 완료 + sentence B 50% 시점 끼어들기 → transcript DB 에 A 만 저장, B 는 없음. LLM 다음 턴 history 에 B 미포함 확인.
4. **commit 된 sentence 유지**: 봇 sentence A 송출 완료 후 침묵 → A 는 transcript 에 정상 저장 (기존 동작 유지).
5. **echo grace 보존**: 봇 발화 종료 직후 0.5s 내 잡음으로는 위 cancel 트리거 안 되는지 (기존 동작 유지).
6. **greeting barge-in 비활성**: `greeting_barge_in=False` 설정에서 greeting 중 사용자 발화 → 무시 (기존 동작 유지).

기존 e2e 스크립트 `backend/tests/e2e_voice_sim.py` 의 `barge_in` 시나리오 확장 — `assert sentences_after_cancel == 0` + `assert "B 내용" not in transcript` 추가.

## 8. 머지 후 검증

- `pytest backend/tests` 통과
- 1인 수동 통화 1건 — 봇 응답 중간 (sentence B 진행 중) 끼어들기 → 즉시 멈춤 체감 + DB transcript 확인하여 B 미저장
- LangSmith 미사용 ([[project_callbot_no_langsmith]]) — trace 는 자체 `_tracer` 만 확인
