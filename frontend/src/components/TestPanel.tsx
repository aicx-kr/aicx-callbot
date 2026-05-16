'use client';

import { useEffect, useRef, useState } from 'react';
import { Mic, Square, Send, Bot as BotIcon, User as UserIcon, Loader2, Wrench, ChevronDown, ChevronRight, CheckCircle2, XCircle } from 'lucide-react';
import clsx from 'clsx';
import { api, backendWsUrl } from '@/lib/api';
import type { Bot } from '@/lib/types';

type CallState = 'idle' | 'listening' | 'thinking' | 'speaking';
type Mode = 'browser' | 'gcp' | 'text';

interface ToolInvocation {
  name: string;
  args?: unknown;
  via?: string;
  result?: unknown;
  error?: string | null;
  ok?: boolean;
  duration_ms?: number;
  pending: boolean;
}

interface Bubble {
  role: 'user' | 'assistant' | 'system' | 'tool';
  text: string;
  interim?: boolean;
  tool?: ToolInvocation;
}

export function TestPanel({ bot, voiceModeAvailable }: { bot: Bot; voiceModeAvailable: boolean }) {
  const [running, setRunning] = useState(false);
  const [state, setState] = useState<CallState>('idle');
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [mode, setMode] = useState<Mode>('text');
  const [text, setText] = useState('');
  const [sessionId, setSessionId] = useState<number | null>(null);
  // dynamic 변수 입력 (key=value 줄별 — 예: "customer_name=홍길동\nphone=010-...")
  const [varsRaw, setVarsRaw] = useState('');
  const [showVars, setShowVars] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const playbackTimeRef = useRef(0);
  // barge-in 시 audio queue flush 용 — playPCM 으로 schedule 한 source 들 추적
  const playbackSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const recogRef = useRef<{ stop: () => void; start: () => void; _stopped?: boolean; _paused?: boolean } | null>(null);
  const modeRef = useRef<Mode>('text');
  const stateRef = useRef<CallState>('idle');
  const blockUntilRef = useRef(0); // SR 결과 무시할 시각 (ms epoch)
  const conversationRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 마운트 후 결정 (SSR mismatch 방지). 우선순위: GCP(실 운영 동등) → 브라우저 → 텍스트.
    if (voiceModeAvailable) setMode('gcp');
    else if (hasBrowserSpeech()) setMode('browser');
  }, [voiceModeAvailable]);

  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { stateRef.current = state; }, [state]);

  // SR은 한 번 시작 후 stop/start 안 함 (state guard + blockUntilRef로만 echo 차단)
  // pause/resume이 꼬여서 SR이 영구 정지되는 버그 회피

  useEffect(() => {
    conversationRef.current?.scrollTo({ top: conversationRef.current.scrollHeight });
  }, [bubbles, state]);

  useEffect(() => () => stopCall(), []); // unmount cleanup

  function addBubble(b: Bubble) {
    setBubbles((arr) => [...arr, b]);
  }

  function replaceInterim(role: Bubble['role'], text: string, isFinal: boolean) {
    setBubbles((arr) => {
      const last = arr[arr.length - 1];
      if (last && last.interim && last.role === role) {
        const next = [...arr];
        next[next.length - 1] = { role, text, interim: !isFinal };
        return next;
      }
      return [...arr, { role, text, interim: !isFinal }];
    });
  }

  function parseVars(raw: string): Record<string, string> {
    const out: Record<string, string> = {};
    for (const line of raw.split('\n')) {
      const eq = line.indexOf('=');
      if (eq <= 0) continue;
      const k = line.slice(0, eq).trim();
      const v = line.slice(eq + 1);
      if (k) out[k] = v;
    }
    return out;
  }

  async function startCall() {
    try {
      setBubbles([]);
      const vars = parseVars(varsRaw);
      const resp = await api.post<{ session_id: number; room_id: string; voice_mode_available: boolean }>(
        '/api/calls/start',
        { bot_id: bot.id, vars: Object.keys(vars).length > 0 ? vars : undefined },
      );
      setSessionId(resp.session_id);

      const ws = new WebSocket(`${backendWsUrl()}/ws/calls/${resp.session_id}`);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = async () => {
        setRunning(true);
        if (mode === 'gcp' && voiceModeAvailable) {
          try { await openMicGcp(ws); }
          catch (e) { addBubble({ role: 'system', text: `마이크 열기 실패: ${(e as Error).message}` }); }
        } else if (mode === 'browser') {
          // 권한 받고 SR 즉시 시작
          try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            stream.getTracks().forEach((t) => t.stop());
          } catch (e) {
            addBubble({ role: 'system', text: `마이크 권한 거부됨: ${(e as Error).message}` });
            return;
          }
          try { startBrowserMic(ws); }
          catch (e) { addBubble({ role: 'system', text: `STT 시작 실패: ${(e as Error).message}` }); }
        }
      };
      ws.onmessage = (ev) => {
        if (typeof ev.data === 'string') handleJson(JSON.parse(ev.data));
        // 브라우저 모드에서는 백엔드 TTS PCM 무시 (speechSynthesis와 이중 재생/삐 소리 방지)
        else if (modeRef.current !== 'browser') playPCM(new Int16Array(ev.data));
      };
      ws.onclose = () => onClosed();
      ws.onerror = () => onClosed();
    } catch (e) {
      addBubble({ role: 'system', text: `시작 실패: ${(e as Error).message}` });
    }
  }

  function handleJson(msg: { type: string; [k: string]: unknown }) {
    switch (msg.type) {
      case 'state':
        setState((msg.value as CallState) || 'idle');
        break;
      case 'transcript': {
        const role = msg.role as 'user' | 'assistant';
        const txt = (msg.text as string) || '';
        const isFinal = (msg.is_final ?? true) as boolean;
        replaceInterim(role, txt, isFinal);
        if (mode === 'browser' && role === 'assistant' && isFinal) {
          speakBrowser(txt, bot.language || 'ko-KR');
        }
        break;
      }
      case 'skill':
        addBubble({ role: 'system', text: `🔀 스킬 전환 → ${msg.name}` });
        break;
      case 'barge_in': {
        const inGreeting = Boolean(msg.in_greeting);
        const elapsed = typeof msg.elapsed_ms === 'number' ? `${msg.elapsed_ms}ms 발화 후` : '';
        const label = inGreeting ? '(인사말 중)' : '';
        addBubble({
          role: 'system',
          text: `⚡ 끼어들기 감지 ${label} ${elapsed}`.replace(/\s+/g, ' ').trim(),
        });
        break;
      }
      case 'stop_playback':
        flushPlayback();
        break;
      case 'tool_call':
        addBubble({
          role: 'tool',
          text: '',
          tool: { name: String(msg.name), args: msg.args, via: msg.via as string | undefined, pending: true },
        });
        break;
      case 'tool_result': {
        const name = String(msg.name);
        setBubbles((arr) => {
          for (let i = arr.length - 1; i >= 0; i--) {
            const b = arr[i];
            if (b.role === 'tool' && b.tool?.pending && b.tool.name === name) {
              const next = [...arr];
              next[i] = {
                ...b,
                tool: {
                  ...b.tool,
                  result: msg.result,
                  error: msg.error as string | null,
                  ok: msg.ok as boolean,
                  duration_ms: msg.duration_ms as number,
                  pending: false,
                },
              };
              return next;
            }
          }
          // 페어 못 찾으면(드물게) — 결과 단독 bubble
          return [
            ...arr,
            {
              role: 'tool',
              text: '',
              tool: {
                name,
                result: msg.result,
                error: msg.error as string | null,
                ok: msg.ok as boolean,
                duration_ms: msg.duration_ms as number,
                via: msg.via as string | undefined,
                pending: false,
              },
            },
          ];
        });
        break;
      }
      case 'handover':
        addBubble({ role: 'system', text: '👤 상담사 전환' });
        break;
      case 'speak_end': {
        // 서버가 turn 발화 PCM 송출을 마쳤음을 알림. 클라는 playbackTimeRef.current (PCM 큐의 끝
        // 시각, AudioContext 시계) 기준으로 실제 재생 완료 시점을 추산해 playback_done 회신.
        // 서버는 그 시점에 idle 타이머 baseline 갱신 — 클라 버퍼 잔여 재생 시간 만큼 일찍 prompt 가
        // 발화되던 버그를 해소.
        const id = String(msg.id || '');
        if (!id) break;
        const ws = wsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) break;
        const ctx = audioCtxRef.current;
        // browser 모드는 백엔드 TTS PCM 을 무시 (speechSynthesis 사용) — 즉시 ack 로 처리.
        if (!ctx || modeRef.current === 'browser') {
          ws.send(JSON.stringify({ type: 'playback_done', id }));
          break;
        }
        const remainingMs = Math.max(0, (playbackTimeRef.current - ctx.currentTime) * 1000);
        setTimeout(() => {
          const s = wsRef.current;
          if (s && s.readyState === WebSocket.OPEN) {
            s.send(JSON.stringify({ type: 'playback_done', id }));
          }
        }, remainingMs);
        break;
      }
      case 'error':
        addBubble({ role: 'system', text: `⚠ ${msg.where}: ${msg.message}` });
        break;
      case 'end':
        addBubble({ role: 'system', text: `통화 종료 (${msg.reason})` });
        break;
    }
  }

  async function openMicGcp(ws: WebSocket) {
    const ctx = new AudioContext({ sampleRate: 16000 });
    audioCtxRef.current = ctx;
    await ctx.audioWorklet.addModule('/audio-worklet.js');
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true },
    });
    streamRef.current = stream;
    const src = ctx.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(ctx, 'mic-capture', { processorOptions: { targetRate: 16000 } });
    node.port.onmessage = (e) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(e.data);
    };
    src.connect(node);
    micNodeRef.current = node;
  }

  function startBrowserMic(ws: WebSocket) {
    const W = window as unknown as { SpeechRecognition?: any; webkitSpeechRecognition?: any };
    const SR = W.SpeechRecognition || W.webkitSpeechRecognition;
    if (!SR) throw new Error('이 브라우저는 음성 인식 미지원 (Chrome/Edge 권장)');
    const rec = new SR();
    rec.lang = bot.language || 'ko-KR';
    rec.continuous = true;
    rec.interimResults = true;
    rec.onstart = () => console.log('[SR] started');
    let lastFinalSent = '';
    rec.onresult = (e: any) => {
      let interim = '';
      let final = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t;
        else interim += t;
      }
      // 봇 발화 중/생각 중이거나 발화 직후 잔향 시간엔 무시 (echo 차단)
      const blocked = stateRef.current === 'speaking' || stateRef.current === 'thinking'
                     || Date.now() < blockUntilRef.current;
      if (!blocked && interim) replaceInterim('user', interim, false);
      if (!blocked && final && final !== lastFinalSent) {
        lastFinalSent = final;
        replaceInterim('user', final, true);
        if (ws.readyState === WebSocket.OPEN) {
          console.log('[SR] sending:', final.trim());
          ws.send(JSON.stringify({ type: 'text', text: final.trim() }));
        }
      } else if (blocked && final) {
        console.log('[SR] echo blocked:', final.trim().slice(0, 40));
      }
    };
    rec.onerror = (e: any) => {
      if (e.error !== 'no-speech' && e.error !== 'aborted') {
        addBubble({ role: 'system', text: `STT 에러: ${e.error}` });
      }
    };
    rec.onend = () => {
      const r = recogRef.current;
      if (r && r === rec && !r._stopped) {
        // Chrome SR은 한참 안 들리면 자동 종료 — 즉시 재시작
        // 단 다른 SR로 교체됐거나 _stopped면 재시작 안 함
        setTimeout(() => {
          if (recogRef.current === rec && !rec._stopped) {
            try { rec.start(); console.log('[SR] auto-restart'); } catch {}
          }
        }, 50);
      }
    };
    try { rec.start(); console.log('[SR] started'); } catch (e) { console.warn('[SR] initial start failed', e); }
    recogRef.current = rec;
  }

  function speakBrowser(text: string, lang: string) {
    try {
      // 1) 발화 시작 전 SR 완전 중단 (echo 차단)
      abortRecognition();
      // 2) 추정 발화 시간 + 잔향 그레이스. onend에서 정확히 갱신.
      //    한국어 음절 평균 ~280ms (TTS rate 1.05 보상 후) — 이전 220은 긴 응답에서 짧음.
      const perChar = /^ko/i.test(lang) ? 280 : 100;
      const estimateMs = Math.max(2500, Math.ceil(text.length * perChar / 1.05));
      blockUntilRef.current = Date.now() + estimateMs + 800;

      const u = new SpeechSynthesisUtterance(text);
      u.lang = lang;
      u.rate = 1.05;

      // 3) 발화 끝나면 800ms 후 새 SR 인스턴스로 재시작
      let resumed = false;
      const resume = () => {
        if (resumed) return;
        resumed = true;
        console.log('[speak] done, resume SR in 800ms');
        setTimeout(() => {
          blockUntilRef.current = 0;
          const ws = wsRef.current;
          if (ws && ws.readyState === WebSocket.OPEN && modeRef.current === 'browser') {
            try { startBrowserMic(ws); } catch (e) { console.warn('SR resume failed', e); }
          }
        }, 800);
      };
      u.onend = resume;
      u.onerror = resume;
      // 4) fallback: speechSynthesis.onend가 안 올 수도 있는 Chrome 버그 대비
      setTimeout(resume, estimateMs + 1500);

      window.speechSynthesis.speak(u);
    } catch (e) {
      console.warn('speakBrowser failed', e);
    }
  }

  function abortRecognition() {
    const r = recogRef.current;
    if (!r) return;
    r._stopped = true;  // onend 핸들러가 재시작 안 하도록
    try { r.stop(); } catch {}
    try { (r as any).abort?.(); } catch {}
    recogRef.current = null;
    console.log('[SR] aborted');
  }

  function playPCM(int16: Int16Array) {
    let ctx = audioCtxRef.current;
    if (!ctx) {
      ctx = new AudioContext({ sampleRate: 16000 });
      audioCtxRef.current = ctx;
    }
    const f32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 0x8000;
    const buf = ctx.createBuffer(1, f32.length, 16000);
    buf.getChannelData(0).set(f32);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    const when = Math.max(ctx.currentTime, playbackTimeRef.current);
    src.start(when);
    playbackTimeRef.current = when + buf.duration;
    // stop_playback (barge-in) 시 즉시 중단할 수 있게 추적. 재생 끝나면 set 에서 제거.
    playbackSourcesRef.current.add(src);
    src.onended = () => playbackSourcesRef.current.delete(src);
  }

  function flushPlayback() {
    // backend 가 stop_playback 송신 — barge-in. 현재 큐에 schedule 된 PCM 즉시 중단.
    for (const src of playbackSourcesRef.current) {
      try { src.stop(); } catch {}
    }
    playbackSourcesRef.current.clear();
    playbackTimeRef.current = 0;
  }

  function sendText() {
    const t = text.trim();
    if (!t || !wsRef.current) return;
    wsRef.current.send(JSON.stringify({ type: 'text', text: t }));
    setText('');
  }

  function stopCall() {
    try { wsRef.current?.send(JSON.stringify({ type: 'end_call' })); } catch {}
    setTimeout(() => wsRef.current?.close(), 200);
    onClosed();
  }

  function onClosed() {
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch {}
    try { micNodeRef.current?.disconnect(); } catch {}
    try { audioCtxRef.current?.close(); } catch {}
    try {
      if (recogRef.current) {
        recogRef.current._stopped = true;
        recogRef.current.stop();
      }
    } catch {}
    try { window.speechSynthesis?.cancel(); } catch {}
    streamRef.current = null;
    micNodeRef.current = null;
    audioCtxRef.current = null;
    recogRef.current = null;
    playbackTimeRef.current = 0;
    playbackSourcesRef.current.clear();
    blockUntilRef.current = 0;
    setRunning(false);
    setState('idle');
  }

  return (
    <div className="flex flex-col h-full bg-white dark:bg-ink-900">
      <div className="px-4 py-3 border-b border-ink-100 dark:border-ink-700 flex items-center gap-2">
        <BotIcon className="w-4 h-4 text-violet-600 dark:text-violet-400" />
        <div className="text-sm font-semibold flex-1 dark:text-ink-100">테스트 콜</div>
        <select
          className="text-xs bg-white dark:bg-ink-800 dark:text-ink-100 border border-ink-200 dark:border-ink-600 rounded-md px-2 py-1 outline-none"
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
          disabled={running}
        >
          <option value="browser">음성 (브라우저)</option>
          <option value="gcp" disabled={!voiceModeAvailable}>음성 (GCP){!voiceModeAvailable ? ' — 키 없음' : ''}</option>
          <option value="text">텍스트</option>
        </select>
      </div>

      <div className="px-4 py-3 border-b border-ink-100 dark:border-ink-700">
        <div className="flex items-center gap-3">
          <div className={clsx(
            'w-10 h-10 rounded-full flex items-center justify-center transition-all border-2',
            state === 'idle' && 'border-ink-200 dark:border-ink-600 text-ink-400 dark:text-ink-500',
            state === 'listening' && 'border-sky-400 text-sky-600 shadow-[0_0_18px_rgba(56,189,248,0.4)]',
            state === 'thinking' && 'border-amber-400 text-amber-600 shadow-[0_0_18px_rgba(251,191,36,0.4)]',
            state === 'speaking' && 'border-emerald-400 text-emerald-600 shadow-[0_0_18px_rgba(94,234,212,0.4)]',
          )}>
            {state === 'thinking' ? <Loader2 className="w-4 h-4 animate-spin" /> : <BotIcon className="w-4 h-4" />}
          </div>
          <div className="text-sm">
            <div className={clsx(
              'font-medium transition-colors',
              state === 'listening' && 'text-sky-600 dark:text-sky-400',
              state === 'thinking' && 'text-amber-600 dark:text-amber-400',
              state === 'speaking' && 'text-emerald-600 dark:text-emerald-400',
              state === 'idle' && 'text-ink-700 dark:text-ink-100',
            )}>{stateLabel(state)}</div>
            <div className="text-xs text-ink-500 dark:text-ink-400">{sessionId ? `세션 #${sessionId}` : '미연결'}</div>
          </div>
          <div className="flex-1" />
          {!running ? (
            <button onClick={startCall} className="bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700 flex items-center gap-1.5">
              <Mic className="w-3.5 h-3.5" /> 시작
            </button>
          ) : (
            <button onClick={stopCall} className="bg-rose-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-rose-700 flex items-center gap-1.5">
              <Square className="w-3.5 h-3.5" /> 종료
            </button>
          )}
        </div>
      </div>

      <div ref={conversationRef} className="flex-1 overflow-auto scrollbar-thin px-4 py-3 space-y-2">
        {bubbles.length === 0 && (
          <div className="text-center text-ink-400 dark:text-ink-500 text-sm py-12">
            <BotIcon className="w-10 h-10 mx-auto mb-2 text-ink-200 dark:text-ink-700" />
            {mode === 'text' ? '시작 후 텍스트로 메시지' : '시작 후 마이크로 말씀하세요'}
          </div>
        )}
        {bubbles.map((b, i) => <Bubble key={i} bubble={b} />)}
      </div>

      <div className="px-4 py-3 border-t border-ink-100 dark:border-ink-700">
        <div className="flex gap-2">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendText()}
            placeholder={running ? '메시지 입력' : '먼저 시작을 누르세요'}
            disabled={!running}
            className="flex-1 text-sm px-3 py-2 border border-ink-200 dark:border-ink-600 rounded-md bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400 disabled:bg-ink-50 dark:disabled:bg-ink-800/50"
          />
          <button onClick={sendText} disabled={!running || !text.trim()} className="bg-violet-600 text-white px-3 py-2 rounded-md hover:bg-violet-700 disabled:opacity-40">
            <Send className="w-4 h-4" />
          </button>
        </div>
        <div className="text-[11px] text-ink-400 dark:text-ink-500 mt-1.5 flex items-center gap-2">
          <span className="flex-1">
            {mode === 'browser' && '브라우저 SpeechRecognition (Chrome/Edge). 한국어 자동 인식.'}
            {mode === 'gcp' && 'GCP STT/TTS — 백엔드 음성 처리. 마이크 PCM 16kHz 스트리밍.'}
            {mode === 'text' && '텍스트만 입력. LLM 응답 검증.'}
          </span>
          <button
            onClick={() => setShowVars((v) => !v)}
            className={clsx('px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wider',
              showVars ? 'bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300' : 'bg-ink-100 dark:bg-ink-700 text-ink-500 dark:text-ink-400 hover:bg-ink-200')}
            disabled={running}
            title={running ? '통화 중엔 수정 불가' : '통화 시작 시 주입할 dynamic 변수'}
          >
            VARS{Object.keys(parseVars(varsRaw)).length > 0 ? ` (${Object.keys(parseVars(varsRaw)).length})` : ''}
          </button>
        </div>
        {showVars && (
          <div className="mt-2 p-2 border border-ink-200 dark:border-ink-700 rounded bg-ink-50/60 dark:bg-ink-800/40">
            <div className="text-[10px] text-ink-500 dark:text-ink-400 mb-1">
              통화 시작 시 주입할 변수 — <code className="text-violet-600 dark:text-violet-400">{`{{key}}`}</code> 로 프롬프트·인사말에 치환됨
            </div>
            <textarea
              value={varsRaw}
              onChange={(e) => setVarsRaw(e.target.value)}
              placeholder={`customer_name=홍길동\nphone=010-1234-5678\nreservationNo=ACM-...`}
              rows={4}
              disabled={running}
              className="w-full text-[12px] font-mono px-2 py-1.5 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-900 dark:text-ink-100 outline-none focus:border-violet-400 disabled:opacity-50"
            />
          </div>
        )}
      </div>
    </div>
  );
}

function hasBrowserSpeech(): boolean {
  if (typeof window === 'undefined') return false;
  const W = window as unknown as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown };
  return !!(W.SpeechRecognition || W.webkitSpeechRecognition);
}

function stateLabel(s: CallState) {
  return { idle: '대기', listening: '고객 발화중...', thinking: '생각 중', speaking: '말하는 중' }[s];
}

function ToolCard({ tool }: { tool: ToolInvocation }) {
  const [open, setOpen] = useState(false);
  const argsText = formatJSON(tool.args);
  const resultText = tool.error ? tool.error : formatJSON(tool.result);
  const resultPreview = (resultText || '').slice(0, 140);
  const needsToggle = (resultText || '').length > 140;

  return (
    <div className="flex gap-2 justify-start">
      <div className="w-6 h-6 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 flex items-center justify-center shrink-0">
        <Wrench className="w-3 h-3" />
      </div>
      <div className="max-w-[85%] min-w-0 rounded-lg border border-amber-200 dark:border-amber-800/50 bg-amber-50/70 dark:bg-amber-900/15 overflow-hidden">
        <div className="px-2.5 py-1.5 flex items-center gap-1.5 text-[11px] border-b border-amber-200/70 dark:border-amber-800/40">
          {tool.pending ? (
            <Loader2 className="w-3 h-3 text-amber-600 dark:text-amber-400 animate-spin shrink-0" />
          ) : tool.ok ? (
            <CheckCircle2 className="w-3 h-3 text-emerald-600 dark:text-emerald-400 shrink-0" />
          ) : (
            <XCircle className="w-3 h-3 text-rose-600 dark:text-rose-400 shrink-0" />
          )}
          <span className="font-mono font-semibold text-amber-900 dark:text-amber-200 truncate">{tool.name}</span>
          {tool.via && (
            <span className="px-1 py-px text-[9px] rounded bg-amber-200/60 dark:bg-amber-800/50 text-amber-800 dark:text-amber-300 font-mono shrink-0">
              {tool.via}
            </span>
          )}
          <div className="flex-1" />
          {typeof tool.duration_ms === 'number' && (
            <span className="text-[10px] font-mono text-amber-700 dark:text-amber-400 shrink-0">{tool.duration_ms}ms</span>
          )}
        </div>
        <div className="px-2.5 py-1.5 text-[11px] font-mono">
          <div className="text-[9px] uppercase tracking-wider text-amber-700/70 dark:text-amber-400/60 mb-0.5">args</div>
          <pre className="whitespace-pre-wrap break-all text-amber-900 dark:text-amber-200">{argsText || '{}'}</pre>
        </div>
        {!tool.pending && (
          <div className="px-2.5 py-1.5 text-[11px] font-mono border-t border-amber-200/70 dark:border-amber-800/40">
            <div className="flex items-center gap-1 mb-0.5">
              <span className="text-[9px] uppercase tracking-wider text-amber-700/70 dark:text-amber-400/60">
                {tool.error ? 'error' : 'result'}
              </span>
              {needsToggle && (
                <button
                  onClick={() => setOpen((v) => !v)}
                  className="ml-auto text-[10px] text-amber-700 dark:text-amber-400 hover:underline flex items-center gap-0.5"
                >
                  {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  {open ? '접기' : '펼치기'}
                </button>
              )}
            </div>
            <pre className={clsx(
              'whitespace-pre-wrap break-all',
              tool.error ? 'text-rose-700 dark:text-rose-400' : 'text-amber-900 dark:text-amber-200',
              !open && needsToggle && 'max-h-20 overflow-hidden',
            )}>
              {open || !needsToggle ? resultText : resultPreview + '…'}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

function formatJSON(v: unknown): string {
  if (v === undefined || v === null) return '';
  if (typeof v === 'string') return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function Bubble({ bubble }: { bubble: Bubble }) {
  if (bubble.role === 'system') {
    return <div className="text-center text-xs text-ink-500 dark:text-ink-400 py-1">{bubble.text}</div>;
  }
  if (bubble.role === 'tool') {
    if (bubble.tool) return <ToolCard tool={bubble.tool} />;
    return (
      <div className="flex gap-2 justify-start">
        <div className="w-6 h-6 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 flex items-center justify-center shrink-0">
          <Wrench className="w-3 h-3" />
        </div>
        <div className="max-w-[80%] px-3 py-2 rounded-lg text-xs leading-relaxed bg-amber-50 dark:bg-amber-900/20 text-amber-900 dark:text-amber-200 font-mono whitespace-pre-wrap">
          {bubble.text}
        </div>
      </div>
    );
  }
  const isUser = bubble.role === 'user';
  return (
    <div className={clsx('flex gap-2', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="w-6 h-6 rounded-full bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300 flex items-center justify-center shrink-0">
          <BotIcon className="w-3.5 h-3.5" />
        </div>
      )}
      <div className={clsx(
        'max-w-[80%] px-3 py-2 rounded-lg text-sm leading-relaxed',
        isUser ? 'bg-violet-600 text-white' : 'bg-ink-100 dark:bg-ink-800 text-ink-800 dark:text-ink-100',
        bubble.interim && 'opacity-60 italic',
      )}>
        {bubble.text}
      </div>
      {isUser && (
        <div className="w-6 h-6 rounded-full bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300 flex items-center justify-center shrink-0">
          <UserIcon className="w-3.5 h-3.5" />
        </div>
      )}
    </div>
  );
}
