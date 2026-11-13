"""A made dungeon's one story: who holds it and why, what they keep that says so, and a note that says it too.

The user, 2026-11-12, planning the night's work on dungeons: "maybe there are other principles we can incorporate to
good dungeon craft that we haven't considered yet". The first agreed on: a reason to be there. A made dungeon had its
band, their camp and a prize, each drawn on its own; nothing in it said why these people were here.

What the game's own bands keep that the others don't (lab dn11, 2026-11-12: its 510 dungeons with two or more people
who fight on sight, by the kind of band castsurvey.band_kind gives them; the share of the band's places with the
thing, against the share of every other band's):

- smugglers (29 places): moon sugar carried 24% against 2%, a sack of it 24/4, skooma 31/10, a skooma crate 21/2,
  Dwemer artifacts 24/5 and bowls 17/3, Cyrodilic whiskey 28/9, local brew 48/24;
- bandits (262): bandit crates 31/7 and barrels 20/6, a moon sugar barrel 14/3, tiki torches 62/24, a fire pit 30/8;
- necromancers (19): a mortar 42/8, greater soul gems 37/8, lesser 32/5, skulls 37/15, Darkest Darkness 32/3, the
  corpse preparation books 26/1, quill and inkwell 32/11;
- worshippers (138): braziers 70/1, the chant 62/1, skulls 30/11, emeralds 22/8, greater soul gems 19/5, the Book of
  Daedra 14/1, a Daedra's heart 13/2 (and a cursed ruby 12/0, which is a trap of the game's own: left out);
- cultists (27): corprus meat carried 96/0, ash statues 56/0, their bells and candles 63/0;
- mages (24): scroll urns 46/6, ingredient urns 42/2, conjuration books 29/2, rings and potions;
- vampires (11): nothing of their own but where they live.

So each band has one or more reasons (WHY), each with the goods that say it, taken from that list, a line or two for
the people of a town near (rumours.py reads them), and a note in the band's own words. The leader carries the note
and the goods: found on the leader, as the game's own orders and letters mostly are. Kept with the place,
c['ruin']['story'], and made within the dungeon's own Undo step.
"""
import random
import struct

import mapdata

# (key, weight, goods [(id, count)], what a town near says, notes [(title, text)]). In a note: {place} the dungeon's
# name, {leader} who leads, {other} one of the others (or "the others"), {n} how many they are.
WHY = {
    'smugglers': [
        ('sugar', 0.4, [('ingred_moon_sugar_01', 4), ('potion_skooma_01', 2)],
         ["Smugglers run moon sugar through it, they say. The guards would pay well to see it cleared.",
          "It's a smugglers' den. Sugar comes in by night and goes out as skooma. Best not to ask."],
         [("Smuggler's note", "{leader},\n\nTwo sacks of sugar this time, and the vials. Keep them dry and keep them at {place} until the boat comes. Nobody sells a grain of it before then.\n\nIf the guard comes asking, you are fishermen."),
          ("Tally", "{place}. Sugar, four measures. Skooma, less what was drunk on the way.\n\nThe buyer pays on the new moon. Count it twice.")]),
        ('dwemer', 0.3, [('misc_dwrv_artifact60', 1), ('misc_dwrv_bowl00', 1), ('misc_dwrv_coin00', 6)],
         ["Smugglers, moving Dwemer pieces out past the Emperor's men. There's good coin in that, and a rope if they're caught.",
          "They say there's Dwemer metal hidden in there. It's the Emperor's by law, so somebody's selling it quietly."],
         [("Smuggler's note", "{leader},\n\nThe collector wants the old metal and asks no questions. Coins, cups, anything with their marks on it. Hold it at {place}; I will send word.\n\nNot one piece goes to market. The law hangs men for this."),
          ("Tally", "Held at {place} for the collector: one piece of the old work, whole. One bowl. Coins, loose.\n\nA bigger share was asked for. Whoever asked can take it up with the collector.")]),
        ('liquor', 0.3, [('potion_cyro_whiskey_01', 3), ('potion_cyro_brandy_01', 2), ('Potion_Local_Brew_01', 2)],
         ["Smugglers. Drink, mostly, brought in without the Emperor's stamp. Half the taverns round here buy from them.",
          "A smugglers' den. Whiskey and brandy with no tax paid on it. Nobody minds much, except the excise."],
         [("Smuggler's note", "{leader},\n\nThe whiskey is for the taverns, the brandy for the one who pays in advance. Keep both at {place} and keep {other} out of the crates.\n\nNo stamps, no questions, same price as before."),
          ("Tally", "{place}. Whiskey, brandy, and the local stuff nobody will pay for.\n\nOwed to us: two taverns. Owed by us: nothing, for once.")]),
    ],
    'bandits': [
        ('road', 0.8, [('ingred_ruby_01', 1), ('ingred_pearl_01', 2), ('expensive_ring_01', 1), ('Gold_010', 3)],
         ["Bandits have holed up there. Nobody takes that way alone any more.",
          "There's a band of cutthroats in there now. They rob the road and carry it all back to that hole."],
         [("Scrawled note", "{leader},\n\nA trader's cart comes by every few days and never with more than two guards. We take it on the road and are back at {place} before anyone is missed.\n\nThe rings and stones are easy to carry. Leave the cloth."),
          ("Shares", "{place}. Split {n} ways, {leader} two shares.\n\nThe ruby is not to be sold near here. Somebody will know it.")]),
        ('sugar', 0.2, [('ingred_moon_sugar_01', 3), ('Gold_010', 2)],
         ["Outlaws. They took a smuggler's sugar off him on the road and mean to sell it themselves.",
          "Bandits, sitting on somebody else's moon sugar. Sooner or later its owners will come for it."],
         [("Scrawled note", "{leader},\n\nThe sugar is not ours and the ones we took it from know our faces. We sell it fast or we do not sell it. Until then it stays at {place} and so do we.")]),
    ],
    'necromancers': [
        ('dead', 1.0, [('misc_soulgem_lesser', 1), ('misc_soulgem_common', 1), ('ingred_bonemeal_01', 3), ('bk_darkestdarkness', 1)],
         ["There are lights there at night, and things walking that shouldn't. A necromancer, I'd wager.",
          "Someone's been at the dead out there. Graves opened, and nothing left in them. The Temple won't go near it."],
         [("Working notes", "{place}.\n\nThe third one stood for most of a night before it fell apart. The fault is in the preparation, not the binding: older bones hold better than fresh.\n\nMore bonemeal. More gems. Fewer visitors."),
          ("Working notes", "They will call it desecration. They said the same of every art before it was taught in their guildhalls.\n\n{place} is quiet and the dead here are many. I need nothing else, except that the door is kept.")]),
    ],
    'worshippers': [
        ('shrine', 1.0, [('ingred_daedras_heart_01', 1), ('ingred_emerald_01', 1), ('misc_skull00', 1), ('bookskill_conjuration1', 1)],
         ["Daedra worshippers. They keep to themselves, but folk who go looking don't come back.",
          "A cult, they say. They bring offerings up there, and not all of the offerings go willingly."],
         [("Devotions", "On the day of summoning the offering is laid before the altar at {place}: a heart, a stone of price, and the bones of one who doubted.\n\n{leader} speaks the words. The rest of us are silent, and afterwards we do not speak of it."),
          ("Devotions", "{leader},\n\nThe Temple names us heretics, and the Empire would rather we were only thieves. Let them both think what they like. At {place} we are answered when we call.\n\nBring the stone. I have the rest.")]),
    ],
    'cultists': [
        ('house', 1.0, [('misc_6th_ash_statue_01', 1), ('ingred_6th_corprusmeat_01', 2)],
         ["Sleepers went up there and didn't come back down. People say they dream the same dream, all of them.",
          "The ones who went there aren't themselves any more. Ash on everything. Keep away from it."],
         [("Ash-stained page", "He has spoken to me in the dream and I have come to {place} as I was told.\n\nThe others are here. We do not sleep. We keep the statue and we wait, and the flesh changes as he promised it would.")]),
    ],
    'mages': [
        ('study', 1.0, [('misc_soulgem_common', 1), ('sc_summonskeletalservant', 1), ('p_restore_magicka_c', 2), ('bookskill_conjuration2', 1)],
         ["A wizard has shut himself up in there, away from his guild. Whatever he's working at, he doesn't want it seen.",
          "Mages, and not the Guild's. They went there to study something the Guild wouldn't allow."],
         [("Notes", "{place} will do. Nobody comes here, and what I call up cannot get far if it slips me.\n\nThe Guild would have me fill in forms. Here I have {other} to carry water and nobody to say no."),
          ("Notes", "{leader},\n\nI have the gems you asked for and one of the scrolls. The other is not to be had for any money. Do not try the working without it.\n\nI will come to {place} when the roads are dry.")]),
    ],
    'vampires': [
        ('lair', 1.0, [('Gold_025', 2)],
         ["People have gone missing near there. They find the cattle first, drained, and then they stop looking.",
          "Something sleeps in there by day. Don't be near it when the light goes."],
         [("Stained note", "{leader},\n\nNo more taken from the same village. They count their own, and they have begun to carry torches.\n\nGo further for it, or go hungry. {place} is too good a den to lose.")]),
    ],
}


def _exists(db, rid):
    """Whether the load order has the thing, and with no script on it (a scripted one may be a trap or a quest's)."""
    ri = db.resolve_id(rid)
    if ri is None or db.recs[ri][0] not in ('MISC', 'INGR', 'ALCH', 'BOOK', 'CLOT', 'WEAP', 'ARMO', 'APPA', 'LIGH'):
        return False
    try:
        from esm import iter_subrecords
        r = db.recs[ri]
        _t, _f, data = db.files[r[3]].record_at(r[4])
        return not any(t == 'SCRI' for t, _d in iter_subrecords(data))
    except Exception:
        return True


def band_of(db, key):
    """(band, [person dicts, the leader first]) of the people this mod placed in the place who fight on sight, or
    (None, []) with fewer than one. The band as the game's own are told apart, castsurvey.band_kind."""
    import castsurvey
    m = mapdata.cellmap(db, key)
    setting = castsurvey.setting_of(db, m.get('name') or key, [r['id'] for r in m['refs']])[0]
    ps = []
    for r in m['refs']:
        if r['type'] != 'NPC_':
            continue
        ri = db.resolve_id(r['id'])
        if ri is None or not (db.project.records.get('NPC_|' + r['id'].lower()) or {}).get('created'):
            continue
        o = castsurvey.person(db, ri)
        if o['fight'] >= castsurvey.HOSTILE:
            ps.append(o)
    if not ps:
        return None, []
    ps.sort(key=lambda o: -o['level'])
    return castsurvey.band_kind(ps, setting), ps


def _carry(db, npc_id, things):
    """Things [(id, count)] added to one of the mod's own people's inventory."""
    from esm import ENC, iter_subrecords
    from project import join_subs
    ri = db.resolve_id(npc_id)
    r = db.recs[ri]
    _t, flags, data = db.files[r[3]].record_at(r[4])
    subs = [(t, bytes(v)) for t, v in iter_subrecords(data)]
    idx = max([n + 1 for n, (t, _v) in enumerate(subs) if t == 'NPCO'] or
              [n + 1 for n, (t, _v) in enumerate(subs) if t in ('NPDT', 'FLAG')] or [len(subs)])
    for rid, n in things:
        subs.insert(idx, ('NPCO', struct.pack('<i', int(n)) + rid.encode(ENC, 'replace')[:31].ljust(32, b'\0')))
        idx += 1
    db.project.set_record(r[0], r[7], flags & ~0x20, join_subs(subs),
                          created=bool((db.project.records.get(r[0] + '|' + r[7]) or {}).get('created')))


def _note(db, title, text):
    """A new note of the mod's with that title and text; its id, or None when the load order has no note to model it on."""
    import create
    from esm import ENC
    from project import join_subs, zs
    look = create._book_look(db, create.BOOK_KINDS['Note'])
    if not look:
        return None
    model, icon, weight, value, scroll = look
    new_id = create._check_id(db, 'BOOK', create.suggest_id(db, create._prefix(db), title))
    subs = [('NAME', zs(new_id)), ('MODL', model), ('FNAM', zs(title[:31])),
            ('BKDT', struct.pack('<fiiii', weight, 0, scroll, -1, 0)), ('ITEX', icon),
            ('TEXT', create.book_html(text).encode(ENC, 'replace'))]
    db.project.set_record('BOOK', new_id.lower(), 0, join_subs(subs), created=True)
    return new_id


def tell(db, key, seed=0):
    """The story of the dungeon just built and peopled: its band's reason for being there chosen (WHY, at the weights
    given), a note of it written and given to the band's leader with the goods that say the same, and all of it kept
    with the place. No Undo step of its own (the caller commits). Returns the story, or None for a place with no
    band (nobody, a household, beasts alone: what happened there is told by what lies about, livedin.py)."""
    p = db.project
    c = (getattr(p, 'cells', None) or {}).get(key)
    if not isinstance(c, dict) or not isinstance(c.get('ruin'), dict):
        return None
    band, ps = band_of(db, key)
    if band not in WHY:
        return None
    rng = random.Random('%s|story|%s' % (key, seed))
    whys = WHY[band]
    r = rng.random() * sum(w[1] for w in whys)
    why = next((w for w in whys if (r := r - w[1]) <= 0), whys[-1])
    wkey, _w, goods, say, notes = why
    leader = ps[0]
    others = [o['name'] for o in ps[1:] if o.get('name')]
    name = c.get('name') or (mapdata.cellmap(db, key).get('name') or key)
    # (a note addressed to the leader was written by another of them: with nobody else there, one the leader wrote)
    pool = notes if others else ([n_ for n_ in notes if '{leader},' not in n_[1]] or notes)
    title, text = rng.choice(pool)
    text = text.format(place=name, leader=leader.get('name') or 'you', other=rng.choice(others) if others else 'the others', n=len(ps))
    carried = [(rid, n) for rid, n in goods if _exists(db, rid)]
    note = _note(db, title, text)
    db.sync_project()
    if note:
        carried = [(note, 1)] + carried
    if carried:
        _carry(db, leader['id'], carried)
    story = {'band': band, 'why': wkey, 'leader': leader['id'], 'leader_name': leader.get('name') or '', 'people': len(ps),
             'note': note, 'title': title, 'text': text, 'goods': [[rid, n] for rid, n in carried if rid != note], 'say': list(say)}
    c['ruin']['story'] = story
    db.sync_project()
    return story


def of(db, name):
    """The story kept with a made dungeon, by its name, or None."""
    c = (getattr(getattr(db, 'project', None), 'cells', None) or {}).get((name or '').lower())
    s = (c.get('ruin') or {}).get('story') if isinstance(c, dict) and isinstance(c.get('ruin'), dict) else None
    return s if isinstance(s, dict) else None
