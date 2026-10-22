// ---------- Release: getting a mod ready to share ----------
// 1 check it (with safe fixes), 2 describe it (readme and Nexus text), 3 try it on a clean setup, 4 pack the zip.
const RL = {checks: null, info: null, readme: null, rmode: 'text', busy: false, last: null};
const RL_SEV = {error: ['✕', 'Needs fixing'], warning: ['⚠', 'Worth a look'], info: ['ℹ', 'Good to know'], ok: ['✓', 'Fine']};
const RL_PERMS = ['Ask me before uploading this mod elsewhere or using its parts in your own mods.',
  'You can use parts of this mod in your own mods, as long as you credit me.',
  'Do whatever you like with this mod, no need to ask or credit me.'];

async function renderRelease(){
  const wrap = $('#relwrap');
  if (!S.summary || !S.summary.project){ wrap.innerHTML = '<h1>Get ready to share</h1><p class="lead">Start a mod first.</p>'; return; }
  wrap.innerHTML = '<h1>Get ready to share</h1><p class="lead"><span class="spin"></span>Checking your mod…</p>';
  try { [RL.checks, RL.info] = await Promise.all([api('/api/release/check'), api('/api/release/info')]); }
  catch (e){ wrap.innerHTML = `<h1>Get ready to share</h1><div class="msg err">${esc(e.message)}</div>`; return; }
  rlRender();
}
function rlRender(){
  const c = RL.checks, i = RL.info, wrap = $('#relwrap');
  const n = s => c.checks.filter(x => x.sev === s).length;
  wrap.innerHTML = `<div class="chead"><div><h1 style="margin:0">📦 ${esc(i.name)}</h1>
      <div class="msg">Check it, describe it, try it on a clean setup, then pack a zip for Nexus or friends.</div></div>
      <button class="btn sm" id="rl-back">← My mod</button></div>
    <section class="rlstep"><h2><span class="rlnum">1</span> Check <span class="msg">${n('error') ? `<b class="sev-error">${n('error')} to fix</b> · ` : ''}${n('warning') ? n('warning') + ' worth a look · ' : ''}${n('ok')} fine</span>
      <button class="btn sm" id="rl-recheck" style="margin-left:auto">↻ Check again</button></h2>
      <div id="rl-checks">${c.checks.map(rlCheck).join('')}</div></section>
    <section class="rlstep"><h2><span class="rlnum">2</span> Describe</h2>
      <div class="cgrid2"><div>
        ${cField('Author', `<input class="inp" id="rl-author" maxlength="31" value="${esc(i.author)}" placeholder="Your name or nickname">`)}
        ${cField('Description <output id="rl-dlen"></output>', `<textarea class="inp" id="rl-desc" maxlength="255" rows="3" placeholder="One or two sentences: what the mod is about">${esc(i.description)}</textarea>`, 'Shown in the OpenMW launcher and at the top of the readme.')}
        <div class="crow">${cField('Version', `<input class="inp" id="rl-ver" value="${esc(i.version)}" style="max-width:110px">`, 'e.g. 1.0, then 1.1 for fixes')}
          ${cField('What\'s new in this version', `<input class="inp" id="rl-notes" value="${esc(i.notes)}" placeholder="${i.changelog.length ? 'e.g. Fixed the gate in the tomb' : 'First release'}">`)}</div>
        ${cField('Where to start', `<textarea class="inp" id="rl-start" rows="2" placeholder="Leave empty to list the doors into your new places automatically">${esc(i.start)}</textarea>`, 'Tells players how to find your content, e.g. "Talk to Fenas in Balmora\'s Eight Plates".')}
        ${cField('Credits', `<input class="inp" id="rl-credits" value="${esc(i.credits)}" placeholder="Anyone whose work or help you used">`)}
        ${cField('Permissions', `<select class="inp" id="rl-perm">${RL_PERMS.map(p => `<option ${p === (i.permissions || RL_PERMS[0]) ? 'selected' : ''}>${esc(p)}</option>`).join('')}${i.permissions && !RL_PERMS.includes(i.permissions) ? `<option selected>${esc(i.permissions)}</option>` : ''}</select>`)}
        <div class="actions"><button class="btn primary" id="rl-saveinfo">Save</button><span class="msg" id="rl-infomsg"></span></div>
      </div>
      <div><div class="rltabs"><button data-rm="text" class="${RL.rmode === 'text' ? 'on' : ''}">Readme</button><button data-rm="bbcode" class="${RL.rmode === 'bbcode' ? 'on' : ''}">Nexus description</button>
        <button class="btn sm" id="rl-copy" style="margin-left:auto">⧉ Copy</button></div>
        <pre class="rlreadme" id="rl-readme"><span class="spin"></span></pre></div></div></section>
    <section class="rlstep"><h2><span class="rlnum">3</span> Try it on a clean setup</h2>
      <p class="msg" style="line-height:1.6">Starts OpenMW with <b>only</b> the base game, your mod's masters (${c.masters.map(m => esc(m.name)).join(', ') || 'none'}) and your mod,
        leaving out every other mod you have installed. If something's missing or broken there, players will see it too. Your normal setup and saves are untouched.</p>
      <div class="crow" style="align-items:flex-end">${cField('Start in', `<input class="inp" id="rl-startcell" placeholder="a place name, e.g. Seyda Neen (empty: your first new place)">`)}
        <div class="cfield" style="flex:0"><button class="btn" id="rl-clean">▶ Start a clean test</button></div></div>
      <div class="msg" id="rl-cleanmsg"></div></section>
    <section class="rlstep"><h2><span class="rlnum">4</span> Pack it</h2>
      <p class="msg" style="line-height:1.6">Makes <b>${esc(i.name.replace(/[^\w\-]+/g, '_'))}-${esc(i.version)}.zip</b> with ${esc(i.plugin)}, your own files and the readme, laid out the way mod managers expect.
        Files that aren't used by your records but should go in too (e.g. new music) can go in your
        <a href="#" id="rl-extra">extra files folder</a>.</p>
      <div class="actions"><button class="btn primary" id="rl-pack">📦 Make the zip</button><button class="btn" id="rl-openrel">📂 Open the releases folder</button></div>
      <div id="rl-packmsg"></div>
      ${i.releases.length ? `<table class="t" style="margin-top:10px">${i.releases.map(r => `<tr><td>${esc(r.file)}</td><td class="msg">${(r.size / 1024).toFixed(0)} KB</td><td class="msg">${esc(r.t)}</td></tr>`).join('')}</table>` : ''}
    </section>
    <details class="rlstep" id="rl-dev" ${RL.devOpen ? 'open' : ''}><summary class="msg" style="cursor:pointer;color:var(--muted)">For the Workshop's own developer</summary>
      <p class="msg" style="line-height:1.6;margin-top:8px">Copies the Workshop's own source (its <b>app</b> folder, and the installer's files in <b>packaging</b>: .cs, .py, .txt, .manifest and .md, never the Nexus notes) into your GitHub folder, then opens GitHub Desktop for the commit. For whoever builds the Workshop itself; a mod needs none of this.</p>
      <div class="crow" style="align-items:center;flex-wrap:wrap;gap:8px"><span class="path" id="rl-ghfolder">…</span><button class="btn sm" id="rl-ghpick" title="Choose the folder GitHub Desktop commits from (asked once; kept in the Workshop's settings)">Choose the folder…</button>
        <button class="btn sm primary" id="rl-ghsync" title="Copy the source there and open GitHub Desktop">⇄ Sync to my GitHub folder</button></div>
      <div class="msg" id="rl-ghmsg" style="margin-top:6px"></div></details>`;
  $('#rl-back').onclick = () => showView('mymod');
  $('#rl-recheck').onclick = renderRelease;
  wrap.querySelectorAll('[data-rlfix]').forEach(b => b.onclick = () => rlFix(b.dataset.rlfix, b));
  wrap.querySelectorAll('[data-rlmore]').forEach(b => b.onclick = () => { b.parentElement.classList.toggle('open'); });
  wrap.querySelectorAll('[data-rlcell]').forEach(a => a.onclick = e => { e.preventDefault(); showView('world'); worldOpen(a.dataset.rlcell); });
  wrap.querySelectorAll('[data-rlscript]').forEach(a => a.onclick = e => { e.preventDefault(); sOpen(a.dataset.rlscript); });
  wrap.querySelectorAll('[data-rlquest]').forEach(a => a.onclick = e => { e.preventDefault(); showView('dialog'); dOpen(a.dataset.rlkind, a.dataset.rlquest); });
  const desc = $('#rl-desc'), dl = () => { $('#rl-dlen').textContent = desc.value.length + ' / 255'; };
  desc.oninput = dl; dl();
  $('#rl-saveinfo').onclick = rlSaveInfo;
  wrap.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { RL.rmode = b.dataset.rm; wrap.querySelectorAll('[data-rm]').forEach(x => x.classList.toggle('on', x === b)); rlReadme(); });
  $('#rl-copy').onclick = async () => { try { await navigator.clipboard.writeText($('#rl-readme').textContent); toast('Copied'); } catch (e){ toast('Select the text and copy it with Ctrl+C.', true); } };
  $('#rl-clean').onclick = rlClean;
  $('#rl-pack').onclick = rlPack;
  $('#rl-openrel').onclick = () => post('/api/release/open', {what: 'releases'}).catch(e => toast(e.message, true));
  $('#rl-extra').onclick = e => { e.preventDefault(); post('/api/release/open', {what: 'extra'}).then(r => toast('Opened ' + r.path)).catch(err => toast(err.message, true)); };
  $('#rl-dev').ontoggle = () => { RL.devOpen = $('#rl-dev').open; if (RL.devOpen) rlGithub(); };
  $('#rl-ghpick').onclick = () => rlGithubPick();
  $('#rl-ghsync').onclick = () => rlGithubSync();
  if (RL.devOpen) rlGithub();
  rlReadme();
}
// ----- the developer's corner: the source to the GitHub folder, GitHub Desktop opened for the commit
function rlGithubShow(s){
  RL.gh = s;
  const f = $('#rl-ghfolder'); if (!f) return;
  f.textContent = s.folder ? s.folder : 'No folder chosen yet (the usual one is ' + s.suggested + ')';
  f.style.color = s.folder && !s.exists ? 'var(--red)' : '';
  const m = $('#rl-ghmsg');
  m.textContent = (s.folder && !s.exists ? 'That folder is gone: choose it again. ' : s.folder && !s.is_repo ? 'There is no .git in that folder, so GitHub Desktop will not know it: choose the repository folder. ' : '') +
    `Copies from ${s.source}${s.packaging ? '' : ' (no packaging folder there, so only app is copied)'}.` + (s.desktop ? '' : ' GitHub Desktop was not found under %LOCALAPPDATA%\\GitHubDesktop; the files are copied all the same.');
}
async function rlGithub(){
  try { rlGithubShow(await api('/api/dev/github')); } catch (e){ const m = $('#rl-ghmsg'); if (m) m.textContent = e.message; }
}
async function rlGithubPick(){
  const b = $('#rl-ghpick'); b.disabled = true;
  try { const s = await post('/api/dev/github/pick'); rlGithubShow(s); if (!s.cancelled) toast('GitHub folder: ' + s.folder); }
  catch (e){ toast(e.message, true); }
  b.disabled = false;
}
async function rlGithubSync(){
  if (!RL.gh) await rlGithub();
  if (!RL.gh || !RL.gh.folder){ await rlGithubPick(); if (!RL.gh || !RL.gh.folder) return; }
  if (!confirm(`Copy the Workshop's source into\n${RL.gh.folder}\n(app mirrored, packaging's source files copied), then open GitHub Desktop for the commit?`)) return;
  const b = $('#rl-ghsync'); b.disabled = true; b.innerHTML = '<span class="spin"></span>Copying…';
  try {
    const r = await post('/api/dev/github/sync', {});
    const n = x => x ? `${x.copied} of ${x.total} file${x.total === 1 ? '' : 's'} changed${x.removed ? `, ${x.removed} removed` : ''}` : 'nothing';
    $('#rl-ghmsg').innerHTML = `✓ Synced to <b>${esc(r.folder)}</b>: app ${esc(n(r.app))}${r.packaging ? `; packaging ${esc(n(r.packaging))}` : ''}. ${r.opened ? 'GitHub Desktop is opening: write the commit message there and push.' : 'Open GitHub Desktop to commit' + (r.open_error ? ' (it could not be opened from here: ' + esc(r.open_error) + ')' : '') + '.'}`;
    toast('Synced. The commit is yours, in GitHub Desktop.');
  } catch (e){ toast(e.message, true); }
  b.disabled = false; b.textContent = '⇄ Sync to my GitHub folder';
}
function rlCheck(c){
  const [ic] = RL_SEV[c.sev] || ['•'];
  const items = c.items || [];
  const link = it => it.cell ? ` <a href="#" data-rlcell="${esc(it.cell)}">show</a>` : it.script ? ` <a href="#" data-rlscript="${esc(it.script)}">open</a>`
    : it.quest ? ` <a href="#" data-rlquest="${esc(it.quest)}" data-rlkind="quest">open</a>` : it.topic ? ` <a href="#" data-rlquest="${esc(it.topic)}" data-rlkind="topic">open</a>` : '';
  return `<div class="rlcheck ${c.sev} ${c.sev !== 'ok' && items.length < 6 ? 'open' : ''}">
    <div class="rlchead"><span class="rlic">${ic}</span><b>${esc(c.title)}</b>
      ${c.fix ? `<button class="btn sm ${c.sev === 'error' ? 'primary' : ''}" data-rlfix="${esc(c.fix.action)}">${esc(c.fix.label)}</button>` : ''}
      ${items.length ? `<button class="btn sm rlmore" data-rlmore="1">${items.length} ▾</button>` : ''}</div>
    ${c.detail ? `<div class="msg rldetail">${esc(c.detail)}</div>` : ''}
    ${items.length ? `<ul class="rlitems">${items.map(it => `<li>${esc(it.label)}${it.why && it.why.length ? ` <span class="msg">(${esc(it.why.join('; '))})</span>` : ''}${link(it)}</li>`).join('')}</ul>` : ''}</div>`;
}
async function rlFix(action, b){
  if (!await needProject()) return;
  b.disabled = true; b.innerHTML = '<span class="spin"></span>Fixing…';
  try { const r = await post('/api/release/fix', {action}); toast(`Fixed ${r.fixed} thing${r.fixed === 1 ? '' : 's'}. You can undo it like any change.`); await afterChange(); renderRelease(); }
  catch (e){ toast(e.message, true); b.disabled = false; }
}
async function rlSaveInfo(){
  try {
    RL.info = await post('/api/release/info', {author: $('#rl-author').value, description: $('#rl-desc').value, version: $('#rl-ver').value,
      notes: $('#rl-notes').value, start: $('#rl-start').value, credits: $('#rl-credits').value, permissions: $('#rl-perm').value});
    $('#rl-infomsg').textContent = 'Saved.'; setTimeout(() => { const m = $('#rl-infomsg'); if (m) m.textContent = ''; }, 2000);
    rlReadme(); afterChange();
    RL.checks = await api('/api/release/check'); $('#rl-checks').innerHTML = RL.checks.checks.map(rlCheck).join('');
  } catch (e){ toast(e.message, true); }
}
async function rlReadme(){
  try { RL.readme = await api('/api/release/readme'); } catch (e){ $('#rl-readme').textContent = e.message; return; }
  $('#rl-readme').textContent = RL.rmode === 'bbcode' ? RL.readme.bbcode : RL.readme.text;
}
async function rlClean(){
  const b = $('#rl-clean'); b.disabled = true;
  try {
    const r = await gameStart('/api/release/clean_test', {start: $('#rl-startcell').value});
    if (r) $('#rl-cleanmsg').innerHTML = `Starting OpenMW in <b>${esc(r.start)}</b> with ${r.masters.map(esc).join(', ')} and your mod only
      (${r.folders.length} data folder${r.folders.length === 1 ? '' : 's'}, archives: ${r.archives.map(esc).join(', ') || 'none'}). Quit the game when you're done.`;
  } catch (e){ toast(e.message, true); }
  b.disabled = false;
}
async function rlPack(){
  if (!await needProject()) return;
  const errs = RL.checks.checks.filter(c => c.sev === 'error');
  if (errs.length && !confirm('Some checks still need fixing:\n\n' + errs.map(c => '• ' + c.title).join('\n') + '\n\nPack it anyway?')) return;
  await rlSaveInfo();
  const b = $('#rl-pack'); b.disabled = true; b.innerHTML = '<span class="spin"></span>Packing…';
  try {
    const r = await post('/api/release/package', {});
    $('#rl-packmsg').innerHTML = `<div class="cnote" style="margin-top:10px">✓ Made <b>${esc(r.file)}</b> (${(r.size / 1024).toFixed(0)} KB, ${r.files} files).
      Upload it to Nexus Mods, and paste the <b>Nexus description</b> from step 2 into the mod's page.</div>`;
    toast('Packed ' + r.file);
    RL.info = await api('/api/release/info');
  } catch (e){ toast(e.message, true); }
  b.disabled = false; b.textContent = '📦 Make the zip';
}
