// Callbot Console — vanilla JS SPA + WebSocket 음성 클라이언트.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const main = $('#main');

const state = {
  tenants: [],
  bots: [],
  callSessions: [],
  currentBotId: null,
  health: null,
};

// ---------- API ----------
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return null;
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText} — ${text}`);
  }
  if (res.headers.get('content-type')?.includes('application/json')) return res.json();
  return res.text();
}

// ---------- Routing ----------
const routes = {
  '': viewDashboard,
  '#dashboard': viewDashboard,
  '#bots': viewBots,
  '#bot': viewBotEditor, // #bot/<id>
  '#test-call': viewTestCall, // ?bot_id=
  '#calls': viewCalls,
  '#call': viewCallDetail, // #call/<id>
  '#tenants': viewTenants,
};

window.addEventListener('hashchange', render);
window.addEventListener('DOMContentLoaded', async () => {
  // 네비게이션 클릭 핸들러 (data-view → hash 변경)
  document.querySelector('#nav')?.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-view]');
    if (!a) return;
    e.preventDefault();
    location.hash = '#' + a.dataset.view;
  });

  try {
    state.health = await api('/api/health');
  } catch (e) {
    console.warn('health failed', e);
  }
  await refreshAll();
  updateModePill();
  render();
});

function updateModePill() {
  const pill = $('#modePill');
  if (state.health?.voice_mode_available) {
    pill.className = 'mode-pill voice';
    pill.textContent = '음성 모드 활성 (GCP)';
  } else {
    pill.className = 'mode-pill text';
    pill.textContent = '텍스트 모드 (Mock fallback)';
  }
}

function setActiveNav(view) {
  $$('#nav a').forEach((a) => a.classList.toggle('active', a.dataset.view === view));
}

function render() {
  const hash = location.hash || '';
  const [base, arg] = hash.split('/');
  const fn = routes[base] || viewDashboard;
  setActiveNav(base.replace('#', '') || 'dashboard');
  cleanupCall(); // 다른 뷰로 가면 음성 세션 정리
  fn(arg);
}

async function refreshAll() {
  state.tenants = await api('/api/tenants');
  state.bots = await api('/api/bots');
}

// ---------- View: Dashboard ----------
async function viewDashboard() {
  const sessions = await api('/api/calls?limit=5').catch(() => []);
  main.innerHTML = `
    <h1>대시보드</h1>
    <div class="grid-3">
      <div class="card">
        <h2>고객사</h2>
        <div style="font-size:28px;font-weight:700">${state.tenants.length}</div>
      </div>
      <div class="card">
        <h2>활성 콜봇</h2>
        <div style="font-size:28px;font-weight:700">${state.bots.filter((b) => b.is_active).length}</div>
      </div>
      <div class="card">
        <h2>총 콜봇</h2>
        <div style="font-size:28px;font-weight:700">${state.bots.length}</div>
      </div>
    </div>
    <div class="card">
      <h2>최근 통화 5건</h2>
      ${
        sessions.length
          ? `<table><thead><tr><th>#</th><th>봇</th><th>상태</th><th>시작</th><th>종료 사유</th></tr></thead>
          <tbody>${sessions
            .map((s) => {
              const bot = state.bots.find((b) => b.id === s.bot_id);
              return `<tr onclick="location.hash='#call/${s.id}'">
                <td>${s.id}</td><td>${bot?.name || s.bot_id}</td>
                <td><span class="pill ${s.status === 'ended' ? 'inactive' : 'active'}">${s.status}</span></td>
                <td class="muted">${new Date(s.started_at).toLocaleString()}</td>
                <td class="muted">${s.end_reason || '-'}</td>
              </tr>`;
            })
            .join('')}
          </tbody></table>`
          : '<div class="muted">아직 통화가 없습니다. <a href="#test-call">테스트 콜</a>을 해보세요.</div>'
      }
    </div>
    <div class="card">
      <h2>아키텍처 요약</h2>
      <p class="muted">vox 내재화 MVP. 미디어 운반은 WebSocket + Silero VAD. 인식·합성·LLM은 GCP (Speech-to-Text / TTS / Gemini). 키가 없으면 자동으로 텍스트 모드로 동작합니다.</p>
      <p class="muted">설계 문서: <span class="kbd">docs/plans/VOX_INSOURCING_DESIGN.md</span></p>
    </div>
  `;
}

// ---------- View: Bots ----------
async function viewBots() {
  await refreshAll();
  main.innerHTML = `
    <div class="row" style="justify-content:space-between">
      <h1>콜봇</h1>
      <button onclick="newBotPrompt()">＋ 새 콜봇</button>
    </div>
    <div class="card">
      ${
        state.bots.length
          ? `<table>
              <thead><tr><th>이름</th><th>고객사</th><th>언어/음성</th><th>상태</th><th>스킬</th><th></th></tr></thead>
              <tbody>${state.bots
                .map((b) => {
                  const tenant = state.tenants.find((t) => t.id === b.tenant_id);
                  return `<tr onclick="location.hash='#bot/${b.id}'">
                    <td><strong>${esc(b.name)}</strong></td>
                    <td class="muted">${tenant?.name || b.tenant_id}</td>
                    <td class="muted">${b.language} · ${b.voice}</td>
                    <td><span class="pill ${b.is_active ? 'active' : 'inactive'}">${b.is_active ? '활성' : '비활성'}</span></td>
                    <td class="muted">${b.llm_model}</td>
                    <td><button class="ghost" onclick="event.stopPropagation();location.hash='#test-call?bot_id=${b.id}'">테스트</button></td>
                  </tr>`;
                })
                .join('')}
              </tbody></table>`
          : '<div class="muted">콜봇이 없습니다.</div>'
      }
    </div>
  `;
}

async function newBotPrompt() {
  if (!state.tenants.length) {
    alert('먼저 고객사를 만드세요.');
    location.hash = '#tenants';
    return;
  }
  const name = prompt('새 콜봇 이름?');
  if (!name) return;
  const tenant_id = state.tenants[0].id;
  const bot = await api('/api/bots', { method: 'POST', body: { tenant_id, name } });
  location.hash = `#bot/${bot.id}`;
}

// ---------- View: Bot editor ----------
async function viewBotEditor(id) {
  const botId = parseInt(id, 10);
  if (!botId) return viewBots();
  const bot = await api(`/api/bots/${botId}`);
  const skills = await api(`/api/skills?bot_id=${botId}`);
  const kbs = await api(`/api/knowledge?bot_id=${botId}`);

  main.innerHTML = `
    <div class="row" style="justify-content:space-between">
      <h1>${esc(bot.name)}</h1>
      <div class="row">
        <button class="ghost" onclick="location.hash='#test-call?bot_id=${bot.id}'">테스트 콜</button>
        <button class="ghost" onclick="showRuntime(${bot.id})">런타임 프롬프트 보기</button>
        <button class="danger" onclick="deleteBot(${bot.id})">삭제</button>
      </div>
    </div>

    <div class="card">
      <h2>기본 정보</h2>
      <div class="grid-2">
        <div><label>이름</label><input id="f_name" value="${esc(bot.name)}"/></div>
        <div><label>활성 여부</label>
          <select id="f_is_active">
            <option value="true" ${bot.is_active ? 'selected' : ''}>활성</option>
            <option value="false" ${!bot.is_active ? 'selected' : ''}>비활성</option>
          </select>
        </div>
        <div><label>인사말 (첫 turn에 재생)</label><input id="f_greeting" value="${esc(bot.greeting)}"/></div>
        <div><label>언어</label><input id="f_language" value="${esc(bot.language)}"/></div>
        <div><label>음성 (GCP voice name)</label><input id="f_voice" value="${esc(bot.voice)}"/></div>
        <div><label>LLM 모델</label><input id="f_llm_model" value="${esc(bot.llm_model)}"/></div>
      </div>
      <hr/>
      <div><label>페르소나 — 봇의 정체성/말투</label>
        <textarea id="f_persona">${esc(bot.persona)}</textarea>
      </div>
      <div style="margin-top:12px"><label>봇 가이드 (전체 공통 시스템 프롬프트)</label>
        <textarea id="f_system_prompt">${esc(bot.system_prompt)}</textarea>
      </div>
      <div style="margin-top:12px"><button onclick="saveBot(${bot.id})">저장</button></div>
    </div>

    <div class="card">
      <div class="row" style="justify-content:space-between"><h2>스킬 (Skill)</h2>
        <button class="ghost" onclick="addSkill(${bot.id})">＋ 새 스킬</button></div>
      ${skills
        .map(
          (s) => `
        <div class="card" style="margin:8px 0;background:#1c2230">
          <div class="row" style="justify-content:space-between">
            <div><strong>${esc(s.name)}</strong>
              ${s.is_frontdoor ? '<span class="pill frontdoor">Frontdoor</span>' : ''}
              <span class="muted" style="margin-left:8px">order ${s.order}</span>
            </div>
            <div class="row">
              <button class="ghost" onclick="editSkill(${s.id})">편집</button>
              <button class="danger" onclick="deleteSkill(${s.id})">삭제</button>
            </div>
          </div>
          <div class="muted" style="margin:6px 0">${esc(s.description)}</div>
          <pre style="white-space:pre-wrap;background:#0f1115;padding:10px;border-radius:8px;border:1px solid #2a3142;font-size:12px;margin:0">${esc(s.content)}</pre>
        </div>`
        )
        .join('')}
    </div>

    <div class="card">
      <div class="row" style="justify-content:space-between"><h2>지식 베이스</h2>
        <button class="ghost" onclick="addKB(${bot.id})">＋ 새 지식</button></div>
      ${kbs
        .map(
          (k) => `
        <div class="card" style="margin:8px 0;background:#1c2230">
          <div class="row" style="justify-content:space-between">
            <strong>${esc(k.title)}</strong>
            <button class="danger" onclick="deleteKB(${k.id})">삭제</button>
          </div>
          <div class="muted" style="margin-top:6px">${esc(k.content)}</div>
        </div>`
        )
        .join('')}
    </div>
  `;
}

async function saveBot(id) {
  const payload = {
    name: $('#f_name').value,
    persona: $('#f_persona').value,
    system_prompt: $('#f_system_prompt').value,
    greeting: $('#f_greeting').value,
    language: $('#f_language').value,
    voice: $('#f_voice').value,
    llm_model: $('#f_llm_model').value,
    is_active: $('#f_is_active').value === 'true',
  };
  await api(`/api/bots/${id}`, { method: 'PATCH', body: payload });
  alert('저장되었습니다.');
  render();
}

async function deleteBot(id) {
  if (!confirm('정말 삭제하시겠어요?')) return;
  await api(`/api/bots/${id}`, { method: 'DELETE' });
  location.hash = '#bots';
}

async function addSkill(botId) {
  const name = prompt('스킬 이름?');
  if (!name) return;
  await api('/api/skills', { method: 'POST', body: { bot_id: botId, name, description: '', content: '## 흐름\n- ', order: 99 } });
  render();
}

async function editSkill(id) {
  const skills = await api(`/api/skills?bot_id=${$('#f_name') ? parseInt(location.hash.split('/')[1], 10) : 0}`);
  const s = skills.find((x) => x.id === id);
  const html = `
    <div class="card">
      <h1>스킬 편집: ${esc(s.name)}</h1>
      <div class="grid-2">
        <div><label>이름</label><input id="es_name" value="${esc(s.name)}"/></div>
        <div><label>순서</label><input id="es_order" type="number" value="${s.order}"/></div>
        <div><label>설명</label><input id="es_description" value="${esc(s.description)}"/></div>
        <div><label>Frontdoor</label>
          <select id="es_frontdoor">
            <option value="false" ${!s.is_frontdoor ? 'selected' : ''}>아니오</option>
            <option value="true" ${s.is_frontdoor ? 'selected' : ''}>예</option>
          </select>
        </div>
      </div>
      <div style="margin-top:12px"><label>스킬 내용 (markdown)</label>
        <textarea id="es_content" style="min-height:280px">${esc(s.content)}</textarea>
      </div>
      <div style="margin-top:12px" class="row">
        <button onclick="saveSkillFromForm(${s.id}, ${s.bot_id})">저장</button>
        <button class="ghost" onclick="location.hash='#bot/${s.bot_id}'">취소</button>
      </div>
    </div>`;
  main.innerHTML = html;
}

async function saveSkillFromForm(id, botId) {
  await api(`/api/skills/${id}`, {
    method: 'PATCH',
    body: {
      name: $('#es_name').value,
      description: $('#es_description').value,
      content: $('#es_content').value,
      is_frontdoor: $('#es_frontdoor').value === 'true',
      order: parseInt($('#es_order').value, 10) || 0,
    },
  });
  location.hash = `#bot/${botId}`;
}

async function deleteSkill(id) {
  if (!confirm('스킬을 삭제할까요?')) return;
  await api(`/api/skills/${id}`, { method: 'DELETE' });
  render();
}

async function addKB(botId) {
  const title = prompt('지식 제목?');
  if (!title) return;
  const content = prompt('지식 내용?');
  if (content === null) return;
  await api('/api/knowledge', { method: 'POST', body: { bot_id: botId, title, content } });
  render();
}

async function deleteKB(id) {
  if (!confirm('지식을 삭제할까요?')) return;
  await api(`/api/knowledge/${id}`, { method: 'DELETE' });
  render();
}

async function showRuntime(botId) {
  const r = await api(`/api/bots/${botId}/runtime`);
  const w = window.open('', '_blank');
  w.document.body.innerHTML = `<pre style="font-family:ui-monospace,SFMono-Regular,monospace;white-space:pre-wrap;padding:20px">${esc(JSON.stringify(r, null, 2))}</pre>`;
}

// ---------- View: Test Call ----------
let activeCall = null; // {ws, session_id, audioCtx, micSrc, workletNode, queueTime}

async function viewTestCall(arg) {
  const params = new URLSearchParams((arg || '').replace(/^.*\?/, ''));
  const initialBotId = parseInt(params.get('bot_id') || state.currentBotId || (state.bots[0]?.id || 0), 10);
  if (!state.bots.length) {
    main.innerHTML = '<div class="card">콜봇이 없습니다. 먼저 콜봇을 만드세요.</div>';
    return;
  }

  main.innerHTML = `
    <h1>테스트 콜</h1>
    <div class="card">
      <div class="grid-2">
        <div><label>콜봇 선택</label>
          <select id="tc_bot">
            ${state.bots.map((b) => `<option value="${b.id}" ${b.id === initialBotId ? 'selected' : ''}>${esc(b.name)}</option>`).join('')}
          </select>
        </div>
        <div><label>모드</label>
          <select id="tc_mode">
            <option value="voice" ${state.health?.voice_mode_available ? '' : 'disabled'}>음성 (마이크 + GCP STT/TTS)</option>
            <option value="text" ${state.health?.voice_mode_available ? '' : 'selected'}>텍스트 (LLM만)</option>
          </select>
        </div>
      </div>
      <div class="row" style="margin-top:12px">
        <button id="tc_start" onclick="startCall()">▶ 통화 시작</button>
        <button id="tc_end" class="danger" disabled onclick="endCall()">⏹ 종료</button>
        <button id="tc_interrupt" class="ghost" disabled onclick="interruptCall()">⛔ 끼어들기</button>
        <span id="tc_session" class="muted"></span>
      </div>
    </div>

    <div class="card">
      <div class="row" style="justify-content:center;margin-bottom:12px">
        <div id="tc_orb" class="tc-orb">대기</div>
      </div>
      <div id="tc_conv" class="tc-conv"></div>
      <div class="tc-textbar">
        <input id="tc_input" placeholder="텍스트 모드에서 메시지 입력 후 엔터" />
        <button onclick="sendText()">전송</button>
      </div>
    </div>
  `;

  $('#tc_input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendText();
  });
}

function setOrb(value) {
  const orb = $('#tc_orb');
  if (!orb) return;
  orb.className = 'tc-orb ' + (value !== 'idle' ? value : '');
  const label = { idle: '대기', listening: '듣는 중', thinking: '생각 중', speaking: '말하는 중' }[value] || value;
  orb.textContent = label;
}

function addBubble(role, text, opts = {}) {
  const conv = $('#tc_conv');
  if (!conv) return;
  let node;
  if (opts.replaceInterim) {
    node = conv.querySelector('.bubble.interim');
  }
  if (!node) {
    node = document.createElement('div');
    conv.appendChild(node);
  }
  node.className = `bubble ${role}${opts.interim ? ' interim' : ''}`;
  node.textContent = text;
  conv.scrollTop = conv.scrollHeight;
}

async function startCall() {
  const botId = parseInt($('#tc_bot').value, 10);
  const mode = $('#tc_mode').value;
  const resp = await api('/api/calls/start', { method: 'POST', body: { bot_id: botId } });
  $('#tc_session').textContent = `세션 #${resp.session_id} · room ${resp.room_id}`;

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws/calls/${resp.session_id}`);
  ws.binaryType = 'arraybuffer';

  activeCall = { ws, sessionId: resp.session_id, audioCtx: null, micNode: null, queueTime: 0, mode };

  ws.onopen = async () => {
    $('#tc_start').disabled = true;
    $('#tc_end').disabled = false;
    $('#tc_interrupt').disabled = mode === 'text';
    if (mode === 'voice') {
      await openMic(ws);
    }
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') {
      handleServerJson(JSON.parse(ev.data));
    } else {
      playPCM(new Int16Array(ev.data));
    }
  };
  ws.onclose = () => onCallClosed();
  ws.onerror = (e) => {
    console.error('ws error', e);
    onCallClosed();
  };
}

function handleServerJson(msg) {
  switch (msg.type) {
    case 'state':
      setOrb(msg.value);
      break;
    case 'transcript':
      addBubble(msg.role, msg.text, { interim: msg.is_final === false, replaceInterim: msg.is_final === false });
      // is_final이 true면 interim 흔적 제거
      if (msg.role === 'user' && msg.is_final !== false) {
        const old = $('#tc_conv').querySelector('.bubble.interim');
        if (old) old.classList.remove('interim');
      }
      break;
    case 'skill':
      addBubble('assistant', `[스킬 전환] ${msg.name}`, {});
      break;
    case 'handover':
      addBubble('assistant', '[상담사 전환 요청]', {});
      break;
    case 'error':
      addBubble('assistant', `[에러] ${msg.where}: ${msg.message}`, {});
      break;
    case 'end':
      addBubble('assistant', `[종료] ${msg.reason}`, {});
      break;
  }
}

async function openMic(ws) {
  const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
  await audioCtx.audioWorklet.addModule('/audio-worklet.js');
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true } });
  const src = audioCtx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(audioCtx, 'mic-capture', {
    processorOptions: { targetRate: 16000 },
  });
  node.port.onmessage = (e) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(e.data);
  };
  src.connect(node);
  // 출력은 destination에 연결하지 않음 (피드백 방지)
  activeCall.audioCtx = audioCtx;
  activeCall.micNode = node;
  activeCall.micStream = stream;
}

function playPCM(int16) {
  if (!activeCall) return;
  if (!activeCall.audioCtx) {
    activeCall.audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
  }
  const ctx = activeCall.audioCtx;
  const f32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 0x8000;
  const buf = ctx.createBuffer(1, f32.length, 16000);
  buf.getChannelData(0).set(f32);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.connect(ctx.destination);
  const when = Math.max(ctx.currentTime, activeCall.queueTime);
  src.start(when);
  activeCall.queueTime = when + buf.duration;
}

function sendText() {
  if (!activeCall) {
    alert('먼저 통화를 시작하세요.');
    return;
  }
  const text = $('#tc_input').value.trim();
  if (!text) return;
  activeCall.ws.send(JSON.stringify({ type: 'text', text }));
  $('#tc_input').value = '';
}

function interruptCall() {
  if (!activeCall) return;
  activeCall.ws.send(JSON.stringify({ type: 'interrupt' }));
}

async function endCall() {
  if (!activeCall) return;
  try {
    activeCall.ws.send(JSON.stringify({ type: 'end_call' }));
  } catch {}
  setTimeout(() => activeCall && activeCall.ws.close(), 200);
}

function onCallClosed() {
  if ($('#tc_start')) {
    $('#tc_start').disabled = false;
    $('#tc_end').disabled = true;
    $('#tc_interrupt').disabled = true;
  }
  cleanupCall();
}

function cleanupCall() {
  if (!activeCall) return;
  try {
    activeCall.micStream?.getTracks().forEach((t) => t.stop());
  } catch {}
  try {
    activeCall.micNode?.disconnect();
  } catch {}
  try {
    activeCall.audioCtx?.close();
  } catch {}
  try {
    if (activeCall.ws.readyState !== WebSocket.CLOSED) activeCall.ws.close();
  } catch {}
  activeCall = null;
}

// ---------- View: Calls ----------
async function viewCalls() {
  const sessions = await api('/api/calls?limit=200');
  main.innerHTML = `
    <h1>통화 로그</h1>
    <div class="card">
      ${
        sessions.length
          ? `<table>
            <thead><tr><th>#</th><th>봇</th><th>상태</th><th>시작</th><th>종료</th><th>사유</th></tr></thead>
            <tbody>${sessions
              .map((s) => {
                const bot = state.bots.find((b) => b.id === s.bot_id);
                return `<tr onclick="location.hash='#call/${s.id}'">
                  <td>${s.id}</td><td>${esc(bot?.name || s.bot_id)}</td>
                  <td><span class="pill ${s.status === 'ended' ? 'inactive' : 'active'}">${s.status}</span></td>
                  <td class="muted">${new Date(s.started_at).toLocaleString()}</td>
                  <td class="muted">${s.ended_at ? new Date(s.ended_at).toLocaleString() : '-'}</td>
                  <td class="muted">${s.end_reason || '-'}</td>
                </tr>`;
              })
              .join('')}
            </tbody></table>`
          : '<div class="muted">아직 통화 기록이 없습니다.</div>'
      }
    </div>
  `;
}

async function viewCallDetail(arg) {
  const id = parseInt(arg, 10);
  const sess = await api(`/api/calls/${id}`);
  const ts = await api(`/api/transcripts/${id}`);
  const bot = state.bots.find((b) => b.id === sess.bot_id);
  main.innerHTML = `
    <div class="row" style="justify-content:space-between">
      <h1>통화 #${sess.id}</h1>
      <button class="ghost" onclick="history.back()">← 뒤로</button>
    </div>
    <div class="card">
      <div class="row">
        <div class="col"><span class="muted">봇</span><div>${esc(bot?.name || sess.bot_id)}</div></div>
        <div class="col"><span class="muted">상태</span><div><span class="pill ${sess.status === 'ended' ? 'inactive' : 'active'}">${sess.status}</span></div></div>
        <div class="col"><span class="muted">시작</span><div>${new Date(sess.started_at).toLocaleString()}</div></div>
        <div class="col"><span class="muted">종료</span><div>${sess.ended_at ? new Date(sess.ended_at).toLocaleString() : '-'}</div></div>
        <div class="col"><span class="muted">사유</span><div>${esc(sess.end_reason || '-')}</div></div>
      </div>
    </div>
    <div class="card">
      <h2>트랜스크립트</h2>
      <div class="tc-conv" style="max-height:none">
        ${
          ts.length
            ? ts
                .map(
                  (t) => `<div class="bubble ${t.role}">
                    <span class="pill role-${t.role}">${t.role}</span>
                    <div style="margin-top:6px">${esc(t.text)}</div>
                    <div class="muted" style="font-size:11px;margin-top:4px">${new Date(t.created_at).toLocaleTimeString()}</div>
                  </div>`
                )
                .join('')
            : '<div class="muted">트랜스크립트 없음</div>'
        }
      </div>
    </div>
  `;
}

// ---------- View: Tenants ----------
async function viewTenants() {
  await refreshAll();
  main.innerHTML = `
    <div class="row" style="justify-content:space-between">
      <h1>고객사</h1>
      <button onclick="newTenant()">＋ 새 고객사</button>
    </div>
    <div class="card">
      ${
        state.tenants.length
          ? `<table>
            <thead><tr><th>ID</th><th>이름</th><th>슬러그</th><th>봇 수</th><th>생성일</th><th></th></tr></thead>
            <tbody>${state.tenants
              .map((t) => {
                const botCount = state.bots.filter((b) => b.tenant_id === t.id).length;
                return `<tr>
                  <td>${t.id}</td><td>${esc(t.name)}</td><td class="muted">${esc(t.slug)}</td>
                  <td>${botCount}</td>
                  <td class="muted">${new Date(t.created_at).toLocaleDateString()}</td>
                  <td><button class="danger" onclick="deleteTenant(${t.id})">삭제</button></td>
                </tr>`;
              })
              .join('')}
            </tbody></table>`
          : '<div class="muted">고객사가 없습니다.</div>'
      }
    </div>
  `;
}

async function newTenant() {
  const name = prompt('고객사 이름?');
  if (!name) return;
  const slug = prompt('슬러그 (영문, 소문자, 하이픈)?', name.toLowerCase().replace(/\s+/g, '-'));
  if (!slug) return;
  await api('/api/tenants', { method: 'POST', body: { name, slug } });
  render();
}

async function deleteTenant(id) {
  if (!confirm('정말 삭제하시겠어요? (소속 콜봇/통화도 모두 삭제됩니다)')) return;
  await api(`/api/tenants/${id}`, { method: 'DELETE' });
  render();
}

// ---------- Utils ----------
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Expose handlers to inline onclick
Object.assign(window, {
  newBotPrompt,
  saveBot,
  deleteBot,
  addSkill,
  editSkill,
  saveSkillFromForm,
  deleteSkill,
  addKB,
  deleteKB,
  showRuntime,
  startCall,
  endCall,
  sendText,
  interruptCall,
  newTenant,
  deleteTenant,
});
