// ---------- The guided first house (Home → Build your first house) ----------
// A few pointers over the real buttons, one at a time: start a mod, Create → Build from pieces, name it,
// lay out the rooms, build it (furnished), see it in 3D, then Play here. Each step goes on by itself once
// it's done (or with Next where there's nothing to wait for); Skip ends it, and nothing is done for you.
const COACH = {on: false};

const COACH_STEPS = [
  {skip: () => S.summary && S.summary.project,
   at: () => $('#projpill'), title: 'First, start a mod',
   text: 'Click here and give it a name. Everything you make goes into it, saved as you work.',
   done: () => S.summary && S.summary.project},
  {at: () => $('nav [data-view="createv"]'), title: 'Open Create',
   text: 'Quick starts for houses, dungeons, people, items and more.',
   done: () => pageOn('createv')},
  {skip: () => typeof CR !== 'undefined' && CR.kind === 'build' && CR.bmode !== 'copy' && $('#cr-name'),
   at: () => $('[data-ck="build"]'), title: 'Build from pieces',
   text: 'A new house built from one style\'s walls, floors and doors, the way the game\'s own are.',
   done: () => typeof CR !== 'undefined' && CR.kind === 'build' && $('#cr-name')},
  {at: () => $('#cr-name'), title: 'Name it, and pick a style',
   text: 'A name like "Balmora, My House". The style just below (Hlaalu, Redoran, Imperial…) picks the walls, the lights and the furniture.',
   above: true, next: true},
  {at: () => $('#pl-stage'), title: 'Lay out the rooms',
   text: 'Drag the rooms into place and resize them; "+ Room" adds a Bedroom, Kitchen, Storeroom… Their names tell the furnisher what each room is for.',
   next: true},
  {at: () => $('#cr-go'), title: 'Build it',
   text: '"Furnish the rooms" is ticked, so it comes furnished too. It takes a moment, then the house opens on the World map.',
   // (once pressed: what is happening and how far it is, here in the tip; the page's own note beside the button
   // was under the tip, so the tour looked stuck for the minutes a big house takes)
   busy: () => pageOn('createv') && $('#cr-go') && $('#cr-go').disabled, busyAt: () => $('#cr-msg'),
   busyTitle: 'Building your house…',
   busyText: 'The walls, floors, doors and stairs go up first, then the furnisher fills every room, floor by floor. A big house takes a minute or two; the first time, the Workshop also learns from the game\'s own places once. The house opens on the World map by itself when it\'s done.',
   start: () => { COACH.key = W.key; },
   done: () => pageOn('world') && W.key && W.key !== COACH.key && W.cells[W.key]},
  {at: () => $('[data-view3d="1"]'), title: 'See it in 3D',
   text: 'Walk through it the way you will in the game.',
   done: () => V3.on},
  {at: null, title: 'Have a look round',
   text: 'Right-drag to look, W A S D to fly, the wheel to go forward and back. Click anything to select it, drag the arrows to move it. Ctrl+Z takes back any change.',
   next: true},
  {at: () => $('#w-play'), title: 'Try it in the game',
   text: 'Play here starts OpenMW in your house with a test character (your own saves are untouched). Things you change here show up in the game as you make them.',
   last: true},
];

function coachHouse(){
  coachEnd();
  COACH.on = true; COACH.n = -1; COACH.skipped = 0;
  const css = document.createElement('style'); css.id = 'coach-css';
  css.textContent = `
    .coach-ring{position:fixed;z-index:9990;pointer-events:none;border-radius:9px;box-shadow:0 0 0 3px var(--gold2),0 0 0 9999px #0006;
      transition:all .25s ease;animation:coach-pulse 1.6s ease-in-out infinite}
    @keyframes coach-pulse{50%{box-shadow:0 0 0 6px var(--gold2),0 0 0 9999px #0006}}
    .coach-ring.none{box-shadow:0 0 0 9999px #0004;animation:none}
    .coach-tip{position:fixed;z-index:9991;width:320px;background:var(--panel);color:var(--text);border:1px solid var(--gold);border-radius:12px;
      padding:13px 15px 11px;box-shadow:0 12px 40px #000a;font-size:13.5px;line-height:1.5;transition:left .25s ease,top .25s ease}
    .coach-tip b{display:block;font-family:Cinzel,serif;color:var(--gold2);font-size:16px;margin-bottom:3px}
    .coach-tip .coach-prog{font-size:12.5px} .coach-tip .coach-prog b{display:inline;font-family:inherit;font-size:inherit;color:var(--text-b);margin:0}
    .coach-tip .foot{display:flex;align-items:center;gap:8px;margin-top:10px}
    .coach-tip .foot .msg{margin-right:auto;font-size:12px}`;
  document.head.appendChild(css);
  COACH.ring = document.createElement('div'); COACH.ring.className = 'coach-ring';
  COACH.tip = document.createElement('div'); COACH.tip.className = 'coach-tip';
  document.body.append(COACH.ring, COACH.tip);
  COACH.tip.addEventListener('click', e => {
    const b = e.target.closest('[data-coach]'); if (!b) return;
    if (b.dataset.coach === 'skip' || b.dataset.coach === 'end') coachEnd();
    else coachNext();
  });
  showView('guide');
  coachNext();
  COACH.timer = setInterval(coachTick, 250);
  window.addEventListener('resize', coachPlace);
}

function coachNext(){
  for (COACH.n++; COACH.n < COACH_STEPS.length; COACH.n++){
    const s = COACH_STEPS[COACH.n];
    if (!(s.skip && s.skip())) break;
    COACH.skipped++;                     // (a step already done, like having a mod open, isn't counted)
  }
  const s = COACH_STEPS[COACH.n];
  if (!s) return coachEnd(true);
  if (s.start) s.start();
  COACH.busy = false;
  COACH.seen = null;                   // (what it points at is scrolled into view once it's there)
  const shown = COACH.n + 1 - COACH.skipped, all = COACH_STEPS.length - COACH.skipped;
  COACH.tip.innerHTML = `<b>${esc(s.title)}</b><div>${esc(s.text)}</div>
    <div class="foot"><span class="msg">${shown} of ${all}</span>
      ${s.last ? '<button class="btn sm primary" data-coach="end">Done</button>' : `<button class="btn sm" data-coach="skip">Skip the tour</button>${s.next ? '<button class="btn sm primary" data-coach="next">Next</button>' : ''}`}</div>`;
  coachPlace();
}

function coachTick(){
  if (!COACH.on) return;
  const s = COACH_STEPS[COACH.n];
  if (s && s.done && s.done()) return coachNext();
  if (s && s.busy) coachBusy(s, s.busy());
  coachPlace();
}

// a step's "working on it" state: its own words and a copy of the page's progress (with its bar), kept up to date
function coachBusy(s, on){
  if (on === !!COACH.busy && !on) return;
  COACH.busy = on;
  const shown = COACH.n + 1 - COACH.skipped, all = COACH_STEPS.length - COACH.skipped;
  if (!on){ COACH.n--; return coachNext(); }      // (back to the step as it was: the build stopped with an error)
  const src = s.busyAt && s.busyAt(), prog = src ? src.innerHTML : '';
  COACH.tip.innerHTML = `<b>${esc(s.busyTitle)}</b><div>${esc(s.busyText)}</div>
    <div class="coach-prog" style="margin-top:8px">${prog || '<span class="spin"></span>Working…'}</div>
    <div class="foot"><span class="msg">${shown} of ${all}</span><button class="btn sm" data-coach="skip">Skip the tour</button></div>`;
}

// the ring round the button to press, and the tip beside it (below it if there's room, else above; with
// nothing to point at, or what it points at not on screen, the tip sits low in the middle)
function coachPlace(){
  if (!COACH.on) return;
  const s = COACH_STEPS[COACH.n]; if (!s) return;
  // (while it works: no ring on the button, and the tip low in the middle, clear of the page's own note)
  const el = COACH.busy ? null : s.at && s.at(), tip = COACH.tip, ring = COACH.ring;
  if (el && el !== COACH.seen && el.offsetParent !== null){ COACH.seen = el; el.scrollIntoView({block: 'nearest'}); }
  const r = el && el.offsetParent !== null ? el.getBoundingClientRect() : null;
  const tw = tip.offsetWidth, th = tip.offsetHeight, W0 = innerWidth, H0 = innerHeight;
  if (!r || r.width === 0 || r.bottom < 0 || r.top > H0){
    ring.className = 'coach-ring none'; Object.assign(ring.style, {left: '50%', top: '50%', width: '0px', height: '0px'});
    tip.style.left = (W0 - tw) / 2 + 'px'; tip.style.top = (H0 - th - 60) + 'px';
    return;
  }
  ring.className = 'coach-ring';
  Object.assign(ring.style, {left: r.left - 5 + 'px', top: r.top - 5 + 'px', width: r.width + 10 + 'px', height: r.height + 10 + 'px'});
  let x = Math.max(12, Math.min(W0 - tw - 12, r.left + r.width / 2 - tw / 2));
  // (below it, unless the step says above, so the tip doesn't cover the field that comes next)
  let y = s.above && r.top - th - 16 >= 12 ? r.top - th - 16 : r.bottom + 16;
  if (y + th > H0 - 12) y = r.top - th - 16;
  // (a big target, like the room planner: the tip goes inside its top corner instead)
  if (y < 12){ y = Math.max(12, r.top + 12); x = Math.max(12, Math.min(W0 - tw - 12, r.right - tw - 12)); }
  // (a small button down the page: beside it, on its right, where it covers least of the form round it)
  else if (r.top > 140 && r.width < 220 && r.right + 16 + tw < W0 - 12){
    x = r.right + 16; y = Math.max(12, Math.min(H0 - th - 12, r.top + r.height / 2 - th / 2));
  }
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}

function coachEnd(finished){
  if (!COACH.on) return;
  COACH.on = false; clearInterval(COACH.timer);
  window.removeEventListener('resize', coachPlace);
  for (const el of [COACH.ring, COACH.tip, $('#coach-css')]) if (el) el.remove();
  if (finished) toast('That\'s the tour. Home (the logo, top left) has it again any time.');
}
