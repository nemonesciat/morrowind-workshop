// Building together: host the open mod for others to join, or join someone's, live from anywhere.
// The top bar's 👥 button shows who's in; what anyone changes shows up for everyone (and in each
// person's game) within a second or so.
const TOG = {st: null, seq: 0, feedN: null, timer: null, modal: null};

function togIsCopy(){
  const p = S.summary && S.summary.project;
  return !!(p && /\(together\)$/.test(p.name || ''));
}

async function togPoll(){
  try { TOG.st = await api('/api/together/status'); } catch (e){ TOG.st = null; }
  const st = TOG.st, b = $('#togetherbtn');
  if (b && st){
    const n = (st.members || []).filter(m => m.here !== false).length;
    if (st.role === 'host'){ b.textContent = `👥 Hosting · ${n + 1} here`; b.className = 'btn primary'; }
    else if (st.role === 'join'){ b.textContent = st.connected ? `👥 With ${st.host} · ${n} here` : '👥 Reconnecting…'; b.className = st.connected ? 'btn primary' : 'btn danger'; }
    else if (togIsCopy() && st.can_rejoin){ b.textContent = '👥 Rejoin'; b.className = 'btn primary'; }
    else { b.textContent = '👥 Build together'; b.className = 'btn'; }
  }
  if (!st) return;
  // a note when someone else changed something
  const feed = st.feed || [];
  const last = feed.length ? feed[feed.length - 1].n : 0;
  if (TOG.feedN === null) TOG.feedN = last;
  else if (last > TOG.feedN){
    const fresh = feed.filter(f => f.n > TOG.feedN);
    TOG.feedN = last;
    if (fresh.length > 2) toast(`${fresh.length} changes from ${[...new Set(fresh.map(f => f.who))].join(', ')}.`);
    else fresh.forEach(f => toast(`${f.who}: ${f.text}`));
  }
  // and show it where you're looking
  if (st.role && st.seq !== TOG.seq){
    const first = TOG.seq === 0;
    TOG.seq = st.seq;
    if (!first){
      try {
        if (typeof W !== 'undefined' && W.key && typeof worldReloadCell === 'function') await worldReloadCell(W.key);
        if (typeof V3 !== 'undefined' && V3.on && typeof v3Refresh === 'function') v3Refresh();
        if (typeof drawMap === 'function' && typeof W !== 'undefined' && W.key) drawMap();
      } catch (e){}
    }
  }
  if (TOG.modal && document.body.contains(TOG.modal)) togRender();
}

function togOpen(){
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = '<div class="modal" style="width:min(680px,94vw);max-height:92vh;overflow:auto" id="tog-m"></div>';
  document.body.appendChild(bg);
  bg.onclick = e => { if (e.target === bg) bg.remove(); };
  TOG.modal = bg;
  togRender();
}

const TOG_NEEDS = `<details id="tog-needs" style="margin-top:10px"><summary class="msg"><b>What you both need</b></summary><div class="msg" style="margin-top:6px">
  <ul style="margin:4px 0 0 18px;padding:0">
    <li>Morrowind, OpenMW and the Workshop, the <b>same Workshop version</b>.</li>
    <li>The <b>same game data and mods</b> the mod is built on (its masters, e.g. Tamriel Data if it uses it). Joining tells you if any are missing.
      Your own models, pictures and sounds from the Library come along by themselves.</li>
    <li>A way to reach the host's PC. On the same home network nothing is needed. From elsewhere the Workshop asks the host's router to let you in;
      if it can't, install <b>Tailscale</b> (free, tailscale.com) on both PCs and sign in (the host shares their PC with you), or use Hamachi or ZeroTier.
      The host then copies the invite code again.</li>
  </ul>
  To see the mod in your game, start it from the Workshop (▶ Play). Models, pictures and sounds that are new to you since the game started need a game restart.</div></details>`;

function togRender(){
  const m = TOG.modal && TOG.modal.querySelector('#tog-m'); if (!m) return;
  const st = TOG.st || {};
  const active = document.activeElement;
  if (active && m.contains(active) && (active.tagName === 'INPUT' || active.tagName === 'SELECT')) return;     // (not while typing)
  // (it's drawn again every few seconds: what you opened stays open, and the window stays scrolled where it was)
  const open = [...m.querySelectorAll('details[open]')].map(d => d.id), scrolled = m.scrollTop;
  const typed = {}; for (const id of ['tog-jcode', 'tog-hname', 'tog-jname', 'tog-pub']){ const e = m.querySelector('#' + id); if (e) typed[id] = e.value; }
  const errWas = (m.querySelector('#tog-err') || {}).textContent || '';
  const who = (st.members || []).map(x => `<span class="badge" style="margin:2px">${x.here === false ? '○' : '●'} ${esc(x.name)}${x.host ? ' (host)' : ''}</span>`).join(' ');
  const feed = (st.feed || []).slice().reverse().map(f => `<div class="msg">• <b>${esc(f.who)}</b>: ${esc(f.text)}</div>`).join('');
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem('ws-together') || '{}'); } catch (e){}
  if (st.role === 'host'){
    const router = st.router === 'asking' ? 'asking your router to let people in…'
      : st.router === 'open' ? `your router lets people in (your public address ${esc(st.router_ip || '')} is in the code)`
      : st.router === 'off' ? 'not asking the router (test mode)'
      : `your router didn't let people in by itself: ${esc((st.router || '').replace(/^no \(|\)$/g, ''))}`;
    m.innerHTML = `<h2>👥 You're hosting ${esc((S.summary && S.summary.project && S.summary.project.name) || '')}</h2>
      <div class="msg">Send this <b>invite code</b> to the people you want to build with (like a key: only give it to them). They paste it in their Workshop under 👥 Build together → Join.
        It stays the same for this mod, so they can come back any time you're hosting.</div>
      <div style="display:flex;gap:6px;margin:8px 0"><input class="inp" id="tog-code" readonly value="${esc(st.invite || '')}" style="flex:1;font-family:monospace;font-size:12px"><button class="btn primary" id="tog-copy">Copy</button></div>
      <div class="msg"><b>Here now:</b> ${who || 'just you so far'}</div>
      ${feed ? `<div style="margin-top:6px;max-height:110px;overflow:auto">${feed}</div>` : ''}
      <details id="tog-how" style="margin-top:8px"><summary class="msg"><b>How others reach you</b>: ${router}</summary><div class="msg" style="margin-top:6px">
        The code holds your PC's addresses (${(st.addresses || []).map(esc).join(', ') || 'none found'}) on port ${st.port}${st.router_ip ? ' and your public address' : ''}.
        On the same home network it works as it is. From elsewhere: ${st.router === 'open' ? 'it should work as it is.' : 'the easy way is <b>Tailscale</b> (free) on both PCs, signed in and your PC shared with them; its address (100.…) is then in the code. Or forward port ' + st.port + ' (TCP) on your router to this PC and put your public address below.'}
        If Windows asks whether to let the Workshop through its firewall, allow it.</div>
        <div style="display:flex;gap:6px;margin-top:6px"><input class="inp" id="tog-pub" placeholder="Your public address or name (optional)" value="${esc(st.public || '')}" style="flex:1"><button class="btn sm" id="tog-pubset">Use it</button></div></details>
      ${st.error ? `<div class="msg err">${esc(st.error)}</div>` : ''}
      ${TOG_NEEDS}
      <div class="actions"><button class="btn danger" id="tog-stop">Stop hosting</button><button class="btn" id="tog-newcode" title="Make a new code: the old one stops working (for everyone who had it)">New invite code</button><button class="btn" id="tog-close">Close</button></div>`;
    $('#tog-copy').onclick = () => { $('#tog-code').select(); try { navigator.clipboard.writeText(st.invite); } catch (e){ document.execCommand('copy'); } toast('Invite code copied. Send it to the people you build with.'); };
    $('#tog-pubset').onclick = async () => {
      try { await post('/api/together/host', {restart: true, name: st.name, port: st.port, public: $('#tog-pub').value}); toast('The code now has that address too. Copy it again.'); togPoll(); }
      catch (e){ toast(e.message, true); }
    };
    $('#tog-newcode').onclick = async () => {
      if (!confirm('Make a new invite code? The old one stops working, so everyone needs the new one to come back.')) return;
      try { await post('/api/together/host', {restart: true, name: st.name, port: st.port, new_code: true}); toast('New code made. Copy it and send it again.'); togPoll(); }
      catch (e){ toast(e.message, true); }
    };
  } else if (st.role === 'join'){
    m.innerHTML = `<h2>👥 Building together with ${esc(st.host || '')}</h2>
      <div class="msg">You're working on <b>${esc(st.mod || '')}</b> together. What anyone changes shows up for everyone in a second or so, here and in each person's game
        (start it from here with ▶ Play). <b>Undo</b> takes back your own last change only.</div>
      <div class="msg" style="margin-top:8px">${st.connected ? '● Connected.' : '<span class="err">Not reaching the host right now: trying again. Your changes wait and go when it\'s back.</span>'}
        ${st.sending ? ` ${st.sending} change${st.sending === 1 ? '' : 's'} on the way.` : ''}</div>
      <div class="msg"><b>Here now:</b> ${who}</div>
      ${feed ? `<div style="margin-top:6px;max-height:110px;overflow:auto">${feed}</div>` : ''}
      ${st.error && !st.connected ? '' : st.error ? `<div class="msg err">${esc(st.error)}</div>` : ''}
      ${(st.missing || []).length ? `<div class="msg err" style="margin-top:6px">The mod is built on ${st.missing.map(esc).join(', ')}, which your load order hasn't got. What comes from ${st.missing.length === 1 ? 'it' : 'them'} won't show for you. Get ${st.missing.length === 1 ? 'it' : 'them'}, switch ${st.missing.length === 1 ? 'it' : 'them'} on in Load order, and join again.</div>` : ''}
      ${st.versions ? `<div class="msg" style="margin-top:6px">You have Workshop ${esc(st.versions.you)} and the host ${esc(st.versions.host)}: it works, but the same version on both is best.</div>` : ''}
      ${TOG_NEEDS}
      <div class="actions"><button class="btn danger" id="tog-stop">Leave</button><button class="btn" id="tog-close">Close</button></div>`;
  } else {
    const proj = S.summary && S.summary.project;
    const copy = togIsCopy();
    m.innerHTML = `<h2>👥 Build together</h2>
      <div class="msg">Work on one mod with other people at the same time, from wherever they are. One person hosts; the others join with an invite code.
        Everyone sees every change within a second or so, in the Workshop and in their own game.</div>
      ${st.error ? `<div class="msg err" style="margin-top:6px">${esc(st.error)}</div>` : ''}
      ${copy && st.can_rejoin ? `<div style="border:1px solid #6b5730;border-radius:10px;padding:10px;margin-top:10px;background:#1e1810"><b style="color:var(--gold2)">This is your copy of ${esc(st.can_rejoin.mod || '')}</b>
        <div class="msg">Rejoin to keep building with the others. (The mod as the host has it replaces this copy: anything changed here while you weren't joined is left out.)</div>
        <div class="actions"><button class="btn primary" id="tog-rejoin">Rejoin</button></div></div>` : ''}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px">
        <div style="border:1px solid var(--line);border-radius:10px;padding:10px"><b style="color:var(--gold2)">Host ${proj && !copy ? esc(proj.name) : 'a mod'}</b>
          <div class="msg">${proj && !copy ? 'Share the mod you have open. Your copy is the one that counts.' : copy ? 'This is a copy of someone else\'s mod: open one of your own to host it.' : 'Open or start a mod first (the button at the top).'}</div>
          <label>Your name</label><input class="inp" id="tog-hname" value="${esc(saved.name || '')}" placeholder="e.g. Nemo">
          <div class="actions"><button class="btn primary" id="tog-host" ${proj && !copy ? '' : 'disabled'}>Start hosting</button></div></div>
        <div style="border:1px solid var(--line);border-radius:10px;padding:10px"><b style="color:var(--gold2)">Join someone</b>
          <div class="msg">Paste the invite code they sent you. You get a copy of their mod, as a mod of its own here (your own mods stay as they are).</div>
          <label>Invite code</label><input class="inp" id="tog-jcode" placeholder="WS-…">
          <label>Your name</label><input class="inp" id="tog-jname" value="${esc(saved.name || '')}" placeholder="e.g. Nemo">
          <div class="actions"><button class="btn primary" id="tog-join">Join</button></div></div></div>
      <div class="msg err" id="tog-err"></div>
      ${TOG_NEEDS}
      <div class="actions"><button class="btn" id="tog-close">Close</button></div>`;
    const remember = n => { try { localStorage.setItem('ws-together', JSON.stringify({name: n})); } catch (e){} };
    $('#tog-host').onclick = async () => {
      const name = $('#tog-hname').value.trim() || 'Host'; remember(name);
      const b = $('#tog-host'); b.disabled = true; b.textContent = 'Starting…';
      try { await post('/api/together/host', {name}); await togPoll(); }
      catch (e){ $('#tog-err').textContent = e.message; b.disabled = false; b.textContent = 'Start hosting'; }
    };
    const doJoin = async (code, name, btn) => {
      $('#tog-err').textContent = ''; btn.disabled = true; const was = btn.textContent; btn.textContent = 'Joining… (getting the mod and its files)';
      try {
        if (typeof rememberSelection === 'function') rememberSelection();
        await post('/api/together/join', {code, name});
        btn.textContent = 'Joined: the Workshop is getting the mod ready (a few seconds)…';
        toast('Joined. Getting the mod ready…'); setTimeout(poll, 300); await togPoll();
      } catch (e){ $('#tog-err').textContent = e.message; btn.disabled = false; btn.textContent = was; }
    };
    $('#tog-join').onclick = () => {
      const code = $('#tog-jcode').value.trim();
      if (!code) return $('#tog-err').textContent = 'Paste the invite code first.';
      const name = $('#tog-jname').value.trim() || 'Builder'; remember(name); doJoin(code, name, $('#tog-join'));
    };
    if ($('#tog-rejoin')) $('#tog-rejoin').onclick = () => doJoin('', '', $('#tog-rejoin'));
  }
  open.forEach(id => { const d = id && m.querySelector('#' + id); if (d) d.open = true; });
  for (const [id, v] of Object.entries(typed)){ const e = m.querySelector('#' + id); if (e && v !== '') e.value = v; }
  const err = m.querySelector('#tog-err'); if (err && errWas) err.textContent = errWas;
  m.scrollTop = scrolled;
  const stop = $('#tog-stop');
  if (stop) stop.onclick = async () => {
    if (!confirm(st.role === 'host' ? 'Stop hosting? The others can\'t make changes until you host again (they keep their copies).' : 'Leave? You keep your copy of the mod, and can rejoin any time the host is hosting.')) return;
    try { await post('/api/together/stop', {}); await togPoll(); } catch (e){ toast(e.message, true); }
  };
  $('#tog-close').onclick = () => TOG.modal.remove();
}

(function(){
  const b = $('#togetherbtn');
  if (b) b.onclick = togOpen;
  togPoll();
  TOG.timer = setInterval(togPoll, 2500);
})();
