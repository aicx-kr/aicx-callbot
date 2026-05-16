# Playback ack 기반 idle 타이머 baseline 보정

> 작성일: 2026-05-16
> 상태: **TODO** · 우선순위: **High** · 담당: 홍동완
> 관련: [[2026-05-16-barge-in-llm-stream-cancel]] — voice_session.py / ws/voice.py 동시 편집 충돌 가능
>
> **문서 성격**: 설계 산출물. 사용자 검토 후 빌드.

---

## 1. 증상

봇 발화가 끝난 뒤 사용자 체감으로 **3초만에** "여보세요?" idle prompt 가 나옴. `Callbot.idle_prompt_ms = 7000` (default, DB 값 확인 완료) 이므로 7초가 나와야 정상.

## 2. 근본 원인

`_speak` (voice_session.py:2013-2063) 의 `finally` 블록이 `self.state.last_speak_end_t = _time.monotonic()` 로 baseline 을 찍는데, 이 시각은 **서버가 마지막 PCM chunk 를 WebSocket 으로 push 끝낸 시각**이지 **클라이언트가 실제 오디오 재생을 끝낸 시각이 아니다**.

`google_tts.py:86-101` 는 `response.audio_content` 전체를 메모리에 받은 뒤 200ms/500ms chunk 로 `await asyncio.sleep(0)` 만 끼워 즉시 push — 4초짜리 발화도 서버에선 ~수십 ms 안에 다 flush 끝남. 클라이언트의 Web Audio API `BufferSourceNode.start(when)` 큐에 ~4초가 쌓여 재생 중인 상태.

따라서 서버 시계로 봇 발화 종료 후 7s 가 흐른 시점은 클라이언트 체감으론 봇 종료 후 ~3s. → idle prompt 가 너무 빨리 발화.

옵션 C (서버가 PCM 길이 누적해서 보정) 는 검토했으나 거부 — 네트워크 jitter / 클라 디바이스 버퍼 가정에 의존하는 추정치라 근본 해결 아님.

## 3. 해결 방향

WebSocket 프로토콜에 **playback ack 채널** 신설 — 클라가 자신의 audio output queue 가 비는 시점을 서버에 알려준다.

```
[server → client]
{"type":"speak_end", "id":"<uuid>"}   ← 신규. _speak 가 PCM 다 emit 한 직후 송신.

[client → server]
{"type":"playback_done", "id":"<uuid>"}   ← 신규. 클라 큐의 해당 id 지점이 재생 완료된 시점에 송신.
```

서버는 `playback_done` 수신 시점에 `_last_activity_t = monotonic()`. 그 전엔 idle 카운트 시작 안 함 — 실제 클라 재생 시간 기반이 됨.

## 4. 변경 범위

| 파일 | 변경 |
|---|---|
| `backend/src/application/voice_session.py` | `_speak` finally 에 marker 송신 / `_last_activity_t` 갱신 책임을 `playback_done` 핸들러로 이관 / `_SessionState` 에 `pending_speak_id: str \| None` |
| `backend/src/api/ws/voice.py` | 프로토콜 헤더 docstring 업데이트 / `playback_done` 메시지 케이스 추가 |
| `frontend/src/components/TestPanel.tsx` | `playPCM` 의 `playbackTimeRef` 이용해서 `speak_end` 수신 시 자체 setTimeout 으로 `playback_done` 회신 |

## 5. 구현 단계

### (a) 서버 — marker 송신

`voice_session.py` `_speak` 의 `finally` 블록 뒤 (cancel 안 됐을 때만):

```python
if cancelled or self._closed:
    return
speak_id = uuid.uuid4().hex
self.state.pending_speak_id = speak_id
# 이전 fallback timer 정리 + 새 fallback timer 등록
prev_fallback = self.state.playback_fallback_task
if prev_fallback is not None and not prev_fallback.done():
    prev_fallback.cancel()
audio_duration_s = total_pcm_bytes / float(self.sample_rate * 2) if total_pcm_bytes else 0.0
self.state.playback_fallback_task = asyncio.create_task(
    self._playback_fallback_timer(speak_id, audio_duration_s)
)
await self.send_json({"type": "speak_end", "id": speak_id})
```

cancel 된 경우 (barge-in) marker 송신하지 않음. 그 경우는 `_on_speech_end:776` 의 `_last_activity_t = monotonic()` 갱신 경로가 담당.

`_on_speech_start` 의 barge-in cancel 분기에서도 `pending_speak_id`/fallback task 명시적 정리 — 늦게 도착하는 `playback_done` 이 id mismatch 로 silent ignore 되도록.

### (b) 서버 — `_last_activity_t` 책임 이전

`_speak` finally 의 다음 라인 제거:

```python
last = getattr(self, "_last_activity_t", 0.0)
if last < self.state.last_speak_end_t:
    self._last_activity_t = self.state.last_speak_end_t
```

`last_speak_end_t` 자체는 echo grace 용도로 남겨둠 (서버 측 timing). 단, `_last_activity_t` 는 더 이상 여기서 갱신 안 함.

### (c) 서버 — `playback_done` 핸들러

`backend/src/api/ws/voice.py` 의 메시지 디스패치에 추가:

```python
elif mtype == "playback_done":
    pid = msg.get("id")
    if pid and pid == voice.state.pending_speak_id:
        voice.state.pending_speak_id = None
        voice._last_activity_t = _time.monotonic()
```

id mismatch / pending 없음 / 이미 barge-in 된 경우 → silent ignore. 늦게 도착한 ack 가 baseline 을 잘못 흔드는 사고 방지.

### (d) 서버 — fallback 타임아웃

클라가 답을 안 보내는 경우 (구버전 클라, 버그 등) idle prompt 가 영원히 안 나오면 곤란. `_speak` 가 marker 송신 후 별도 `asyncio.create_task(_playback_fallback_timer(speak_id))` 등록:

```python
async def _playback_fallback_timer(self, speak_id: str) -> None:
    # 안전 상한 — 발화 길이 + 5s 가 지나도록 ack 없으면 timeout 으로 간주.
    await asyncio.sleep(audio_duration_s + 5.0)
    if self.state.pending_speak_id == speak_id:
        self.state.pending_speak_id = None
        self._last_activity_t = _time.monotonic()
        logger.warning("playback_done 미수신 — fallback baseline", speak_id=speak_id)
```

`audio_duration_s` 는 `total_pcm_bytes / (sample_rate * 2)` 로 계산. 보수적 +5s 마진.

### (e) 클라 — `speak_end` 처리 & 회신

`frontend/src/components/TestPanel.tsx:350-366` `playPCM` 가 이미 `playbackTimeRef.current = when + buf.duration` 로 큐 끝 시각을 추적 중.

WebSocket `onmessage` 의 JSON 케이스에 추가:

```ts
else if (msg.type === 'speak_end') {
  const ctx = audioCtxRef.current;
  if (!ctx) { ws.send(JSON.stringify({type:'playback_done', id: msg.id})); return; }
  const remainingMs = Math.max(0, (playbackTimeRef.current - ctx.currentTime) * 1000);
  setTimeout(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({type:'playback_done', id: msg.id}));
    }
  }, remainingMs);
}
```

`speak_end` 수신 시점엔 그 turn 의 모든 PCM chunk 가 이미 `onmessage` 로 도착해서 (WebSocket 메시지 순서 보장) `playbackTimeRef` 에 누적된 상태. 따라서 `playbackTimeRef.current - ctx.currentTime` 는 정확히 "현재 시점부터 큐가 빌 때까지" 시간.

### (f) 프로토콜 헤더 업데이트

`ws/voice.py:1-19` docstring 에 신규 메시지 두 줄 추가 (문서화).

## 6. 확정된 결정 사항

- **marker 송신 시점 — option A (LWW) 로 구현 확정**. _speak 가 정상 종료(=PCM 끝까지 emit + cancel 안 됨)할 때마다 marker 송신. 사용자는 option B (turn-end 1번) 를 선호했으나, _speak 호출 지점이 9곳 이상 (streaming sentence / greeting / DTMF say / idle prompt / body residual / tool followup / handover / transfer msg / etc) 분산되어 있어 "이게 turn 의 마지막 _speak 인가" 식별 비용이 큼. LWW 로 가도 idle baseline 정확도는 동일 (마지막 playback_done 만 baseline 갱신). 추가 WS 트래픽은 turn 당 N-1 JSON msg (보통 2-3개). 1인 운영 단계 ([[feedback_review_pre_production]]) 의 trade-off — 운영 후 트래픽이 실측 문제가 되면 option B 로 refactor.
- **`audio_duration_s` 추정 정확도**: WAV 헤더 strip 한 raw PCM 기준 `total_pcm_bytes / (sample_rate * 2)`. fallback 용 상한이라 정확할 필요 없음 (+5s 마진).

## 7. 테스트 계획

1. **idle prompt 정확도**: 봇 발화 4s → 발화 종료 후 7s 시점 정확히 prompt 발화 확인 (이전엔 3s 시점). 1인 수동 통화로 체감 검증.
2. **multi-sentence turn**: 3 sentence 응답 → 마지막 sentence 의 `speak_end` 만 baseline 갱신에 영향. 중간 marker 의 `playback_done` 도 도착하지만 무시되는지 로그 확인.
3. **barge-in 시 marker 안 보냄**: 봇 발화 중 끼어들기 → `speak_end` JSON 송신 안 됨. 클라가 `playback_done` 도 안 보냄. `_last_activity_t` 는 [[2026-05-16-barge-in-llm-stream-cancel]] 의 `_on_speech_start` 경로(voice_session.py:776) 로 갱신됨.
4. **fallback 타임아웃**: 클라 끄기 / `playback_done` 안 보내도록 패치 후 → fallback timer 가 baseline 잡고 idle prompt 정상 작동.
5. **늦게 도착한 ack**: 클라가 의도적으로 1초 지연해서 ack 보냄 → `pending_speak_id` 매치되면 정상 갱신, 매치 안 되면 무시.

## 8. 머지 후 검증

- frontend e2e (`frontend/e2e`) playback 시나리오 통과
- 1인 수동 통화 — 봇 발화 종료 후 7s 시점 prompt 발화 체감 확인
- 봇 발화 4s + 사용자 발화 2s 짜리 짧은 통화 → idle prompt 안 나오는지 확인 (사용자 발화로 baseline 갱신되니까)
