"""Voice Session Orchestrator.

상태 머신: idle → listening → thinking → speaking → idle
- listening: VAD가 speech_start 감지, STT 스트리밍 진행
- thinking: STT final → LLM 호출 중
- speaking: TTS 합성 + 오디오 송출
- idle: 다음 발화 대기. 사용자가 발화 시작하면 speaking 중단(barge-in)
"""

from __future__ import annotations

import asyncio
import contextvars
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..core.config import settings
from ..core.logging import get_logger, hash_text, reset_bot_id, set_bot_id
from ..domain import callbot as callbot_module
from ..domain.call_session import normalize_end_reason
from ..domain.global_rule import GlobalAction, dispatch as dispatch_global_rules
from ..domain.ports import ChatMessage, LLMPort, LLMResponse, STTPort, ToolSpec, TTSPort, VADPort
from ..domain.variable import VariableContext
from ..infrastructure import models
from ..infrastructure.db import SessionLocal
from ..infrastructure.repositories.callbot_agent_repository import SqlAlchemyCallbotAgentRepository
from .post_call import analyze_session
from .skill_runtime import build_runtime, find_bot, parse_signal_and_strip
from .tool_runtime import execute_tool
from .tracer import TraceRecorder


# Builtin 도구 스펙 — 시스템 capability (tenant-specific 아님). DB의 Tool과 별개로 항상 LLM에 노출.
# 코드 상수가 안전한 케이스: 의도가 명확한 시스템 동작이고, tenant가 커스터마이즈할 영역 아님.
_BUILTIN_TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="end_call",
        description="통화를 종료한다. 사용자가 작별 인사하거나 더 도움이 필요 없다고 명시할 때 호출.",
        parameters_schema={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="transfer_to_specialist",
        description="복잡한 사례·민감 정보·환불 거부 등 봇이 처리할 수 없을 때 사람 상담사로 전환.",
        parameters_schema={
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "전환 사유"}},
            "required": ["reason"],
        },
    ),
    ToolSpec(
        name="handover_to_human",
        description="transfer_to_specialist의 동의어 — 사용자가 상담사 연결을 직접 요청한 경우.",
        parameters_schema={
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "전환 사유"}},
            "required": ["reason"],
        },
    ),
    ToolSpec(
        name="transfer_to_agent",
        description="다른 에이전트(봇)로 통화 컨텍스트를 인계. branch trigger 조건 충족 시 호출.",
        parameters_schema={
            "type": "object",
            "properties": {
                "target_bot_id": {"type": "integer", "description": "대상 봇 ID"},
                "reason": {"type": "string", "description": "인계 사유"},
            },
            "required": ["target_bot_id"],
        },
    ),
]
_BUILTIN_TOOL_NAMES = {s.name for s in _BUILTIN_TOOL_SPECS}


def _params_to_json_schema(params: list[dict] | None) -> dict:
    """Tool.parameters([{name, type, description, required}, ...])를 JSON Schema로 변환.

    callbot_v0 흡수 #1 — Gemini FunctionDeclaration용. Tool 모델의 list 형식과 SDK가 요구하는
    JSON Schema 형식이 다르기 때문에 변환이 필요하다.
    """
    if not params:
        return {"type": "object", "properties": {}}
    props: dict = {}
    required: list[str] = []
    for p in params:
        name = p.get("name")
        if not name:
            continue
        prop: dict = {"type": p.get("type") or "string"}
        desc = p.get("description")
        if desc:
            prop["description"] = desc
        props[name] = prop
        if p.get("required"):
            required.append(name)
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema

logger = get_logger(__name__)

SendBytes = Callable[[bytes], Awaitable[None]]
SendJSON = Callable[[dict], Awaitable[None]]

# 봇 발화 종료 직후 echo 잔향 차단 시간 (초) — idle 상태에서만 적용.
# speaking 중 barge-in은 영향 X. 너무 길면 사용자 즉시 응답 차단 → 0.5s가 균형점.
_ECHO_GRACE_S = 0.5


def _heuristic_extract(text: str) -> dict:
    """발화에서 흔한 슬롯을 정규식으로 추출 (LLM이 놓쳐도 보장하는 보조).

    - phone: 010-/02- 등 한국 전화번호
    - reservationNo: ACM-..., ABC-..., 또는 7자리 이상 연속 숫자 (공백 포함 "2 3 4 5" 도)
    - userId: "회원번호 N", "userId N", "유저 아이디 N" 패턴
    """
    import re as _re
    out: dict = {}

    # phone
    m = _re.search(r"(\b0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}\b)", text)
    if m:
        out["phone"] = _re.sub(r"[-\s]", "", m.group(1))

    # userId 먼저 — "회원번호 N", "유저 아이디 N", "userId N"
    m = _re.search(r"(?:회원\s*번호|유저\s*아이디|user\s*id)\s*[은는]?\s*(\d{4,15})", text, _re.IGNORECASE)
    if m:
        out["userId"] = m.group(1)

    # reservationNo — ACM-..., ABC-... 영문 prefix
    m = _re.search(r"\b([A-Z]{2,4}-[A-Z0-9-]{4,30})\b", text)
    if m:
        out["reservationNo"] = m.group(1)
    else:
        # 한국식 "예약번호 ..." 또는 단독 7자리+ 숫자 (공백 포함)
        m = _re.search(r"예약\s*번호\s*[은는]?\s*([0-9\s]{7,})", text)
        if m:
            digits = _re.sub(r"\s", "", m.group(1))
            if digits.isdigit() and 7 <= len(digits) <= 20:
                out["reservationNo"] = digits
        else:
            # 단독 7자리 이상 숫자 시퀀스 (이미 userId/phone로 잡힌 건 제외)
            stripped = _re.sub(r"\s", "", text)
            taken = set()
            if "userId" in out: taken.add(out["userId"])
            if "phone" in out: taken.add(out["phone"])
            m2 = _re.search(r"(?<!\d)(\d{7,15})(?!\d)", stripped)
            if m2 and m2.group(1) not in taken:
                out["reservationNo"] = m2.group(1)

    return out


def _resolve_args_deep(args: dict, vc: VariableContext) -> dict:
    """args dict의 모든 string 값에 vc.resolve() 적용 (nested dict/list 재귀)."""
    def walk(v):
        if isinstance(v, str):
            return vc.resolve(v)
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v
    return walk(args) if isinstance(args, dict) else args


@dataclass
class _SessionState:
    state: str = "idle"
    active_skill: str | None = None
    transcripts: list[tuple[str, str]] = field(default_factory=list)
    speech_task: asyncio.Task | None = None
    auto_context: dict = field(default_factory=dict)  # 자동 호출 결과 누적
    var_ctx: VariableContext = field(default_factory=VariableContext)  # vox 3종 변수 통합
    # callbot_v0 흡수 #3 — interim 도달 시 build_runtime을 백그라운드로 선제 실행.
    # _run_stt에서 spawn, _handle_user_final에서 await로 소비. 매 발화마다 None으로 초기화.
    pending_runtime_task: asyncio.Task | None = None
    pending_runtime_interim_text: str = ""
    # TTFF (Time To First Frame) 측정: 사용자 발화 final → 봇 첫 PCM 송신 ms.
    # _handle_user_final 시작 시 turn_t0 기록, _speak이 첫 byte 보낼 때 first_audio_t 기록.
    turn_t0: float | None = None
    first_audio_t: float | None = None
    # Echo grace — 봇 발화 종료 직후 짧은 시간(_ECHO_GRACE_S) 동안 새로 들어온 speech_start는
    # 봇 자기 발화 잔향(echo)으로 간주하고 무시. barge-in (speaking 중 끼어들기)은 그대로 작동.
    last_speak_end_t: float = 0.0
    # 봇 발화 시작 시각 — barge-in 시 elapsed_since_speak_start_ms 계산용.
    last_speak_start_t: float = 0.0
    # (a) AICC-910 — 인사말 발화 중 표식. greeting_barge_in=False 면 _on_speech_start 가 cancel 스킵.
    in_greeting: bool = False
    # (b) AICC-910 — 무응답 자동 종료 타이머 task. idle 진입 시 시작, listening/thinking/speaking
    #     진입 시 즉시 cancel. close() 직전 cancel.
    idle_task: asyncio.Task | None = None
    # interim STT 첫 도달 시각 — (a) barge-in 가속 판정 (f1) 단위 테스트용.
    first_interim_t: float | None = None
    # _run_streaming_turn 이 commit 한 sentence 누적 (turn 도중 barge-in cancel 시 _handle_user_final
    # 이 인스턴스 상태에서 partial 을 회수해 transcript 에 저장하기 위함). turn 시작 시 [] 로 초기화.
    streaming_sentences: list[str] = field(default_factory=list)


class VoiceSession:
    """통화 단위 비동기 오케스트레이터.

    AsyncSession 격리 정책: VoiceSession 은 self.db 를 보관하지 않는다.
    STT/LLM/TTS/tracer 등 각 비동기 task 가 동시 실행되는 환경에서 단일
    AsyncSession 을 공유하면 sqlalchemy.exc.IllegalStateChangeError 가
    발생한다. DB 접근이 필요한 모든 메서드는 `async with SessionLocal() as db:`
    로 자체 세션을 열고 즉시 close 한다.
    """

    def __init__(
        self,
        session_id: int,
        bot_id: int,
        stt: STTPort,
        tts: TTSPort,
        llm: LLMPort,
        vad: VADPort,
        send_bytes: SendBytes,
        send_json: SendJSON,
        sample_rate: int = 16000,
    ):
        self.session_id = session_id
        self.bot_id = bot_id
        self.stt = stt
        self.tts = tts
        self.llm = llm
        self.vad = vad
        self.send_bytes = send_bytes
        self.send_json = send_json
        self.sample_rate = sample_rate
        self.state = _SessionState()
        self._audio_q: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._stt_task: asyncio.Task | None = None
        self._closed = False
        self._tracer = TraceRecorder(session_id)
        # (a)(b)(d)(e) AICC-910 — 현재 봇이 속한 CallbotAgent (음성 동작 설정).
        # start() 에서 1회 채워두고, 통화 동안 캐시. None 이면 callbot 미연결 봇.
        self._callbot_settings: "callbot_module.CallbotAgent | None" = None
        # 침묵 누적 측정용 — 마지막 사용자 발화 종료/봇 발화 종료 중 최신 시각.
        self._last_activity_t: float = 0.0
        # idle prompt 가 이미 발화되었는지 — 매 idle 세션에서 1회만.
        self._idle_prompt_emitted: bool = False
        # AICC-908/909 — transfer 로 bot_id 가 바뀌면 ContextVar(_bot_id_ctx) 도 동기.
        # ws_call_context 가 진입 시 main bot_id 로 1회 set 했으므로, 인계 시 self 가 그 위에
        # 새 토큰을 쌓는다. close 시 LIFO 로 reset.
        self._bot_id_token: contextvars.Token | None = None

    async def _check_global_rules(self, user_text: str) -> bool:
        """공통 규칙 매칭 검사. 매치되면 액션 실행 후 True 반환.
        매치 안 되면 False (LLM 호출 계속).
        """
        stmt = (
            select(models.CallbotMembership)
            .where(models.CallbotMembership.bot_id == self.bot_id)
            .options(selectinload(models.CallbotMembership.callbot))
        )
        async with SessionLocal() as db:
            membership = (await db.execute(stmt)).scalar_one_or_none()
            rules = (
                membership.callbot.global_rules
                if membership and membership.callbot and membership.callbot.global_rules
                else None
            )
        if not rules:
            return False

        rule_id, rule_start = await self._tracer.start(
            "global_rule_check", "span",
            input={"text": user_text, "rules_count": len(rules)},
        )
        matched = dispatch_global_rules(rules, user_text)
        await self._tracer.end(
            rule_id, rule_start,
            meta={"matched": matched.pattern if matched else None,
                  "action": matched.action.value if matched else None},
        )
        if matched is None:
            return False

        # 매치 — 액션 실행
        if matched.action is GlobalAction.HANDOVER:
            await self._record_tool_invocation("global_rule_handover", {"pattern": matched.pattern, "reason": matched.reason}, result={"signal": "handover"})
            await self.send_json({"type": "handover", "args": {"reason": matched.reason or matched.pattern}, "via": "global_rule"})
            if not self._closed:
                await self.set_state("idle")
            return True
        if matched.action is GlobalAction.END_CALL:
            await self._record_tool_invocation("global_rule_end_call", {"pattern": matched.pattern}, result={"signal": "end_call"})
            await self.close(reason=f"global_rule:{matched.pattern}")
            return True
        if matched.action is GlobalAction.TRANSFER_AGENT and matched.target_bot_id:
            await self._handle_tool_signal(
                "transfer_to_agent",
                {"target_bot_id": matched.target_bot_id, "reason": matched.reason or matched.pattern},
                runtime=None, turn_id=None,
                via="global_rule",
            )
            if not self._closed:
                await self.set_state("idle")
            return True
        return False

    def _all_vars(self) -> dict:
        """var_ctx의 모든 변수 entries (dynamic > system 우선). 시스템 프롬프트 안내용."""
        out: dict = {}
        out.update(self.state.var_ctx.system)
        out.update(self.state.var_ctx.dynamic)   # dynamic > system
        out.update(self.state.var_ctx.extracted) # extracted > dynamic
        return out

    async def _membership_silent_transfer(self, target_bot_id: int) -> bool:
        """AICC-908 — 인계 대상 봇의 CallbotMembership.silent_transfer 조회.

        같은 CallbotAgent 안의 멤버십을 우선 조회 — 동일 봇이 여러 콜봇에 속할 수 있어도
        현재 통화 컨텍스트의 콜봇이 기준. 멤버십이 없거나 필드가 비면 False.
        """
        if not target_bot_id:
            return False
        async with SessionLocal() as db:
            # 현재 통화 봇이 속한 콜봇을 찾고, 그 콜봇 안에서 target 멤버십 조회
            current_stmt = select(models.CallbotMembership).where(
                models.CallbotMembership.bot_id == self.bot_id
            ).limit(1)
            current_membership = (await db.execute(current_stmt)).scalars().first()
            if current_membership is not None:
                target_stmt = select(models.CallbotMembership).where(
                    models.CallbotMembership.callbot_id == current_membership.callbot_id,
                    models.CallbotMembership.bot_id == target_bot_id,
                ).limit(1)
                target_membership = (await db.execute(target_stmt)).scalars().first()
                if target_membership is not None:
                    return bool(getattr(target_membership, "silent_transfer", False))
            # fallback — 어느 콜봇에 속한 멤버십이라도 첫 번째 행 사용
            any_stmt = select(models.CallbotMembership).where(
                models.CallbotMembership.bot_id == target_bot_id
            ).limit(1)
            any_membership = (await db.execute(any_stmt)).scalars().first()
            if any_membership is not None:
                return bool(getattr(any_membership, "silent_transfer", False))
        return False

    # ---------- AICC-908 — 인계 시 bot_id 동기 ----------
    def _switch_bot(self, new_bot_id: int) -> None:
        """transfer_to_agent 시 self.bot_id + ContextVar(_bot_id_ctx) + var_ctx.system["bot_id"]
        를 함께 갱신.

        ws_call_context 가 통화 시작 시 main bot_id 로 토큰을 1회 set 한다. 인계가 일어나면
        self.bot_id 만 바꾸고 ContextVar 를 갱신하지 않으면 이후 logger.event 가 stale 한
        main bot_id 로 라벨링된다 — Slack alert / JSON 로그 / 통화 흐름 재구성 모두 어긋남.
        var_ctx.system["bot_id"] 도 start() 에서 1회만 set 되므로, sub 봇의 system_prompt
        에서 `{{bot_id}}` 를 쓰면 stale 한 main bot_id 로 resolve 됨 → 세 곳 동시 갱신.
        이전 인계 토큰이 있으면 reset 후 새로 set (LIFO 보장 — ws_call_context 의 outer
        token 보다 위에만 self 토큰이 쌓이도록).
        """
        if self._bot_id_token is not None:
            try:
                reset_bot_id(self._bot_id_token)
            except (ValueError, LookupError):
                # 다른 컨텍스트에서 set 됐을 가능성 — silent 처리 후 새 토큰으로 진행.
                pass
            self._bot_id_token = None
        self.bot_id = int(new_bot_id)
        self._bot_id_token = set_bot_id(str(new_bot_id))
        # 템플릿 치환용 system 변수도 동기 — {{bot_id}} 사용처가 prompt/SMS body 등에 있을 수
        # 있고 콘솔 자유 입력이라 잠재 silent corruption 회피.
        if hasattr(self, "state") and getattr(self.state, "var_ctx", None) is not None:
            self.state.var_ctx.set_system("bot_id", str(new_bot_id))

    # ---------- AICC-910 — CallbotAgent 설정 캐시 ----------
    async def _load_callbot_settings(self) -> "callbot_module.CallbotAgent | None":
        """현재 bot 이 속한 CallbotAgent 도메인 객체를 1회 로드 (start 시점 호출).

        CallbotAgent 가 없으면 None — barge-in/idle/DTMF/STT keywords/TTS rate 모두 기본값 사용.
        Repository 통해 domain entity 로 받음 — Clean Architecture 준수.
        """
        try:
            async with SessionLocal() as db:
                repo = SqlAlchemyCallbotAgentRepository(db)
                agent = await repo.find_by_bot_id(self.bot_id)
        except Exception as e:
            logger.warning(
                "CallbotAgent 설정 로드 실패 — 기본값 사용",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return None
        return agent

    def _callbot(self) -> "callbot_module.CallbotAgent | None":
        # 테스트가 __init__ 우회 (VoiceSession.__new__) — 안전 가드.
        return getattr(self, "_callbot_settings", None)

    def _stt_keywords(self) -> list[str]:
        cb = self._callbot()
        return cb.normalized_stt_keywords() if cb else []

    def _tts_rate_pitch(self) -> tuple[float, float]:
        cb = self._callbot()
        if cb is None:
            return 1.0, 0.0
        return cb.normalized_speaking_rate(), cb.normalized_pitch()

    def _thinking_budget(self) -> int | None:
        cb = self._callbot()
        return cb.normalized_thinking_budget() if cb is not None else None

    def _tts_apply_pronunciation(self, text: str) -> str:
        """CallbotAgent.tts_pronunciation 의 단순 substring 치환.

        (d) AICC-910: 텍스트 치환만 — SSML 도입은 1차 범위 밖. 빈 dict 면 원본 그대로.
        legacy: tts_pronunciation 비어 있고 pronunciation_dict 만 있으면 그것도 적용.
        """
        cb = self._callbot()
        if cb is None:
            return text
        mapping = cb.tts_pronunciation or {}
        if not mapping and cb.pronunciation_dict:
            mapping = cb.pronunciation_dict
        if not mapping:
            return text
        out = text
        for src, dst in mapping.items():
            if not src:
                continue
            out = out.replace(str(src), str(dst))
        return out

    # ---------- 상태 전이 ----------
    async def set_state(self, value: str) -> None:
        prev = self.state.state
        self.state.state = value
        await self.send_json({"type": "state", "value": value})
        # (b) AICC-910 idle 자동 종료 타이머 관리
        if value == "idle":
            self._start_idle_timer()
        elif prev == "idle" and value != "idle":
            self._cancel_idle_timer()

    # ---------- (b) AICC-910 무응답 자동 종료 ----------
    def _start_idle_timer(self) -> None:
        """idle 진입 직후 호출. 7s 침묵 → idle_prompt_text TTS 1회, 15s 누적 → close('idle_timeout')."""
        if self._closed:
            return
        self._cancel_idle_timer()
        self._idle_prompt_emitted = False
        import time as _time
        self._last_activity_t = _time.monotonic()
        self.state.idle_task = asyncio.create_task(self._idle_loop())

    def _cancel_idle_timer(self) -> None:
        t = self.state.idle_task
        if t is not None and not t.done():
            t.cancel()
        self.state.idle_task = None

    async def _idle_loop(self) -> None:
        """침묵 누적을 폴링. 정책: 상태가 idle 상태에서 벗어나면 즉시 종료 (set_state 가 cancel).

        polling 주기 200ms — 정확도 ±200ms 면 7000/15000 기준 무시 가능 (사용자 체감 X).
        """
        cb = self._callbot()
        prompt_ms = cb.idle_prompt_ms if cb else 7000
        terminate_ms = cb.idle_terminate_ms if cb else 15000
        prompt_text = cb.idle_prompt_text if cb else "여보세요?"
        # 0 이하 값은 기능 비활성 — 음수/0 들어오면 idle 종료 disable.
        if terminate_ms <= 0:
            return
        try:
            poll_s = 0.2
            while not self._closed and self.state.state == "idle":
                await asyncio.sleep(poll_s)
                if self._closed or self.state.state != "idle":
                    return
                import time as _time
                elapsed_ms = int((_time.monotonic() - self._last_activity_t) * 1000)
                # 1차 prompt — 한 번만 발화
                if not self._idle_prompt_emitted and prompt_ms > 0 and elapsed_ms >= prompt_ms:
                    self._idle_prompt_emitted = True
                    logger.event("call.idle_prompt", elapsed_ms=elapsed_ms, text_chars=len(prompt_text or ""))
                    if prompt_text:
                        try:
                            await self._speak_idle_prompt(prompt_text)
                        except Exception as e:
                            logger.warning("idle prompt 발화 실패", error_type=type(e).__name__, error_message=str(e))
                # 종료 — 누적 임계 초과
                if elapsed_ms >= terminate_ms:
                    logger.event("call.idle_timeout", elapsed_ms=elapsed_ms)
                    await self.close(reason="idle_timeout")
                    return
        except asyncio.CancelledError:
            return

    async def _speak_idle_prompt(self, text: str) -> None:
        """idle 동안 callbot 의 idle_prompt_text 를 TTS 로 1회 발화.

        _speak 는 set_state("speaking") 을 호출 → set_state 가 idle 타이머를 cancel 한다.
        prompt 발화 후 idle 로 복귀할 때 set_state("idle") 을 부르면 _start_idle_timer 가
        _idle_prompt_emitted=False / _last_activity_t=now 로 baseline 을 다 리셋해서
        "prompt 1회 + 누적 silence 로 terminate" 룰이 깨진다 (prompt 가 반복되거나
        terminate 카운트가 prompt 발화 시점부터 재시작).
        따라서 set_state 를 우회하고 state 만 "idle" 로 되돌린 뒤 idle_task 만 재시작 —
        _idle_prompt_emitted (=True) 와 _last_activity_t (=prompt 직전 누적 시각) 보존.
        """
        # callbot 의 voice/language 사용 (없으면 봇 기본)
        cb = self._callbot()
        if cb is not None:
            voice = cb.voice
            language = cb.language
        else:
            # 폴백 — Bot.voice / Bot.language
            async with SessionLocal() as db:
                bot = await db.get(models.Bot, self.bot_id)
                voice = bot.voice if bot else "ko-KR-Neural2-A"
                language = bot.language if bot else "ko-KR"
        await self.send_json({"type": "transcript", "role": "assistant", "text": text})
        await self._save_transcript("assistant", text)
        await self._speak(text, voice, language)
        if self._closed:
            return
        # baseline 보존 idle 복귀 — _start_idle_timer 우회.
        self.state.state = "idle"
        await self.send_json({"type": "state", "value": "idle"})
        self._cancel_idle_timer()
        self.state.idle_task = asyncio.create_task(self._idle_loop())

    # ---------- (c) AICC-910 DTMF ----------
    async def on_dtmf(self, digit: str) -> None:
        """클라이언트(SIP gateway/SDK) 의 DTMF 입력 처리. dtmf_map 룩업 + action 실행.

        digit: "0"~"9" / "*" / "#" 중 하나. 그 외 값은 silently ignore.
        action 종류: transfer_to_agent / say / terminate / inject_intent.
        """
        if self._closed:
            return
        if not digit or not isinstance(digit, str):
            return
        d = digit.strip()
        if d not in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "#"}:
            return
        span_id, span_start = await self._tracer.start("dtmf_input", "span", input={"digit": d})
        try:
            cb = self._callbot()
            if cb is None:
                await self._tracer.end(span_id, span_start, meta={"matched": False, "reason": "no_callbot"})
                return
            mapping = cb.normalized_dtmf_map()
            entry = mapping.get(d)
            if not entry:
                await self._tracer.end(span_id, span_start, meta={"matched": False, "reason": "unmapped"})
                return
            action = entry.get("type") or ""
            payload = entry.get("payload") or ""
            logger.event("call.dtmf", digit=d, action=action, payload_chars=len(payload))
            await self._dispatch_dtmf(action, payload)
            await self._tracer.end(span_id, span_start, meta={"matched": True, "action": action})
        except Exception as e:
            await self._tracer.end(span_id, span_start, error=str(e))
            raise

    async def _dispatch_dtmf(self, action: str, payload: str) -> None:
        """4 action: transfer_to_agent / say / terminate / inject_intent."""
        if action == "transfer_to_agent":
            # payload = target bot_id (string). transfer_to_agent 도구 시그널 재사용.
            try:
                target = int(payload)
            except (TypeError, ValueError):
                logger.warning("DTMF transfer_to_agent payload 가 정수 아님 — skip", payload=payload)
                return
            # AICC-908 인계 경로 재사용 (handover 시그널 송신).
            await self._handle_tool_signal(
                "transfer_to_agent",
                {"target_bot_id": target, "reason": "dtmf"},
                runtime=None, turn_id=None,
                via="dtmf",
            )
            if not self._closed:
                await self.set_state("idle")
        elif action == "say":
            # callbot voice/language 로 즉시 발화
            cb = self._callbot()
            voice = cb.voice if cb else "ko-KR-Neural2-A"
            language = cb.language if cb else "ko-KR"
            if payload:
                await self._save_transcript("assistant", payload)
                await self.send_json({"type": "transcript", "role": "assistant", "text": payload})
                await self._speak(payload, voice, language)
            if not self._closed:
                await self.set_state("idle")
        elif action == "terminate":
            # payload 가 EndReason enum 중 하나면 그 reason, 아니면 normalize.
            reason = normalize_end_reason(payload or "normal")
            await self.close(reason=reason)
        elif action == "inject_intent":
            # LLM 컨텍스트에 시스템 user 메시지 형태로 주입 — 다음 turn 에서 의도로 처리되도록.
            # 즉시 _handle_user_final 호출 (DTMF 입력 자체를 사용자 발화로 취급).
            if payload:
                await self._handle_user_final(payload)
        else:
            logger.warning("알 수 없는 DTMF action", action=action)

    # ---------- 외부 입력 ----------
    async def on_audio(self, chunk: bytes) -> None:
        if self._closed:
            return
        events = self.vad.feed(chunk)
        for ev in events:
            if ev.kind == "start":
                await self._on_speech_start()
            elif ev.kind == "end":
                await self._on_speech_end()
        if self.state.state == "listening":
            await self._audio_q.put(chunk)

    async def on_text_message(self, user_text: str) -> None:
        """텍스트 모드 — STT를 우회하고 사용자 입력으로 직접 LLM 호출."""
        if self._closed:
            return
        await self._handle_user_final(user_text)

    async def start(self) -> None:
        # (a)(b)(d)(e) AICC-910 — CallbotAgent 설정 우선 로드 (greeting_barge_in 분기 등)
        self._callbot_settings = await self._load_callbot_settings()

        await self.set_state("idle")

        # System + Dynamic 변수 채움 (vox VOX_AGENT_STRUCTURE §5)
        self.state.var_ctx.set_system("call_id", str(self.session_id))
        async with SessionLocal() as db:
            sess = await db.get(models.CallSession, self.session_id)
            if sess:
                self.state.var_ctx.set_system("room_id", sess.room_id)
                self.state.var_ctx.set_system("started_at", sess.started_at.isoformat() if sess.started_at else "")
                # SDK/웹훅이 주입한 dynamic 변수 — calls/start payload.vars로 들어옴
                if sess.dynamic_vars:
                    self.state.var_ctx.merge_dynamic(dict(sess.dynamic_vars))
        self.state.var_ctx.set_system("bot_id", str(self.bot_id))

        # session_start 자동 호출 도구 실행 (vox pre-call 패턴) — 인사말 전에
        await self._run_auto_calls("session_start")

        # 인사말은 텍스트로 먼저 보냄 (음성 모드면 TTS도 함께)
        async with SessionLocal() as db:
            runtime, skill = await build_runtime(db, self.bot_id, None, auto_context=self.state.auto_context, variables=self._all_vars())
        self.state.active_skill = skill
        if runtime.greeting:
            greeting = self.state.var_ctx.resolve(runtime.greeting)
            await self._save_transcript("assistant", greeting)
            await self.send_json(
                {"type": "transcript", "role": "assistant", "text": greeting}
            )
            # (a) AICC-910 — 인사말 동안 barge-in 가드. _on_speech_start 가 in_greeting 을 보고 분기.
            self.state.in_greeting = True
            try:
                await self._speak(greeting, runtime.voice, runtime.language)
            finally:
                self.state.in_greeting = False
            # 인사말 발화 후 idle 복귀 — 안 그러면 클라이언트가 사용자 음성을 echo로 차단함
            if not self._closed:
                await self.set_state("idle")

    async def close(self, reason: str = "normal") -> None:
        if self._closed:
            return
        self._closed = True
        # AICC-909 — 6값 EndReason enum 으로 정규화 (레거시 user_end / disconnect / global_rule:* 흡수)
        normalized_reason = normalize_end_reason(reason)
        if self.state.speech_task and not self.state.speech_task.done():
            self.state.speech_task.cancel()
        if self._stt_task and not self._stt_task.done():
            self._stt_task.cancel()
        if self.state.pending_runtime_task and not self.state.pending_runtime_task.done():
            self.state.pending_runtime_task.cancel()
        # (b) AICC-910 — idle 타이머 정리
        self._cancel_idle_timer()
        await self._audio_q.put(None)
        # 세션 격리: 종료 commit 은 자체 SessionLocal 로 — STT/LLM/TTS task 가 보유한 세션과 충돌 X
        # async lazy load 불가 → bot 관계 selectinload 로 함께 가져오기
        stmt = (
            select(models.CallSession)
            .where(models.CallSession.id == self.session_id)
            .options(selectinload(models.CallSession.bot))
        )
        model_name = "gemini-3.1-flash-lite"
        async with SessionLocal() as db:
            sess = (await db.execute(stmt)).scalar_one_or_none()
            if sess and sess.status != "ended":
                from datetime import datetime

                sess.status = "ended"
                sess.ended_at = datetime.utcnow()
                sess.end_reason = normalized_reason
                if sess.bot and sess.bot.llm_model:
                    model_name = sess.bot.llm_model
                await db.commit()
            elif sess and sess.bot and sess.bot.llm_model:
                model_name = sess.bot.llm_model
        await self.send_json({"type": "end", "reason": normalized_reason})
        # AICC-909 표준 이벤트 — reason 은 EndReason enum 값.
        logger.event("call.end", reason=normalized_reason)

        # 통화 후 분석 (백그라운드 태스크) — 자체 SessionLocal 로 처리 (post_call.analyze_session)
        asyncio.create_task(self._run_post_call_analysis(model_name))

        # AICC-908 — 인계 토큰 정리. ws_call_context 의 outer t_bot 이 reset 되기 전에 self 가
        # 쌓은 토큰부터 먼저 reset (LIFO). post_call 태스크는 이미 spawn 됐고 자기 context 사본을
        # 가지므로 여기서 reset 해도 영향 없음.
        if self._bot_id_token is not None:
            try:
                reset_bot_id(self._bot_id_token)
            except (ValueError, LookupError):
                pass
            self._bot_id_token = None

    # ---------- 내부 로직 ----------
    async def _on_speech_start(self) -> None:
        # Echo grace — idle 상태에서 봇 발화 종료 직후 들어온 speech_start는 잔향으로 간주, 무시.
        # (speaking 중 barge-in은 grace 적용 안 함 — 진짜 사용자 끼어들기 위해)
        if self.state.state == "idle" and self.state.last_speak_end_t > 0:
            import time as _time
            elapsed = _time.monotonic() - self.state.last_speak_end_t
            if elapsed < _ECHO_GRACE_S:
                logger.debug("speech_start ignored — within echo grace", elapsed_ms=int(elapsed * 1000))
                return
        # (a) AICC-910 — 인사말 동안 barge-in 가드. greeting_barge_in=False(기본)면 cancel skip.
        if self.state.in_greeting:
            cb = self._callbot()
            allow = bool(cb.greeting_barge_in) if cb is not None else False
            if not allow:
                logger.debug("speech_start ignored — greeting_barge_in disabled")
                return
        # barge-in: 봇이 말하는 중이면 즉시 중단 (TTS speech_task + STT 이전 task 둘 다 정리)
        if self.state.state == "speaking" and self.state.speech_task:
            import time as _time
            elapsed_ms: int | None = None
            if self.state.last_speak_start_t > 0:
                elapsed_ms = int((_time.monotonic() - self.state.last_speak_start_t) * 1000)
            in_greeting = bool(self.state.in_greeting)
            # 신규분에 span() 패턴 적용 — 통화 상세 Waterfall 에서 barge-in 시점 시각화.
            # span() 이 try/finally 로 _stack pop 보장 → tracer.start/end raw 호출의 누수 위험 회피.
            async with self._tracer.span(
                "barge_in",
                "span",
                input={"in_greeting": in_greeting, "elapsed_ms": elapsed_ms},
            ):
                logger.event(
                    "call.barge_in",
                    in_greeting=in_greeting,
                    elapsed_since_speak_start_ms=elapsed_ms,
                )
                await self.send_json({
                    "type": "barge_in",
                    "in_greeting": in_greeting,
                    "elapsed_ms": elapsed_ms,
                })
                self.state.speech_task.cancel()
        # 이전 turn 의 STT task 가 살아 있으면 정리 — 새 audio_q 로 교체하므로 그대로 두면 leak.
        if self._stt_task and not self._stt_task.done():
            self._stt_task.cancel()
        # 이전 발화의 prefetch task가 남아있으면 정리 (interim 도달 → speech_end 없이 끊긴 경우)
        if self.state.pending_runtime_task and not self.state.pending_runtime_task.done():
            self.state.pending_runtime_task.cancel()
        self.state.pending_runtime_task = None
        self.state.pending_runtime_interim_text = ""
        # (f1) — 매 발화마다 interim 첫 도달 시각 리셋
        self.state.first_interim_t = None
        await self.set_state("listening")
        # STT 스트림 시작
        self._audio_q = asyncio.Queue()
        self._stt_task = asyncio.create_task(self._run_stt())

    async def _on_speech_end(self) -> None:
        import time as _time
        # (b) AICC-910 — 사용자 발화 종료 시 침묵 카운트 리셋 (다음 turn 시작)
        self._last_activity_t = _time.monotonic()
        await self._audio_q.put(None)

    def _maybe_start_prefetch(self, interim_text: str) -> None:
        """interim 텍스트 길이가 임계치 이상이고 아직 prefetch 안 했으면 백그라운드 task spawn.

        callbot_v0 흡수 #3 — 사용자가 말하는 도중 build_runtime을 미리 실행해 TTFF ~500ms~1s 절감.
        skill 라우팅은 interim으로 결정하지 않음 (잘못된 skill 위험) — active_skill은 그대로 두고
        runtime(language·voice·system_prompt·tools 합성)만 미리 빌드한다.
        """
        if self.state.pending_runtime_task is not None:
            return
        threshold = settings.preempt_min_chars
        if threshold <= 0 or len(interim_text) < threshold:
            return
        self.state.pending_runtime_interim_text = interim_text
        self.state.pending_runtime_task = asyncio.create_task(
            self._prefetch_runtime(interim_text)
        )

    async def _prefetch_runtime(self, interim_text: str):
        """interim 텍스트로 build_runtime을 백그라운드 실행. tracer span 기록."""
        span_id, span_start = await self._tracer.start(
            "prefetch_runtime", "span",
            input={"interim_chars": len(interim_text), "active_skill": self.state.active_skill},
        )
        try:
            async with SessionLocal() as db:
                result = await build_runtime(
                    db,
                    self.bot_id,
                    self.state.active_skill,
                    auto_context=self.state.auto_context,
                    variables=self._all_vars(),
                )
            await self._tracer.end(span_id, span_start, meta={"ok": True})
            return result
        except Exception as e:
            await self._tracer.end(span_id, span_start, error=str(e))
            raise

    async def _consume_prefetched_runtime(self) -> tuple:
        """_handle_user_final에서 호출. prefetched task 있으면 그 결과를, 없거나 실패면 fresh build.

        반환: (runtime, used_prefetch_bool). active_skill·auto_context는 turn 시작~final 동안
        바뀌지 않으므로 interim 시점 결과를 그대로 신뢰해도 안전 (skill 전환은 LLM 응답 후에만 발생).
        """
        task = self.state.pending_runtime_task
        self.state.pending_runtime_task = None
        used_prefetch = False
        if task is not None and not task.cancelled():
            try:
                runtime, _ = await task
                used_prefetch = True
                return runtime, used_prefetch
            except Exception as e:
                logger.warning(
                    "prefetched runtime failed, falling back to fresh build",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
        async with SessionLocal() as db:
            runtime, _ = await build_runtime(
                db,
                self.bot_id,
                self.state.active_skill,
                auto_context=self.state.auto_context,
                variables=self._all_vars(),
            )
        return runtime, used_prefetch

    async def _run_stt(self) -> None:
        async with SessionLocal() as db:
            runtime, _ = await build_runtime(db, self.bot_id, self.state.active_skill, auto_context=self.state.auto_context, variables=self._all_vars())

        chunk_count = 0
        chunk_bytes = 0

        async def audio_iter():
            nonlocal chunk_count, chunk_bytes
            while True:
                item = await self._audio_q.get()
                if item is None:
                    return
                chunk_count += 1
                chunk_bytes += len(item) if item else 0
                yield item

        stt_id, stt_start = await self._tracer.start(
            "stt", "stt",
            input={"language": runtime.language, "sample_rate": self.sample_rate},
        )
        # AICC-909 — STT 세션 단위 latency 측정. tracer.duration_ms 와 별개로 JSON 로그 stt_ms 분리.
        stt_mono_start = time.monotonic()
        logger.event(
            "stt.session_started",
            vendor=settings.provider_stt,
            language=runtime.language,
            sample_rate=self.sample_rate,
        )
        final_text = ""
        partial_count = 0
        # (d) AICC-910 — CallbotAgent.stt_keywords 를 phrase hint 로 STT 에 전달.
        keywords = self._stt_keywords()
        try:
            async for result in self.stt.transcribe(
                audio_iter(),
                language=runtime.language,
                sample_rate=self.sample_rate,
                keywords=keywords or None,
            ):
                if not result.text:
                    continue
                if not result.is_final:
                    partial_count += 1
                    # (f1) AICC-910 — interim 첫 도달 시각 기록 (barge-in 가속 측정/테스트용)
                    if self.state.first_interim_t is None:
                        self.state.first_interim_t = time.monotonic()
                    # callbot_v0 흡수 #3 — interim N자+ 도달 시 build_runtime 선제 실행
                    self._maybe_start_prefetch(result.text)
                await self.send_json(
                    {
                        "type": "transcript",
                        "role": "user",
                        "text": result.text,
                        "is_final": result.is_final,
                    }
                )
                if result.is_final:
                    final_text = result.text
        except asyncio.CancelledError:
            stt_ms = int((time.monotonic() - stt_mono_start) * 1000)
            await self._tracer.end(stt_id, stt_start, meta={"cancelled": True, "partials": partial_count, "chunks": chunk_count, "bytes": chunk_bytes, "stt_ms": stt_ms})
            logger.event(
                "stt.session_ended",
                stt_ms=stt_ms,
                total_partials=partial_count,
                total_finals=0,
                cancelled=True,
            )
            return
        except Exception as e:
            stt_ms = int((time.monotonic() - stt_mono_start) * 1000)
            await self._tracer.end(stt_id, stt_start, error=str(e), meta={"partials": partial_count, "chunks": chunk_count, "bytes": chunk_bytes, "stt_ms": stt_ms})
            logger.error(
                "stt.error",
                event="stt.error",
                error_type=type(e).__name__,
                vendor=settings.provider_stt,
                stt_ms=stt_ms,
            )
            await self.send_json({"type": "error", "where": "stt", "message": str(e)})
            await self.set_state("idle")
            return

        stt_ms = int((time.monotonic() - stt_mono_start) * 1000)
        await self._tracer.end(
            stt_id, stt_start,
            output=final_text or None,
            meta={"partials": partial_count, "final_chars": len(final_text),
                  "chunks": chunk_count, "bytes": chunk_bytes, "stt_ms": stt_ms},
        )
        # AICC-909 — stt.final 표준 이벤트. PII 정책: text 본문 X, text_hash + char_count 만.
        logger.event(
            "stt.final",
            stt_ms=stt_ms,
            char_count=len(final_text),
            text_hash=hash_text(final_text),
            partials=partial_count,
            vendor=settings.provider_stt,
        )
        if final_text.strip():
            await self._handle_user_final(final_text.strip())
        else:
            await self.set_state("idle")

    async def _build_history(self, max_turns: int = 12) -> list[ChatMessage]:
        """최근 N turn의 final transcript를 LLM 히스토리로 변환.
        현재 turn의 user 발화는 호출자가 user_text로 별도 전달하므로 여기엔 미포함.

        세션 격리: 자체 SessionLocal 로 read-only 쿼리 — 다른 task 가 같은 세션을 만지지 않게.
        """
        stmt = (
            select(models.Transcript)
            .where(
                models.Transcript.session_id == self.session_id,
                models.Transcript.is_final.is_(True),
                models.Transcript.role.in_(["user", "assistant"]),
            )
            .order_by(models.Transcript.id)
        )
        async with SessionLocal() as db:
            finals = list((await db.execute(stmt)).scalars().all())
        # 마지막 turn(=방금 저장한 user 발화)은 user_text로 따로 보내므로 제외
        if finals and finals[-1].role == "user":
            finals = finals[:-1]
        # 너무 길면 최근 N개만
        finals = finals[-max_turns:]
        return [ChatMessage(role=t.role, text=t.text) for t in finals]  # type: ignore

    async def _handle_user_final(self, user_text: str) -> None:
        import time as _time
        await self._save_transcript("user", user_text)
        await self.set_state("thinking")
        # TTFF 시작점: STT final 이후 _handle_user_final 진입 시점
        self.state.turn_t0 = _time.monotonic()
        self.state.first_audio_t = None

        # § 4 ① 공통 규칙 검사 — LLM 호출 전 가장 먼저 (vox VOX_AGENT_STRUCTURE)
        if await self._check_global_rules(user_text):
            return  # 룰 매치 시 즉시 액션 후 종료, LLM 호출 X

        history = await self._build_history()

        # 정규식 보조 추출 — LLM이 instruction을 놓쳐도 보장
        heur = _heuristic_extract(user_text)
        if heur:
            for k, v in heur.items():
                if not self.state.var_ctx.has(k):  # 이미 있으면 건드리지 않음
                    self.state.var_ctx.set_extracted(k, v)
            if any(not self.state.var_ctx.has(k) or self.state.var_ctx.get(k) == v for k, v in heur.items()):
                await self.send_json({"type": "extracted", "values": heur, "source": "regex"})

        turn_id, turn_start = await self._tracer.start(
            f"turn: {user_text[:60]}", "turn",
            input={"user_text": user_text, "active_skill": self.state.active_skill, "history_turns": len(history)},
        )
        try:
            # 시스템 프롬프트 합성 sub-span (Skill/Knowledge/Tools 머지)
            build_id, build_start = await self._tracer.start(
                "build_prompt", "span", parent_id=turn_id,
                input={"active_skill": self.state.active_skill},
            )
            runtime, used_prefetch = await self._consume_prefetched_runtime()
            # VariableContext {{var}} 치환 — system/dynamic/extracted 변수 system_prompt에 인라인
            resolved_system_prompt = self.state.var_ctx.resolve(runtime.system_prompt)
            # callbot_v0 흡수 — 외부 RAG (document_processor) 옵션 호출
            external_kb_text = await self._maybe_fetch_external_kb(user_text, parent_turn_id=turn_id)
            if external_kb_text:
                resolved_system_prompt = resolved_system_prompt + "\n\n---\n\n" + external_kb_text
            await self._tracer.end(
                build_id, build_start,
                meta={"system_prompt_chars": len(resolved_system_prompt), "model": runtime.llm_model,
                      "var_keys": sorted(self.state.var_ctx.keys()),
                      "prefetched": used_prefetch,
                      "external_kb_chars": len(external_kb_text)},
            )

            # callbot_v0 흡수 #1 (function calling) + #2 (streaming + 문장 TTS)
            # 항상 stream으로 시작. 첫 chunk가 tool_call이면 tool 루프 진입, text면 문장 streaming.
            tool_specs = await self._build_tool_specs()
            # barge-in cancel 시 partial sentence 회수용 baseline 초기화 (방어).
            self.state.streaming_sentences = []
            try:
                sentences, signal_tail = await self._run_streaming_turn(
                    turn_id, resolved_system_prompt, user_text, history, runtime, tool_specs,
                )
            except asyncio.CancelledError:
                # _stt_task cancel 로 도달. commit 된 sentence (PCM 끝까지 송출된 것) 만 transcript
                # 에 보존. shield 로 save 가 cancel 영향 안 받게 한 뒤 cancel 재전파.
                committed = list(self.state.streaming_sentences)
                if committed:
                    full_body = " ".join(committed).strip()
                    if full_body:
                        await asyncio.shield(self._save_transcript("assistant", full_body))
                raise

            # sentences=None: tool path 완료 또는 에러. 시그널 파싱·transcript 저장 스킵하고
            # finally 거쳐 set_state("idle")로 복귀. 에러 경로는 내부에서 이미 idle 처리됨.
            if sentences is not None:
                # parse_signal_and_strip은 SIGNAL TAIL(JSON-looking 마지막 partial)에만 적용.
                # 일반 문장은 이미 streaming으로 TTS·송출됐으므로 다시 처리하면 중복.
                raw_signal = signal_tail or ""
                parse_id, parse_start = await self._tracer.start(
                    "parse_signal", "span", parent_id=turn_id, input={"raw_chars": len(raw_signal)}
                )
                body_residual, signal = parse_signal_and_strip(raw_signal)
                await self._tracer.end(
                    parse_id, parse_start,
                    meta={
                        "next_skill": signal.next_skill,
                        "body_residual_chars": len(body_residual),
                        "extracted": list((signal.extracted or {}).keys()),
                        "sentences_count": len(sentences),
                    },
                )
                if signal.extracted:
                    for k, v in signal.extracted.items():
                        self.state.var_ctx.set_extracted(k, v)
                    await self.send_json({"type": "extracted", "values": signal.extracted})
                if signal.next_skill:
                    async with SessionLocal() as db:
                        bot = await find_bot(db, self.bot_id)
                    skill_names = {s.name for s in bot.skills} if bot else set()
                    db_tool_names = {t.name for t in bot.tools if t.is_enabled} if bot else set()
                    tool_names = _BUILTIN_TOOL_NAMES | db_tool_names
                    if signal.next_skill not in skill_names and signal.next_skill in tool_names:
                        logger.info(
                            "LLM이 도구 이름을 next_skill로 보냄 — 무시 (native FC로 처리됨)",
                            next_skill=signal.next_skill,
                        )
                    else:
                        self.state.active_skill = signal.next_skill
                        await self.send_json({"type": "skill", "name": signal.next_skill})

                # signal_tail에 prose가 섞여 있던 edge case 안전망 — 보통 비어 있다.
                if body_residual.strip():
                    await self._save_transcript("assistant", body_residual)
                    await self.send_json({"type": "transcript", "role": "assistant", "text": body_residual})
                    tts_id, tts_start = await self._tracer.start(
                        "tts.residual", "tts", parent_id=turn_id,
                        input={"text": body_residual, "voice": runtime.voice, "language": runtime.language},
                    )
                    try:
                        await self._speak(body_residual, runtime.voice, runtime.language)
                        await self._tracer.end(tts_id, tts_start, meta={"chars": len(body_residual)})
                    except Exception as e:
                        await self._tracer.end(tts_id, tts_start, error=str(e))
                        raise

                # streaming 중 이미 TTS·송출된 문장들은 transcript로 한 번 저장 (DB 행 1개).
                # commit-aware 로직 (commit-aware-streaming-turn) 으로 sentences 가 비어 있을 수 있음
                # (LLM 첫 chunk 도착 전 barge-in 등) — 빈 row 저장 방지.
                if sentences:
                    full_body = " ".join(sentences).strip()
                    if body_residual.strip():
                        full_body = (full_body + " " + body_residual).strip()
                    if full_body:
                        await self._save_transcript("assistant", full_body)
        finally:
            # TTFF 계산 (있을 때만): user_text 처리 시작 ~ 첫 PCM 송신
            ttff_ms = None
            if self.state.turn_t0 is not None and self.state.first_audio_t is not None:
                ttff_ms = int((self.state.first_audio_t - self.state.turn_t0) * 1000)
            self.state.turn_t0 = None
            self.state.first_audio_t = None
            meta = {"active_skill": self.state.active_skill}
            if ttff_ms is not None:
                meta["ttff_ms"] = ttff_ms
            await self._tracer.end(turn_id, turn_start, meta=meta)

        # barge-in 보호: 발화 도중 사용자가 끼어들면 _on_speech_start가 이미 state를 "listening"
        # (또는 그 뒤 thinking)으로 바꿔놨을 수 있다. 그 경우 idle로 덮어쓰지 않는다.
        if not self._closed and self.state.state not in ("listening", "thinking"):
            await self.set_state("idle")

    # ---------- callbot_v0 흡수 — 외부 RAG (document_processor) ----------

    async def _maybe_fetch_external_kb(self, user_text: str, *, parent_turn_id: int | None = None) -> str:
        """봇.external_kb_enabled=True + env URL 설정 시에만 document_processor 검색.

        실패해도 빈 문자열 반환 (LLM 호출은 계속). 토글 OFF면 즉시 빈 반환.
        """
        async with SessionLocal() as db:
            bot = await db.get(models.Bot, self.bot_id)
            if bot is None or not bot.external_kb_enabled:
                return ""
            inquiry_types_raw = bot.external_kb_inquiry_types
        if not settings.document_processor_base_url:
            return ""  # 토글은 켜졌지만 환경 미설정 — 조용히 skip

        from ..infrastructure.adapters import document_processor as dp

        span_id, span_start = await self._tracer.start(
            "external_kb_retrieve", "span", parent_id=parent_turn_id,
            input={"q": user_text[:100], "tenant_id": settings.document_processor_tenant_id},
        )
        try:
            inquiry_types = list(inquiry_types_raw or []) or None
            results = await dp.search(query=user_text, inquiry_types=inquiry_types)
            formatted = dp.format_results_for_prompt(results)
            await self._tracer.end(
                span_id, span_start,
                meta={"results_count": len(results), "chars": len(formatted),
                      "inquiry_types": inquiry_types or "(env default)"},
            )
            return formatted
        except Exception as e:
            await self._tracer.end(span_id, span_start, error=str(e))
            logger.warning(
                "external_kb_retrieve failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return ""

    # ---------- callbot_v0 흡수 #2 — streaming + 문장 TTS ----------

    @staticmethod
    def _looks_like_signal_chunk(text: str) -> bool:
        """LLM이 시그널 JSON을 별도 chunk로 emit한 경우를 식별 — TTS에서 제외해야 함.

        조건: 공백 제거 후 `{`로 시작하고 `}`로 끝남. JSON object 형태.
        한국어 자연어 문장이 우연히 이 패턴을 만족할 확률은 사실상 0.
        """
        t = text.strip()
        return t.startswith("{") and t.endswith("}")

    async def _run_streaming_turn(
        self, turn_id: int, system_prompt: str, user_text: str,
        history: list[ChatMessage], runtime, tool_specs: list[ToolSpec],
    ) -> tuple[list[str] | None, str | None]:
        """LLM stream 시작 → 첫 chunk 검사로 분기:
        - tool_call이면 tool 루프 진입 (continue_after_tool은 비-stream)
        - text면 문장 단위로 즉시 TTS·송출

        반환: (sentences, signal_text)
          sentences = streaming으로 emit·TTS된 문장 list (transcript 누적용)
          signal_text = 누적 텍스트 + 마지막 partial — parse_signal_and_strip 입력
          turn이 tool 루프나 에러로 종료되면 (None, None)

        commit 정책: `_speak` 가 PCM 끝까지 emit 한 sentence 만 sentences 에 추가. barge-in
        으로 cut 된 sentence (uncommitted) 는 폐기. 그리고 partial sentences 회수 위해
        `self.state.streaming_sentences` (인스턴스 속성) 에도 같은 리스트 참조를 둠 — turn 도중
        CancelledError 로 본 함수가 중단되면 `_handle_user_final` 의 except 가 그 리스트에서
        commit 된 sentence 들을 읽어 transcript 에 저장.
        """
        sentences: list[str] = []
        self.state.streaming_sentences = sentences  # 같은 list 참조 — partial 회수용
        partial_tail = ""
        first_chunk: LLMResponse | None = None

        llm_id, llm_start = await self._tracer.start(
            "llm.stream", "llm", parent_id=turn_id,
            input={"system_prompt": system_prompt, "user_text": user_text,
                   "model": runtime.llm_model, "tools_count": len(tool_specs),
                   "history": [{"role": h.role, "text": h.text} for h in history]},
        )
        llm_mono_start = time.monotonic()
        # AICC-909 — llm.request 표준 이벤트. PII: system_prompt/user_text 본문 X, hash 만.
        logger.event(
            "llm.request",
            model=runtime.llm_model,
            system_prompt_hash=hash_text(system_prompt),
            user_text_hash=hash_text(user_text),
            user_text_chars=len(user_text),
            history_turns=len(history),
            tools_count=len(tool_specs),
        )

        stream_iter = self.llm.stream(
            system_prompt=system_prompt, user_text=user_text, model=runtime.llm_model,
            history=history, tools=tool_specs,
            thinking_budget=self._thinking_budget(),
        )
        try:
            try:
                async for chunk in stream_iter:
                    # barge-in race 가드 — _on_speech_start 가 state="listening" 으로 전환 후
                    # cancel 신호 도착 전 다음 chunk 가 새는 케이스 차단.
                    if self.state.state == "listening":
                        break
                    if first_chunk is None:
                        first_chunk = chunk
                        # 첫 chunk가 tool_call이면 stream 닫고 tool 루프로
                        if chunk.tool_call:
                            llm_ms = int((time.monotonic() - llm_mono_start) * 1000)
                            await self._tracer.end(
                                llm_id, llm_start,
                                output=f"<tool_call: {chunk.tool_call.name}>",
                                meta={"model": runtime.llm_model, "tool_call": chunk.tool_call.name,
                                      "sentences": 0, "llm_ms": llm_ms},
                            )
                            logger.event(
                                "llm.response",
                                model=runtime.llm_model,
                                llm_ms=llm_ms,
                                finish_reason="tool_call",
                                tool_calls_count=1,
                                sentences=0,
                            )
                            try:
                                await stream_iter.aclose()
                            except Exception:
                                pass
                            await self._run_tool_loop_after_stream(
                                turn_id, system_prompt, history, runtime, tool_specs, first_chunk,
                            )
                            return None, None
                    # text chunk — 시그널 JSON이면 TTS 스킵 (parse_signal_and_strip이 나중에 추출)
                    if chunk.text:
                        if self._looks_like_signal_chunk(chunk.text):
                            partial_tail = (partial_tail + "\n" + chunk.text).strip() if partial_tail else chunk.text
                        else:
                            # commit-aware: PCM 끝까지 송출된 sentence 만 누적. cut 된 건 폐기.
                            committed = await self._send_and_speak_sentence(
                                chunk.text, runtime, turn_id, len(sentences),
                            )
                            if not committed:
                                # barge-in 으로 sentence cut — 다음 chunk 도 처리 안 함.
                                break
                            sentences.append(chunk.text)
                # stream 종료 — 마지막 partial(종결자 없는 buf)이 sentences에 합쳐졌을 수도 있음.
                # GeminiLLM은 partial을 마지막 yield로 보내므로 위 루프에서 이미 들어옴.
                # signal 파싱을 위해 누적 텍스트 + 만약 partial을 따로 받았다면 합치는 로직 필요 —
                # 현 구현은 partial도 sentence로 함께 yield되어 sentences에 들어가므로 그대로 join 사용.
            except Exception as e:
                llm_ms = int((time.monotonic() - llm_mono_start) * 1000)
                await self._tracer.end(llm_id, llm_start, error=str(e), meta={"llm_ms": llm_ms})
                logger.error(
                    "llm.error",
                    event="llm.error",
                    error_type=type(e).__name__,
                    model=runtime.llm_model,
                    llm_ms=llm_ms,
                )
                logger.exception("LLM stream error", error_type=type(e).__name__)
                await self.send_json({"type": "error", "where": "llm", "message": str(e)})
                await self.set_state("idle")
                return None, None

            llm_ms = int((time.monotonic() - llm_mono_start) * 1000)
            await self._tracer.end(
                llm_id, llm_start,
                output=" ".join(sentences),
                meta={"model": runtime.llm_model, "tool_call": None,
                      "sentences": len(sentences), "llm_ms": llm_ms},
            )
            logger.event(
                "llm.response",
                model=runtime.llm_model,
                llm_ms=llm_ms,
                finish_reason="stop",
                sentences=len(sentences),
                response_chars=sum(len(s) for s in sentences),
            )
        finally:
            # barge-in break (listening state / uncommitted sentence) 경로에서 stream_iter 가 닫히지
            # 않으면 LLM provider 가 백그라운드에서 계속 토큰 생성 — 비용/race 위험. tool_call 분기는
            # 이미 명시 aclose() 호출하므로 본 finally 는 정상 종료/Exception/CancelledError/break 모두
            # 커버하는 안전망.
            try:
                await stream_iter.aclose()
            except Exception:
                pass

        # signal_tail: 시그널 JSON으로 의심되어 TTS 스킵된 chunk들의 누적. parse_signal_and_strip 입력.
        # streaming으로 emit·TTS된 sentences는 다시 처리하지 않음 — 중복 방지.
        return sentences, partial_tail

    async def _send_and_speak_sentence(
        self, sentence: str, runtime, turn_id: int, idx: int,
    ) -> bool:
        """문장 도착 즉시 transcript 전송 + TTS 합성·송출. 문장 N+1은 N의 송출 완료 후 시작 (직렬).

        직렬화 이유: TTSPort.synthesize가 AsyncIterator[bytes]라 클라에 PCM 순서가 보장되어야 함.
        callbot_v0와 동일한 패턴.

        반환: True=PCM 끝까지 송출 (commit), False=barge-in 으로 중간 cut (uncommitted).
        uncommitted sentence 는 호출자가 transcript 누적 리스트에 추가하지 않아야 함 — 고객이
        끝까지 못 들은 내용을 LLM 다음 턴 history 로 들이지 않기 위함.
        """
        await self.send_json({"type": "transcript", "role": "assistant", "text": sentence})
        tts_id, tts_start = await self._tracer.start(
            f"tts.s{idx}", "tts", parent_id=turn_id,
            input={"text": sentence, "voice": runtime.voice, "language": runtime.language},
        )
        tts_mono_start = time.monotonic()
        try:
            committed = await self._speak(sentence, runtime.voice, runtime.language)
            tts_ms = int((time.monotonic() - tts_mono_start) * 1000)
            await self._tracer.end(
                tts_id, tts_start,
                meta={"chars": len(sentence), "tts_ms": tts_ms, "committed": committed},
            )
            # AICC-909 — tts.synthesized 표준 이벤트.
            logger.event(
                "tts.synthesized",
                tts_ms=tts_ms,
                char_count=len(sentence),
                voice=runtime.voice,
                language=runtime.language,
                vendor=settings.provider_tts,
                sentence_idx=idx,
                committed=committed,
            )
            return committed
        except Exception as e:
            tts_ms = int((time.monotonic() - tts_mono_start) * 1000)
            await self._tracer.end(tts_id, tts_start, error=str(e), meta={"tts_ms": tts_ms})
            logger.error(
                "tts.error",
                event="tts.error",
                error_type=type(e).__name__,
                vendor=settings.provider_tts,
                voice=runtime.voice,
                tts_ms=tts_ms,
            )
            raise

    async def _run_tool_loop_after_stream(
        self, turn_id: int, system_prompt: str, history: list[ChatMessage],
        runtime, tool_specs: list[ToolSpec], first_response: LLMResponse,
    ) -> None:
        """stream 첫 chunk가 tool_call이면 진입. continue_after_tool은 비-stream으로 호출 — 결과 문장은
        보통 짧고, P1 검증으로 tool_call 후속 응답에서도 stream 가능하지만 단순화 위해 generate 사용."""
        response = first_response
        tool_iter = 0
        max_iter = settings.tool_loop_max_iterations
        while response.tool_call is not None and tool_iter < max_iter:
            tool_iter += 1
            tool_name = response.tool_call.name
            tool_args = _resolve_args_deep(response.tool_call.args or {}, self.state.var_ctx)
            tool_result, terminating = await self._execute_tool_for_loop(
                tool_name, tool_args, runtime, turn_id,
            )
            if terminating:
                return
            response = await self._llm_continue_with_trace(
                turn_id, "llm.tool_followup",
                system_prompt=system_prompt, history=history,
                prior_model_content=response.raw_model_content,
                tool_name=tool_name,
                tool_result=tool_result if tool_result is not None else {"error": "no_result"},
                model=runtime.llm_model, tools=tool_specs,
            )
            if response is None:
                return

        if response.tool_call is not None and tool_iter >= max_iter:
            logger.warning("tool loop reached max iterations", max_iter=max_iter)

        # 마지막 text 응답 TTS — 비-stream이라 통째로
        text = (response.text or "").strip()
        if text:
            body, signal = parse_signal_and_strip(text)
            if signal.extracted:
                for k, v in signal.extracted.items():
                    self.state.var_ctx.set_extracted(k, v)
                await self.send_json({"type": "extracted", "values": signal.extracted})
            if signal.next_skill:
                async with SessionLocal() as db:
                    bot = await find_bot(db, self.bot_id)
                skill_names = {s.name for s in bot.skills} if bot else set()
                if signal.next_skill in skill_names:
                    self.state.active_skill = signal.next_skill
                    await self.send_json({"type": "skill", "name": signal.next_skill})
            if body:
                # commit-aware: PCM 끝까지 송출된 경우에만 transcript 에 save. barge-in 으로 cut 된
                # tool followup 응답은 LLM 다음 턴 history 에 포함되지 않게 폐기.
                # cancel 전파 case 는 _handle_user_final 의 try/except CancelledError 가 처리.
                await self.send_json({"type": "transcript", "role": "assistant", "text": body})
                tts_id, tts_start = await self._tracer.start(
                    "tts.followup", "tts", parent_id=turn_id,
                    input={"text": body, "voice": runtime.voice, "language": runtime.language},
                )
                try:
                    committed = await self._speak(body, runtime.voice, runtime.language)
                    await self._tracer.end(
                        tts_id, tts_start, meta={"chars": len(body), "committed": committed},
                    )
                except Exception as e:
                    await self._tracer.end(tts_id, tts_start, error=str(e))
                    raise
                if committed:
                    await self._save_transcript("assistant", body)

    # ---------- callbot_v0 흡수 #1 — native function calling 헬퍼 ----------

    async def _build_tool_specs(self) -> list[ToolSpec]:
        """LLM에 노출할 도구 스펙 = builtin + bot.tools(enabled).

        callbot_v0 흡수 — 활성 스킬에 allowed_tool_names가 있으면 그 목록만 노출.
        빈 리스트는 'legacy: 전체 허용' 의미. builtin(end_call, transfer 등)은 안전 escape이라 항상 노출.
        """
        specs: list[ToolSpec] = list(_BUILTIN_TOOL_SPECS)
        async with SessionLocal() as db:
            bot = await find_bot(db, self.bot_id)
        if bot is None:
            return specs

        # 활성 스킬의 화이트리스트 (있으면)
        allowed: set[str] | None = None
        if self.state.active_skill:
            skill = next((s for s in bot.skills if s.name == self.state.active_skill), None)
            if skill and skill.allowed_tool_names:
                allowed = set(skill.allowed_tool_names)

        for t in bot.tools:
            if not t.is_enabled:
                continue
            if allowed is not None and t.name not in allowed:
                continue  # 스킬에서 허용 안 한 도구
            # 이름 충돌 방지: DB tool이 builtin과 같은 이름이면 DB 우선 (override 의도일 수 있음)
            specs = [s for s in specs if s.name != t.name]
            specs.append(ToolSpec(
                name=t.name,
                description=t.description or "",
                parameters_schema=_params_to_json_schema(t.parameters or []),
            ))
        return specs

    async def _llm_generate_with_trace(
        self, turn_id: int, span_name: str,
        *, system_prompt: str, user_text: str, model: str,
        history: list[ChatMessage], tools: list[ToolSpec],
    ):
        """generate 호출을 tracer span으로 감싼다. 실패 시 None 반환 + WS error 송신."""
        llm_id, llm_start = await self._tracer.start(
            span_name, "llm", parent_id=turn_id,
            input={"system_prompt": system_prompt, "user_text": user_text, "model": model,
                   "history": [{"role": h.role, "text": h.text} for h in history],
                   "tools_count": len(tools)},
        )
        try:
            response = await self.llm.generate(
                system_prompt=system_prompt, user_text=user_text, model=model,
                history=history, tools=tools,
                thinking_budget=self._thinking_budget(),
            )
            await self._tracer.end(
                llm_id, llm_start,
                output=response.text or (f"<tool_call: {response.tool_call.name}>" if response.tool_call else ""),
                meta={"model": model, "tool_call": response.tool_call.name if response.tool_call else None},
            )
            return response
        except Exception as e:
            await self._tracer.end(llm_id, llm_start, error=str(e))
            logger.exception("LLM error", error_type=type(e).__name__)
            await self.send_json({"type": "error", "where": "llm", "message": str(e)})
            await self.set_state("idle")
            return None

    async def _llm_continue_with_trace(
        self, turn_id: int, span_name: str,
        *, system_prompt: str, history: list[ChatMessage],
        prior_model_content, tool_name: str, tool_result, model: str,
        tools: list[ToolSpec],
    ):
        llm_id, llm_start = await self._tracer.start(
            span_name, "llm", parent_id=turn_id,
            input={"system_prompt": system_prompt, "tool_name": tool_name, "model": model,
                   "tools_count": len(tools)},
        )
        try:
            response = await self.llm.continue_after_tool(
                system_prompt=system_prompt, history=history,
                prior_model_content=prior_model_content,
                tool_name=tool_name, tool_result=tool_result, model=model, tools=tools,
                thinking_budget=self._thinking_budget(),
            )
            await self._tracer.end(
                llm_id, llm_start,
                output=response.text or (f"<tool_call: {response.tool_call.name}>" if response.tool_call else ""),
                meta={"model": model, "tool_call": response.tool_call.name if response.tool_call else None},
            )
            return response
        except Exception as e:
            await self._tracer.end(llm_id, llm_start, error=str(e))
            logger.exception("LLM continue_after_tool error", error_type=type(e).__name__)
            await self.send_json({"type": "error", "where": "llm", "message": str(e)})
            await self.set_state("idle")
            return None

    async def _execute_tool_for_loop(
        self, tool_name: str, args: dict, runtime, turn_id: int | None,
    ) -> tuple[object, bool]:
        """native tool_call 실행. (result, terminating) 반환.

        terminating=True면 턴 종료 (end_call/handover/transfer_to_agent — 세션이 끝났거나 봇이 바뀜).
        그 외 result는 LLM에 다시 주입되어 자연어 응답으로 이어진다.
        """
        # builtin
        if tool_name == "end_call":
            await self._record_tool_invocation(tool_name, args, result={"signal": "end_call"})
            await self.close(reason="bot_end_call")
            return None, True
        if tool_name in ("transfer_to_specialist", "handover_to_human"):
            await self._record_tool_invocation(tool_name, args, result={"signal": "handover"})
            await self.send_json({"type": "handover", "args": args})
            return None, True
        if tool_name == "transfer_to_agent":
            target_id = args.get("target_bot_id")
            reason = args.get("reason", "")
            async with SessionLocal() as db:
                target_bot = await db.get(models.Bot, target_id) if target_id else None
                target_name = target_bot.name if target_bot else None
                target_bot_id = target_bot.id if target_bot else None
            await self._record_tool_invocation(
                tool_name, args,
                result={"signal": "transfer_to_agent", "target_bot_id": target_id, "ok": bool(target_bot)},
            )
            if not target_bot:
                await self.send_json({"type": "error", "where": "transfer_to_agent", "message": f"target bot {target_id} not found"})
                return None, True
            # AICC-908 — 컨텍스트 유실 0:
            #   state.var_ctx (system+dynamic+extracted), state.transcripts, DB Transcript 모두 그대로 유지.
            #   bot_id만 교체하고 build_runtime을 새 봇으로 다시 호출 → system_prompt만 sub 봇 페르소나로 갱신.
            #   _build_history는 session_id 기반 DB 쿼리라 sub 봇에서도 동일 history 조회 가능.
            silent = await self._membership_silent_transfer(target_id)
            prev_bot_id = self.bot_id
            # self.bot_id + ContextVar(_bot_id_ctx) 동시 갱신 — 이후 logger.event 가 sub bot 으로 라벨링.
            self._switch_bot(target_bot_id)
            # bot_id 변경 후 CallbotAgent 캐시 리로드 — dtmf_map / idle / TTS rate·pitch /
            # thinking_budget 등 봇별 설정이 stale 채로 남으면 인계 후에도 이전 봇 동작.
            self._callbot_settings = await self._load_callbot_settings()
            self.state.active_skill = None
            self.state.auto_context = {}
            logger.event(
                "call.transfer",
                from_bot_id=prev_bot_id,
                to_bot_id=target_bot_id,
                target_name=target_name,
                reason=reason or None,
                silent=silent,
                via="tool",
            )
            await self.send_json({
                "type": "transfer_to_agent", "target_bot_id": target_id,
                "target_name": target_name, "reason": reason, "silent": silent,
            })
            async with SessionLocal() as db:
                new_runtime, new_skill = await build_runtime(db, self.bot_id, None, variables=self._all_vars())
            self.state.active_skill = new_skill
            if not silent:
                handover_line = f"네, {target_name}로 안내해드릴게요." if reason else "에이전트 전환했습니다."
                await self._save_transcript("assistant", handover_line)
                await self.send_json({"type": "transcript", "role": "assistant", "text": handover_line})
                await self._speak(handover_line, new_runtime.voice, new_runtime.language)
            return None, True

        # DB tool — 자체 세션으로 Tool + Bot 한 번에 로드하고 즉시 close (이후 task 와 격리)
        import os
        import re
        async with SessionLocal() as db:
            tool_stmt = (
                select(models.Tool)
                .where(models.Tool.bot_id == self.bot_id, models.Tool.name == tool_name)
            )
            tool = (await db.execute(tool_stmt)).scalar_one_or_none()
            bot = await db.get(models.Bot, self.bot_id)
            bot_env = (bot.env_vars if bot and bot.env_vars else {}) or {}
        if tool is None:
            return await self._execute_mcp_for_loop(tool_name, args, turn_id)

        await self.send_json({"type": "tool_call", "name": tool_name, "args": args})

        # 도구별 "실행 중 안내 메시지" — Tool.settings.running_message_enabled가 True면
        # running_message를 TTS로 발화 (도구 실행 전). 빈 메시지면 skip.
        # callbot_v0 흡수 — LLM stalling 금지 + 시스템이 도구별로 자연어 안내.
        tsettings = tool.settings or {}
        if tsettings.get("running_message_enabled"):
            msg = (tsettings.get("running_message") or "").strip()
            if msg:
                msg_resolved = self.state.var_ctx.resolve(msg)
                stall_id, stall_start = await self._tracer.start(
                    "tts.tool_stall", "tts", parent_id=turn_id,
                    input={"text": msg_resolved, "tool": tool_name},
                )
                try:
                    await self._save_transcript("assistant", msg_resolved)
                    await self.send_json({"type": "transcript", "role": "assistant", "text": msg_resolved})
                    await self._speak(msg_resolved, runtime.voice, runtime.language)
                    await self._tracer.end(stall_id, stall_start, meta={"chars": len(msg_resolved)})
                except Exception as e:
                    await self._tracer.end(stall_id, stall_start, error=str(e))

        env: dict[str, str] = {}
        ref_text = (tool.code or "") + " " + str(tool.settings or {})
        for m in re.finditer(r"\{\{(\w+)\}\}", ref_text):
            k = m.group(1)
            env[k] = bot_env.get(k) or os.environ.get(k, "")

        tool_trace_id, tool_trace_start = await self._tracer.start(
            f"tool: {tool_name}", "tool", parent_id=turn_id,
            input={"name": tool_name, "args": args, "type": tool.type},
        )
        result = await execute_tool(tool, args, env)
        await self._tracer.end(
            tool_trace_id, tool_trace_start,
            output=str(result.result) if result.ok else None,
            meta={"duration_ms": result.duration_ms, "ok": result.ok},
            error=result.error,
        )
        await self._record_tool_invocation(
            tool_name, args, result=result.result if result.ok else None,
            error=result.error, duration_ms=result.duration_ms,
        )
        await self.send_json({
            "type": "tool_result", "name": tool_name, "ok": result.ok,
            "result": result.result if result.ok else None,
            "error": result.error, "duration_ms": result.duration_ms,
        })
        if result.ok:
            return result.result, False
        return {"error": result.error or "unknown_error"}, False

    async def _execute_mcp_for_loop(
        self, tool_name: str, args: dict, turn_id: int | None,
    ) -> tuple[object, bool]:
        """MCP 서버 도구 native 실행 — 결과를 LLM에 주입할 수 있게 반환."""
        from . import mcp_client
        srv_stmt = (
            select(models.MCPServer)
            .where(models.MCPServer.bot_id == self.bot_id, models.MCPServer.is_enabled.is_(True))
        )
        async with SessionLocal() as db:
            servers = list((await db.execute(srv_stmt)).scalars().all())
        match = None
        for srv in servers:
            for mt in (srv.discovered_tools or []):
                if mt.get("name") == tool_name:
                    match = srv
                    break
            if match:
                break
        if not match:
            await self.send_json({"type": "error", "where": "tool", "message": f"unknown tool: {tool_name}"})
            return {"error": f"unknown tool: {tool_name}"}, False

        await self.send_json({"type": "tool_call", "name": tool_name, "args": args, "via": f"mcp:{match.name}"})
        tid, ts = await self._tracer.start(
            f"mcp_tool: {tool_name}", "tool", parent_id=turn_id,
            input={"name": tool_name, "args": args, "mcp_server": match.name, "base_url": match.base_url},
        )
        result = await mcp_client.call_tool(
            match.base_url, match.mcp_tenant_id, tool_name, args, match.auth_header,
        )
        await self._tracer.end(
            tid, ts,
            output=str(result.result) if result.ok else None,
            meta={"duration_ms": result.duration_ms, "ok": result.ok, "via": "mcp"},
            error=result.error,
        )
        await self._record_tool_invocation(
            tool_name, args, result=result.result if result.ok else None,
            error=result.error, duration_ms=result.duration_ms,
        )
        await self.send_json({
            "type": "tool_result", "name": tool_name, "ok": result.ok,
            "result": result.result if result.ok else None,
            "error": result.error, "duration_ms": result.duration_ms, "via": "mcp",
        })
        if result.ok:
            return result.result, False
        return {"error": result.error or "unknown_error"}, False

    # ---------- 레거시 _handle_tool_signal — global_rule + DTMF transfer_to_agent 진입점 ----------

    async def _handle_tool_signal(
        self, tool_name: str, args: dict, runtime, turn_id: int | None = None,
        *, via: str = "global_rule",
    ) -> None:
        """transfer_to_agent 등의 builtin 시그널 핸들러. via 는 logger.event 라벨링용
        (예: "global_rule" / "dtmf"). 호출처가 명시 안 하면 기본 "global_rule".
        """
        # builtin 단축 처리 (DB에 없어도 동작하도록)
        if tool_name in ("end_call",):
            await self._record_tool_invocation(tool_name, args, result={"signal": "end_call"})
            await self.close(reason="bot_end_call")
            return
        if tool_name in ("transfer_to_specialist", "handover_to_human"):
            await self._record_tool_invocation(tool_name, args, result={"signal": "handover"})
            await self.send_json({"type": "handover", "args": args})
            return
        if tool_name == "transfer_to_agent":
            # 허브-앤-스포크: 같은 통화 세션 안에서 봇 컨텍스트 스왑
            target_id = args.get("target_bot_id")
            reason = args.get("reason", "")
            async with SessionLocal() as db:
                target_bot = await db.get(models.Bot, target_id) if target_id else None
                target_name = target_bot.name if target_bot else None
                target_bot_id = target_bot.id if target_bot else None
            await self._record_tool_invocation(
                tool_name, args,
                result={"signal": "transfer_to_agent", "target_bot_id": target_id, "ok": bool(target_bot)},
            )
            if not target_bot:
                await self.send_json({"type": "error", "where": "transfer_to_agent", "message": f"target bot {target_id} not found"})
                return
            # AICC-908 — silent_transfer 멤버십 플래그 적용 (자세한 의미는 _execute_tool_for_loop 분기 참조)
            silent = await self._membership_silent_transfer(target_id)
            prev_bot_id = self.bot_id
            # self.bot_id + ContextVar(_bot_id_ctx) 동시 갱신 — 이후 logger.event 가 sub bot 으로 라벨링.
            self._switch_bot(target_bot_id)
            # bot_id 변경 후 CallbotAgent 캐시 리로드 — dtmf_map / idle / TTS rate·pitch /
            # thinking_budget 등 봇별 설정이 stale 채로 남으면 인계 후에도 이전 봇 동작.
            self._callbot_settings = await self._load_callbot_settings()
            self.state.active_skill = None
            self.state.auto_context = {}
            logger.event(
                "call.transfer",
                from_bot_id=prev_bot_id,
                to_bot_id=target_bot_id,
                target_name=target_name,
                reason=reason or None,
                silent=silent,
                via=via,
            )
            await self.send_json({
                "type": "transfer_to_agent", "target_bot_id": target_id,
                "target_name": target_name, "reason": reason, "silent": silent,
            })
            async with SessionLocal() as db:
                new_runtime, new_skill = await build_runtime(db, self.bot_id, None, variables=self._all_vars())
            self.state.active_skill = new_skill
            if not silent:
                handover_line = f"네, {target_name}로 안내해드릴게요." if reason else "에이전트 전환했습니다."
                await self._save_transcript("assistant", handover_line)
                await self.send_json({"type": "transcript", "role": "assistant", "text": handover_line})
                await self._speak(handover_line, new_runtime.voice, new_runtime.language)
            return

        # DB에 등록된 도구 + Bot env 를 자체 세션으로 로드 (이후 task 들과 격리)
        import os
        import re
        async with SessionLocal() as db:
            tool_stmt = (
                select(models.Tool)
                .where(models.Tool.bot_id == self.bot_id, models.Tool.name == tool_name)
            )
            tool = (await db.execute(tool_stmt)).scalar_one_or_none()
            bot = await db.get(models.Bot, self.bot_id) if tool else None
            bot_env = (bot.env_vars if bot and bot.env_vars else {}) or {}
        # DB에 없으면 MCP 서버에서 찾아 proxy
        if not tool:
            await self._handle_mcp_tool(tool_name, args, runtime, turn_id)
            return

        # VC 치환 — LLM이 {{customer_name}} 같은 토큰을 args에 넣으면 실 값으로
        args = _resolve_args_deep(args, self.state.var_ctx)
        await self.send_json({"type": "tool_call", "name": tool_name, "args": args})

        # env: 봇별 env_vars 우선 → 없으면 OS env fallback
        env: dict[str, str] = {}
        # 도구가 참조하는 모든 placeholder 자동 수집
        ref_text = (tool.code or "") + " " + str(tool.settings or {})
        for m in re.finditer(r"\{\{(\w+)\}\}", ref_text):
            k = m.group(1)
            env[k] = bot_env.get(k) or os.environ.get(k, "")

        tool_trace_id, tool_trace_start = await self._tracer.start(
            f"tool: {tool_name}", "tool", parent_id=turn_id,
            input={"name": tool_name, "args": args, "type": tool.type},
        )
        result = await execute_tool(tool, args, env)
        await self._tracer.end(
            tool_trace_id, tool_trace_start,
            output=str(result.result) if result.ok else None,
            meta={"duration_ms": result.duration_ms, "ok": result.ok},
            error=result.error,
        )
        await self._record_tool_invocation(
            tool_name, args,
            result=result.result if result.ok else None,
            error=result.error,
            duration_ms=result.duration_ms,
        )

        await self.send_json({
            "type": "tool_result",
            "name": tool_name,
            "ok": result.ok,
            "result": result.result if result.ok else None,
            "error": result.error,
            "duration_ms": result.duration_ms,
        })

        # tool-use loop (1회): 결과를 LLM에 다시 보내 자연어 응답 생성
        if result.ok and result.result is not None:
            followup_user = (
                f"방금 도구 '{tool_name}'를 호출했고 결과는 다음과 같다:\n"
                f"{result.result}\n\n"
                f"이 결과를 바탕으로 사용자에게 1~2문장 자연어로 답하라. "
                f"도구 호출 JSON은 출력하지 말 것."
            )
            followup_history = await self._build_history()  # tool 호출 시점의 누적 history 포함
            llm2_id, llm2_start = await self._tracer.start(
                "llm.followup", "llm", parent_id=turn_id,
                input={"system_prompt": runtime.system_prompt, "user_text": followup_user, "model": runtime.llm_model},
            )
            try:
                followup = await self.llm.generate(
                    system_prompt=self.state.var_ctx.resolve(runtime.system_prompt),
                    user_text=followup_user,
                    model=runtime.llm_model,
                    history=followup_history,
                    thinking_budget=self._thinking_budget(),
                )
                await self._tracer.end(llm2_id, llm2_start, output=followup, meta={"model": runtime.llm_model})
                body2, _ = parse_signal_and_strip(followup)
                if body2:
                    await self._save_transcript("assistant", body2)
                    await self.send_json({"type": "transcript", "role": "assistant", "text": body2})
                    tts2_id, tts2_start = await self._tracer.start(
                        "tts.followup", "tts", parent_id=turn_id,
                        input={"text": body2, "voice": runtime.voice, "language": runtime.language},
                    )
                    try:
                        await self._speak(body2, runtime.voice, runtime.language)
                        await self._tracer.end(tts2_id, tts2_start, meta={"chars": len(body2)})
                    except Exception as te:
                        await self._tracer.end(tts2_id, tts2_start, error=str(te))
                        raise
            except Exception as e:
                await self._tracer.end(llm2_id, llm2_start, error=str(e))
                logger.warning(
                    "tool followup failed",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

    async def _record_tool_invocation(
        self, name: str, args: dict, result=None, error: str | None = None, duration_ms: int = 0
    ) -> None:
        try:
            inv = models.ToolInvocation(
                session_id=self.session_id,
                tool_name=name,
                args=args or {},
                result=str(result) if result is not None else None,
                error=error,
                duration_ms=duration_ms,
            )
            async with SessionLocal() as db:
                db.add(inv)
                await db.commit()
        except Exception as e:
            logger.warning(
                "record tool invocation failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    async def _handle_mcp_tool(self, tool_name: str, args: dict, runtime, turn_id: int | None) -> None:
        """LLM이 호출한 이름이 DB Tool에 없으면 MCP 서버들 중 매칭되는 곳으로 proxy."""
        from . import mcp_client
        srv_stmt = (
            select(models.MCPServer)
            .where(models.MCPServer.bot_id == self.bot_id, models.MCPServer.is_enabled.is_(True))
        )
        async with SessionLocal() as db:
            servers = list((await db.execute(srv_stmt)).scalars().all())
        match = None
        for srv in servers:
            for mt in (srv.discovered_tools or []):
                if mt.get("name") == tool_name:
                    match = srv
                    break
            if match:
                break
        if not match:
            await self.send_json({"type": "error", "where": "tool", "message": f"unknown tool: {tool_name}"})
            return

        # VC 치환 — MCP 도구 args도 동일하게
        args = _resolve_args_deep(args, self.state.var_ctx)
        await self.send_json({"type": "tool_call", "name": tool_name, "args": args, "via": f"mcp:{match.name}"})
        tid, ts = await self._tracer.start(
            f"mcp_tool: {tool_name}", "tool", parent_id=turn_id,
            input={"name": tool_name, "args": args, "mcp_server": match.name, "base_url": match.base_url},
        )
        result = await mcp_client.call_tool(
            match.base_url, match.mcp_tenant_id, tool_name, args, match.auth_header,
        )
        await self._tracer.end(
            tid, ts,
            output=str(result.result) if result.ok else None,
            meta={"duration_ms": result.duration_ms, "ok": result.ok, "via": "mcp"},
            error=result.error,
        )
        await self._record_tool_invocation(
            tool_name, args,
            result=result.result if result.ok else None,
            error=result.error,
            duration_ms=result.duration_ms,
        )
        await self.send_json({
            "type": "tool_result",
            "name": tool_name,
            "ok": result.ok,
            "result": result.result if result.ok else None,
            "error": result.error,
            "duration_ms": result.duration_ms,
            "via": "mcp",
        })
        # tool-use loop: 결과를 LLM에 다시 보내 자연어 응답
        if result.ok and result.result is not None:
            followup_user = (
                f"방금 MCP 도구 '{tool_name}'를 호출했고 결과는 다음과 같다:\n"
                f"{result.result}\n\n이 결과를 바탕으로 1~2문장 자연어로 답하라."
            )
            followup_history = await self._build_history()
            llm2_id, llm2_start = await self._tracer.start(
                "llm.followup", "llm", parent_id=turn_id,
                input={"system_prompt": runtime.system_prompt, "user_text": followup_user, "model": runtime.llm_model},
            )
            try:
                followup = await self.llm.generate(
                    system_prompt=self.state.var_ctx.resolve(runtime.system_prompt),
                    user_text=followup_user,
                    model=runtime.llm_model,
                    history=followup_history,
                    thinking_budget=self._thinking_budget(),
                )
                await self._tracer.end(llm2_id, llm2_start, output=followup, meta={"model": runtime.llm_model})
                body2, _ = parse_signal_and_strip(followup)
                if body2:
                    await self._save_transcript("assistant", body2)
                    await self.send_json({"type": "transcript", "role": "assistant", "text": body2})
                    tts2_id, tts2_start = await self._tracer.start(
                        "tts.followup", "tts", parent_id=turn_id,
                        input={"text": body2, "voice": runtime.voice, "language": runtime.language},
                    )
                    try:
                        await self._speak(body2, runtime.voice, runtime.language)
                        await self._tracer.end(tts2_id, tts2_start, meta={"chars": len(body2)})
                    except Exception as te:
                        await self._tracer.end(tts2_id, tts2_start, error=str(te))
                        raise
            except Exception as e:
                await self._tracer.end(llm2_id, llm2_start, error=str(e))
                logger.warning(
                    "MCP tool followup failed",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

    async def _run_auto_calls(self, trigger: str) -> None:
        """auto_call_on=trigger 인 모든 도구를 자동 실행 (args 없음).
        결과는 self.state에 누적되어 다음 build_runtime에서 컨텍스트로 주입."""
        import os
        import re
        tools_stmt = (
            select(models.Tool)
            .where(
                models.Tool.bot_id == self.bot_id,
                models.Tool.is_enabled.is_(True),
                models.Tool.auto_call_on == trigger,
            )
        )
        async with SessionLocal() as db:
            tools = list((await db.execute(tools_stmt)).scalars().all())
            if not tools:
                return
            bot = await db.get(models.Bot, self.bot_id)
            bot_env = (bot.env_vars if bot and bot.env_vars else {}) or {}
        for tool in tools:
            ref_text = (tool.code or "") + " " + str(tool.settings or {})
            env: dict[str, str] = {}
            for m in re.finditer(r"\{\{(\w+)\}\}", ref_text):
                k = m.group(1)
                env[k] = bot_env.get(k) or os.environ.get(k, "")
            args = (tool.settings or {}).get("default_args") or {}
            # VC 치환 — auto_call_on session_start 도구가 dynamic 변수 (예: reservationNo) 활용 가능
            args = _resolve_args_deep(args, self.state.var_ctx)

            tid, ts = await self._tracer.start(
                f"auto_call: {tool.name}", "tool", input={"name": tool.name, "args": args, "trigger": trigger}
            )
            result = await execute_tool(tool, args, env)
            await self._tracer.end(
                tid, ts,
                output=str(result.result) if result.ok else None,
                meta={"duration_ms": result.duration_ms, "ok": result.ok, "auto": True},
                error=result.error,
            )
            await self._record_tool_invocation(
                tool.name, args,
                result=result.result if result.ok else None,
                error=result.error,
                duration_ms=result.duration_ms,
            )
            # state.auto_context에 누적 (build_runtime이 시스템 프롬프트에 inject)
            ctx = getattr(self.state, "auto_context", None) or {}
            ctx[tool.name] = result.result if result.ok else {"error": result.error}
            self.state.auto_context = ctx  # type: ignore
            # settings.merge_result_into_vars=True 면 결과 dict를 var_ctx.dynamic에 머지 (callbot_v0 패턴).
            # 결과가 dict + 값이 모두 str이어야 안전하게 머지.
            if result.ok and (tool.settings or {}).get("merge_result_into_vars") and isinstance(result.result, dict):
                merged = {str(k): str(v) for k, v in result.result.items() if v}
                if merged:
                    self.state.var_ctx.merge_dynamic(merged)
            await self.send_json({
                "type": "auto_call",
                "name": tool.name,
                "ok": result.ok,
                "result": result.result if result.ok else None,
                "error": result.error,
            })

    async def _run_post_call_analysis(self, model: str) -> None:
        try:
            await analyze_session(self.session_id, self.llm, model)
        except Exception as e:
            logger.warning(
                "post-call analysis task failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    async def _speak(self, text: str, voice: str, language: str) -> bool:
        """봇 발화. 반환값: True=PCM 끝까지 송출 완료, False=speech_task 가 barge-in 으로 cancel.

        주의: 외부 task (_stt_task 등) 가 cancelling 중이면 CancelledError 를 그대로 propagate —
        호출자(`_run_streaming_turn`/`_handle_user_final`) 가 partial sentences 를 save 한 뒤
        cancel 을 위로 전달할 수 있도록. 과거에는 무조건 swallow 해서 외부 cancel 신호가 사라지고
        LLM 스트림 루프가 다음 sentence 를 계속 emit 하는 버그가 있었음.
        """
        import time as _time
        self.state.last_speak_start_t = _time.monotonic()

        # (d) AICC-910 — TTS 텍스트 치환 (tts_pronunciation)
        text_to_speak = self._tts_apply_pronunciation(text)
        # (e) AICC-910 — speaking_rate / pitch 전달
        rate, pitch = self._tts_rate_pitch()

        async def speak_task():
            try:
                async for pcm in self.tts.synthesize(
                    text=text_to_speak,
                    language=language,
                    voice=voice,
                    sample_rate=self.sample_rate,
                    speaking_rate=rate,
                    pitch=pitch,
                ):
                    if self._closed:
                        return
                    # TTFF: turn의 첫 PCM 송신 시점 기록 (이미 기록됐으면 skip)
                    if self.state.turn_t0 is not None and self.state.first_audio_t is None:
                        self.state.first_audio_t = _time.monotonic()
                    await self.send_bytes(pcm)
            except asyncio.CancelledError:
                # propagate — speech_task 가 CancelledError 로 종료해야 outer `await speech_task` 가
                # 예외를 받음. `return` 으로 삼키면 task 가 정상 종료로 보여 commit 판정 어긋남.
                # 보고: CodeRabbit PR #13 (https://github.com/aicx-kr/aicx-callbot/pull/13).
                raise
            except Exception as e:
                logger.exception("TTS error", error_type=type(e).__name__)
                await self.send_json({"type": "error", "where": "tts", "message": str(e)})

        # race 방지: speech_task 를 set_state("speaking") 보다 먼저 할당.
        # 순서가 거꾸로면 set_state 의 await(send_json) 사이에 사용자 PCM 이 도착해
        # _on_speech_start 가 speech_task=None 으로 보고 barge-in cancel 분기를 놓침.
        # 발견 경로: e2e_voice_sim.py 의 barge_in 시나리오, 2026-05-15.
        self.state.speech_task = asyncio.create_task(speak_task())
        await self.set_state("speaking")
        completed = True
        try:
            await self.state.speech_task
        except asyncio.CancelledError:
            completed = False
            # 외부 task 가 cancel 중인 경우엔 신호를 위로 전파 — 호출자에서 partial save 후 raise.
            # asyncio.current_task().cancelling() 은 Python 3.11+ — 미만 환경은 보수적으로 그대로 propagate.
            current = asyncio.current_task()
            outer_cancelling = getattr(current, "cancelling", lambda: 0)() > 0 if current else False
            if outer_cancelling:
                raise
        finally:
            # 봇 발화 종료 시각 기록 — _on_speech_start의 echo grace 기준점.
            # cancel(barge-in)된 경우에도 잔향 가능성 있어 동일하게 기록.
            self.state.last_speak_end_t = _time.monotonic()
            # (b) AICC-910 — 봇 발화 종료도 침묵 카운트 기준점 (사용자 발화가 더 늦은 경우만 갱신)
            # 테스트가 __init__ 우회하는 경우 안전 가드.
            last = getattr(self, "_last_activity_t", 0.0)
            if last < self.state.last_speak_end_t:
                self._last_activity_t = self.state.last_speak_end_t
        return completed

    async def _save_transcript(self, role: str, text: str) -> None:
        t = models.Transcript(session_id=self.session_id, role=role, text=text, is_final=True)
        async with SessionLocal() as db:
            db.add(t)
            sess = await db.get(models.CallSession, self.session_id)
            if sess and sess.status == "pending":
                sess.status = "active"
            await db.commit()
