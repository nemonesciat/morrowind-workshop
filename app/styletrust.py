"""How far the Workshop trusts itself in each building style: stars (1 to 5) and the reason, for the
style picker. Written by hand from the evidence at 2026-10-21, not computed: how many of the game's
own places teach the style (kits uses), how many rounds of the user's in-game feedback it has been
through, what the lab's two-floor test house and the gap finder say, and which of its pieces the
builder still can't do justice to. Update the table when a style is tuned or a new one is surveyed.

Stars: 5 = walks clean in the game and looks like the game's own; 4 = builds and furnishes clean in the
lab, few or no in-game rounds; 3 = builds, with known rough edges; 2 = builds, but untuned or with the
game's stairs missing; 1 = nothing of the game's to learn from, or known to look wrong."""

TRUST = {
    # vanilla
    'in_hlaalu': (5, 'The most-taught style (6,300 places), tuned over the most in-game rounds: stairwell of hall corners, posts only where the game stands them, the planner presets built in it.'),
    'in_c_plain': (5, 'Common plain: the tall one-piece stairwell, pillars at every stair corner, jamb stubs covered, walked clean in the game.'),
    'in_c_stone': (5, 'Common stone: as Common plain, walked over several houses; the last two gaps (stairwell wall ends) are closed.'),
    'in_c_rich': (4, 'Common rich: builds clean in the lab; its stairs are borrowed from the family and have had no in-game round of their own.'),
    'in_c_thatch': (3, 'Common thatch: builds, but its stair pieces are not the kit\'s own and the kit prefers pieces with ceilings; one lab round only.'),
    't_de_setind_i': (4, 'Indoril: alcove stairs and caps learnt from the game, loose walls, clean in the lab; walked in the game once (the user liked it).'),
    't_de_setind_i_cha': (3, 'Indoril chapel: builds and looks right in 3D, but the gap finder counts about eleven slits round its open stairwell.'),
    'in_mh_int': (3, 'Mournhold: floors joined by doors as its houses are, front doorway now the game\'s own; no stairs, no in-game round.'),
    'in_r_s_int': (3, 'Redoran small: ramps as stairs, round rooms; the kit has no three-walled piece, so one-tile rooms can\'t close; no in-game round.'),
    'in_r_l_int': (2, 'Redoran large: only 45 game places teach it; the open stairwell leaves about eleven slits; untested in the game.'),
    'in_t_s': (3, 'Telvanni small: builds; its ramps are hall pieces (Telvanni levitate), so floors default to doors; no in-game round.'),
    'in_v_s_int': (2, 'Vivec small: canton rooms, no stairs and no doorway piece; corner tiles read as walled-off one-tile rooms.'),
    'in_impsmall_r': (3, 'Imperial small rich: one floor only (no stairs); its front doorway is now the game\'s own; no in-game round.'),
    'in_stronghold': (2, 'Stronghold: loose walls only, no stairs, no doorway piece; builds a plain box.'),
    'in_m_sewer': (2, 'Mournhold sewer: builds a tunnel; nothing of a house to learn from it.'),
    # Tamriel Data
    't_imp_setgc_i': (5, 'Gold Coast: stairs under arches and stacked switchbacks, pillars at every stair corner, no flickering floors, walked clean over a five-storey house.'),
    't_imp_setgc_i@wallrichaddon': (3, 'Anvil\'s pale ashlar: the Gold Coast kit under its panels, surveyed from Anvil tonight; galleries and columns not yet built; no in-game round.'),
    't_imp_setgc_i@wallstoneaddon': (3, 'Anvil\'s grey stone: as the ashlar; the round stair tower is not built.'),
    't_de_sethla_i': (4, 'Tamriel Data Hlaalu manor: floor slabs under floorless walls, learnt from 1,400 places; no stairs of its own; one in-game round.'),
    't_de_sethla_i_sewerl': (2, 'Hlaalu sewer: builds a tunnel with its stairs; not a house.'),
    't_de_setnecrom_i': (3, 'Necrom: clean in the lab, doorway pieces; no stairs; no in-game round.'),
    't_de_setdres_i': (2, 'Dres: only 61 game places; no stairs; the Dres door is only partly covered by the kit\'s doorway.'),
    't_imp_legioncyr_i': (3, 'Legion fort (Cyrodiil): builds with its own stairs; no in-game round; a fort, not a house.'),
    't_imp_setchapel_i': (2, 'Imperial chapel: stairs the builder can\'t stand properly; a chapel, not a house.'),
    't_imp_legionsky_i': (1, 'No place in your game is built in it: nothing to learn doorways, stairs or furnishing from.'),
    't_imp_setkvaurb_i': (1, 'No place in your game is built in it.'),
    't_imp_setstr_i': (1, 'No place in your game is built in it.'),
    't_nor_sethaafps_i': (1, 'No place in your game is built in it.'),
    't_nor_sethaafpw_i': (1, 'No place in your game is built in it.'),
    't_rga_setrihada_i': (1, 'No place in your game is built in it.'),
    't_rga_setrihadb_i': (1, 'No place in your game is built in it.'),
    't_rga_setrihadc_i': (1, 'No place in your game is built in it.'),
}


def rate(style_id, uses=None):
    """(stars, reason) for a style; a style not in the table goes by whether the game teaches it."""
    t = TRUST.get(style_id) or TRUST.get(style_id.split('@')[0])
    if t:
        return {'stars': t[0], 'why': t[1]}
    if not uses:
        return {'stars': 1, 'why': 'No place in your game is built in it: nothing to learn from.'}
    return {'stars': 2, 'why': 'Builds, but has not been surveyed or walked in the game yet.'}


def table(styles):
    """The picker's styles with their stars, best first (for the write-up and the lab)."""
    rows = [dict(s, **rate(s['id'], s.get('uses'))) for s in styles]
    rows.sort(key=lambda r: (-r['stars'], -(r.get('uses') or 0)))
    return rows
