// ---------- Each kind of record opens in the page made for working on it ----------
// Browse finds anything; it is not where you work on a thing (the user: "Browse is good to have as an absolute
// record finder, but it isn't a good interface to use for working on any specific task"). So whatever is made,
// found or followed (Create's results, Ctrl+K, a used-by list, the right-click menu) opens in its own page: an
// item in the item editor, a person in Characters, a list in Lists, a topic or quest in Dialogue, a script in
// Scripts, a faction or a region in Rules, a place on the World map. Browse is left for the kinds with no page.

const OT_ITEMS = 'WEAP,ARMO,CLOT,ALCH,INGR,MISC,LIGH,LOCK,PROB,REPA,APPA,BOOK,SPEL,ENCH'.split(',');
// (a skill's or a magic effect's record ID is its number, "20" Acrobatics, "79" Fortify Attribute: the same
// numbers the Rules page's lists go by)
const OT_RULES = {FACT: 'faction', CLAS: 'class', RACE: 'race', BSGN: 'birthsign', GLOB: 'global', REGN: 'region', SOUN: 'sound',
                  SKIL: 'skill', MGEF: 'effect'};

// the page a kind of record is worked on in: {label, run(i, id)}, or null for Browse
function otTool(type){
  if (OT_ITEMS.includes(type)) return {label: 'the item editor', run: (i, id) => ieShow(id)};
  if (type === 'NPC_' || type === 'CREA') return {label: 'Characters', run: (i, id) => cOpen(id)};
  if (type === 'LEVI' || type === 'LEVC') return {label: 'Lists', run: (i, id) => lvOpen(id)};
  if (type === 'SCPT') return {label: 'Scripts', run: (i, id) => sOpen(id)};
  if (OT_RULES[type]) return {label: 'Rules', run: (i, id) => ruShow(OT_RULES[type], id)};
  // (game settings are one long list there: opened searched for this one)
  if (type === 'GMST') return {label: 'Rules', run: (i, id) => { RU.gq = id; RU.goff = 0; RU.gall = false; ruShow('gmst'); }};
  if (type === 'CELL') return {label: 'the World map', run: async i => { showView('world'); await worldOpenIndex(i); }};
  if (type === 'DIAL') return {label: 'Dialogue', run: async (i, id) => {
    // (a journal is a quest there, everything else a topic: the record says which)
    let quest = false;
    try { const d = await api('/api/record?i=' + i); quest = (d.fields || []).some(f => f.label === 'Dialogue Type' && f.value === 'Journal'); } catch (e){}
    showView('dialog'); await dOpen(quest ? 'quest' : 'topic', String(id).toLowerCase());
  }};
  return null;
}

// open a record where it is worked on; with no page for its kind, in Browse (type and id are looked up when
// only the record's number is known)
async function openTool(i, type, id){
  if ((!type || !id || type === 'INFO') && i != null){
    try {
      const d = await api('/api/record?i=' + i); type = type || d.type; id = id || d.id;
      // (a line of dialogue opens its topic or quest in Dialogue)
      if (type === 'INFO' && d.topic && d.topic.i != null) return openTool(d.topic.i, 'DIAL', d.topic.id);
    } catch (e){}
  }
  const t = type && otTool(type);
  if (t && id){
    try { await t.run(i, id); return; }
    catch (e){ console.warn('openTool', type, id, e); }
  }
  showView('browse'); openRecord(i, true);
}
