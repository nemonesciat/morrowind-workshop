// Other modding programs (the OpenMW Suite for Blender and Maya…) asking to work on the open mod: bridge.py.
// A program asks once; this window says so and the user answers Allow or Not now. Allowed programs are listed in
// Settings under Connected programs, with Remove. What they send joins the unsaved work, one Undo each, marked ⇄.
const LINKP = {shown: new Set(), programs: [], busy: false};

async function lpPoll(){
  if (LINKP.busy || (typeof S !== 'undefined' && (!S.summary || S.summary.state !== 'ready'))) return;
  if (typeof TW !== 'undefined' && TW.second) return;          // (the first window answers)
  LINKP.busy = true;
  try {
    const r = await api('/api/bridge/asks');
    LINKP.programs = r.programs || [];
    for (const a of r.asks || []) if (!LINKP.shown.has(a.id)){ LINKP.shown.add(a.id); lpAsk(a); }
    lpSettings();
  } catch (e){} finally { LINKP.busy = false; }
}
setInterval(lpPoll, 2000);

function lpAsk(a){
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(480px,94vw)">
    <h3 style="margin-top:0">${esc(a.program)} wants to connect</h3>
    <p class="msg" title="It can place, move and remove things, add models, animations and scenes, and use the Workshop's own actions on the mod you have open. Each change shows in My changes marked ⇄ with its name; Undo takes it back. Remove it any time in Settings › Connected programs.">Its changes go into your open mod with your unsaved work, each with Undo.</p>
    ${a.version ? `<p class="msg">Version ${esc(a.version)}</p>` : ''}
    <div class="actions"><button class="btn primary" id="lp-yes">Allow</button><button class="btn" id="lp-no">Not now</button></div></div>`;
  document.body.appendChild(bg);
  const go = async allow => {
    bg.remove();
    try { await post('/api/bridge/answer', {id: a.id, allow}); if (allow) toast(a.program + ' is connected.'); }
    catch (e){ toast(e.message, true); }
  };
  bg.querySelector('#lp-yes').onclick = () => go(true);
  bg.querySelector('#lp-no').onclick = () => go(false);
}

function lpSettings(){
  const sec = document.getElementById('st-bridge-sec'), box = document.getElementById('st-bridge');
  if (!sec || !box) return;
  sec.hidden = !LINKP.programs.length;
  const html = LINKP.programs.map(p => `<div class="setrow"><span><b>${esc(p.name)}</b>${p.version ? ' ' + esc(p.version) : ''}</span>
    <span><span class="msg">${p.last == null ? 'not seen since the Workshop started' : p.last < 90 ? 'now' : Math.round(p.last / 60) + ' min ago'}</span>
    <button class="btn sm" data-lpremove="${esc(p.name)}" title="It can't change your mod again until it asks and you Allow it">Remove</button></span></div>`).join('');
  if (box.innerHTML !== html){
    box.innerHTML = html;
    box.querySelectorAll('[data-lpremove]').forEach(b => b.onclick = async () => {
      try { LINKP.programs = (await post('/api/bridge/remove', {name: b.dataset.lpremove})).programs || []; lpSettings(); }
      catch (e){ toast(e.message, true); }
    });
  }
}
