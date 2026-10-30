"""Their own words: lines for the people Populate makes, written offline from templates (2026-10-23).

Each person gets a greeting for the first meeting and one for later, a line on "my trade" in the words of
their occupation, lines on "someone in particular" about the people they live or work with (their kin, the
household's head, its servants, a friend or a rival), a "little secret" told only to someone they like,
and a rumour about the place. The templates are in Morrowind's own manner (Dunmer call strangers
outlanders and swear by the Three; Imperials by the Nine; Nords by Shor; a Khajiit speaks of himself as
"this one"), and every line can be changed afterwards like any other. Nothing here asks the Assistant."""
import re

# ---------------------------------------------------------------- how people speak
OATHS = {'dark elf': ('By the Three', 'Almsivi preserve us', 'Ancestors guide me', 'Three blessings'),
         'imperial': ('By the Nine', 'Gods preserve us', 'By Akatosh', 'Stendarr keep us'),
         'breton': ('By the Nine', 'Gods preserve us', 'By Julianos'),
         'nord': ("Shor's bones", 'By Ysmir', "Talos guide me", "By Kyne's breath"),
         'redguard': ('By the HoonDing', 'Tava keep us', 'By the Nine'),
         'high elf': ('By Auri-El', 'By the Eight', 'The Divines preserve us'),
         'wood elf': ('By Y\'ffre', 'By the Green', 'Y\'ffre keep us'),
         'orc': ("By Malacath", "Malacath's teeth", 'By the Code'),
         'khajiit': ('By the Moons', 'Bright Moons guide us', "By Jone and Jode"),
         'argonian': ('By the Hist', 'The Hist keep us', 'By the roots')}
STRANGER = {'dark elf': ('outlander', 'stranger', 'traveler', 'friend'), 'nord': ('friend', 'stranger', 'traveler'),
            'orc': ('stranger', 'traveler'), 'khajiit': ('friend', 'walker'), 'argonian': ('warm-skin', 'traveler', 'friend')}

# ---------------------------------------------------------------- greetings
# (by tone: who they are; {s} a word for a stranger, {oath} an oath, {place}, {town}, {first})
GREET_FIRST = {
    'common': ["Yes? What do you want?", "Hm? I don't know you, {s}.", "Something you need, {s}?", "Not often I see a new face in {town}.",
               "Well met. I'm {first}. Can I help you?", "You're not from around here, are you?", "Mind where you step. What is it?",
               "{oath}, you gave me a start. What is it you want?", "Greetings. You look like you've come a long way."],
    'poor': ["Spare a few drakes? No? Then what do you want?", "Leave me be, unless you've coin.", "I've nothing worth stealing, {s}.",
             "Another one who wants something from me. Speak, then.", "What? Oh. I thought you were the landlord."],
    'noble': ["You are standing in my house, {s}. I trust you have a reason.", "I don't recall inviting you. Speak quickly.",
              "Ah, a visitor. How unexpected. And you are?", "If you have business with me, state it. My time is not cheap.",
              "{oath}. Another petitioner. Very well, what is it?"],
    'trader': ["Welcome, welcome. Looking to buy, or to sell?", "Good day. Everything you see is for sale, at a fair price.",
               "Come in, {s}. You won't find better wares in {town}.", "A customer! Have a look around. Touch nothing you can't pay for.",
               "Greetings. I'm {first}. What can I do for you today?"],
    'publican': ["Welcome to {place}. A drink? A bed? Both?", "Come in out of the dust. What'll it be?", "Pull up a stool, {s}. First mug's not free, mind.",
                 "Another thirsty traveler. Good. What are you drinking?"],
    'guard': ["Keep your weapons sheathed and we'll get along.", "Move along, {s}. Unless you've business here.", "Halt. State your business.",
              "I'm watching you. Don't make trouble.", "Citizen. Something to report?"],
    'priest': ["Blessings upon you, pilgrim. What brings you here?", "Peace be with you. Do you seek counsel, or healing?",
               "Welcome to this holy place. Walk softly.", "{oath}. Come, child. What troubles you?"],
    'scholar': ["Hm? Oh. I was reading. What is it?", "If this is about the noise, it wasn't me.", "You've interrupted a very delicate train of thought.",
                "Ah, someone new. Are you a reader, by any chance?"],
    'fighter': ["You look like you can handle yourself. Good.", "Looking for a sword-arm? I'm not cheap.", "What do you want? Make it quick.",
                "Hm. You've seen a fight or two, I'd guess."],
    'servant': ["Yes, sera? Is there something you need?", "Please, I'm only a servant here. Ask my master.", "Sorry, I didn't see you there.",
                "I'm not supposed to talk to visitors. What is it?"],
    'outlaw': ["Wrong place to wander into, {s}.", "Who sent you? Speak, before I lose my patience.", "Turn around and walk out. Now.",
               "You don't look like one of us."],
}
GREET_AGAIN = {
    'common': ["You again. What now?", "Back so soon?", "Ah, {pc}. What is it this time?", "Yes? I'm still here.", "Something else?"],
    'poor': ["Back with coin this time?", "Still here, still poor. What do you want?", "You again."],
    'noble': ["You return. I suppose you want something.", "Ah, {pc}. Make it brief.", "Yes, yes. What is it now?"],
    'trader': ["Back again! Good. What will it be?", "Ah, my favorite customer. Well, one of them.", "Welcome back, {pc}."],
    'publican': ["Back for another? Sit, sit.", "The usual, {pc}?", "Can't stay away, can you?"],
    'guard': ["You again. Behaving yourself?", "Keep out of trouble, {pc}.", "Still here, citizen?"],
    'priest': ["Welcome back, {pc}. The Three keep you.", "Peace, friend. You've returned.", "Blessings again upon you."],
    'scholar': ["Ah, you again. Interesting.", "Back? Mind the books.", "You've returned. Splendid. Or not. What is it?"],
    'fighter': ["Still breathing, I see.", "Back again. Looking for work?", "What now?"],
    'servant': ["Sera. How may I help you?", "Welcome back. The master is about somewhere.", "Yes, sera?"],
    'outlaw': ["Still alive? Lucky.", "You keep coming back. I don't like it.", "What now?"],
}

# ---------------------------------------------------------------- my trade
# (by words of their class; first match wins)
TRADES = [
    (('publican',), ["I keep {place}. Beds upstairs, drink down here, and no fighting in between.",
                     "I run {place}. Mostly I listen to people complain and pour them another.",
                     "Publican. It's honest work, as long as you count the coins twice."]),
    (('smith', 'armorer'), ["I'm a smith. Iron, steel, a little silver when I can get it. Bring me what's broken.",
                            "I hammer metal into shapes people pay for. Repairs, mostly. Nobody here can afford new steel.",
                            "Smithing. Hot, loud, and I wouldn't do anything else."]),
    (('clothier', 'tailor', 'outfitter'), ["I make and sell clothes. You could do with something better than that, if I may say so.",
                                          "Clothier. A good shirt says more about you than a good sword.",
                                          "I dress half of {town}, and the other half should come and see me."]),
    (('apothecary', 'alchemist'), ["Potions, ingredients, cures. Mind the jars on the left. Some of them bite.",
                                  "I'm an apothecary. If it ails you, I probably have something for it. If it kills you, I don't.",
                                  "Alchemy is patience, and a nose for what's gone bad."]),
    (('enchanter',), ["I bind souls to things. It sounds worse than it is.",
                      "Enchanting. Bring me a filled soul gem and something worth enchanting, and we'll talk.",
                      "I put magic into objects. Rings, mostly. People do love a ring."]),
    (('bookseller', 'scribe', 'savant'), ["Books. I buy them, I sell them, I read them when nobody's looking.",
                                         "I deal in books and papers. Knowledge is the one thing that doesn't spoil.",
                                         "I copy, I keep, I sell. Words, mostly."]),
    (('pawnbroker',), ["I buy what people don't need and sell it to people who do. Everyone wins, mostly me.",
                       "Pawnbroker. Bring me anything. I'll give you something for it."]),
    (('trader', 'merchant'), ["I'm a trader. If you have something to sell, I'll look at it. If you need something, I probably have it.",
                              "Trade keeps {town} alive. I buy, I sell, I try not to get robbed.",
                              "Merchant. Buy low, sell high, and never let them see you smile."]),
    (('healer', 'priest', 'monk', 'acolyte', 'cleric'), ["I serve the Temple, and I tend to those who come here hurting.",
                                                         "I pray, I heal, I listen. The third is the hardest.",
                                                         "My duty is to the faithful. And to the unfaithful too, if they're bleeding."]),
    (('guard', 'ordinator', 'legion', 'warden', 'watch'), ["I keep the peace here. Mostly by standing where people can see me.",
                                                          "Guard. I stand, I watch, I stop trouble before it starts.",
                                                          "I keep order. You'd be surprised how much disorder there is in {town}."]),
    (('miner',), ["I dig. Ebony if we're lucky, rock if we're not. Mostly rock.",
                  "Mining. My back's ruined and my lungs aren't far behind."]),
    (('farmer', 'herder'), ["I work the land. Saltrice, mostly, and the guar don't feed themselves.",
                            "Farming. Up before the sun, to bed after it. Same as every day."]),
    (('fisher', 'sailor', 'shipmaster'), ["I work the water. Fish, cargo, whatever pays.",
                                          "The sea's my trade. It's cruel, but it's honest about it."]),
    (('hunter', 'scout'), ["I hunt. Hides and meat, mostly, and whatever the guilds will pay for.",
                           "I know the wilds around {town} better than anyone in it."]),
    (('mage', 'wizard', 'sorcerer', 'battlemage', 'conjurer', 'spellsword', 'witch', 'healer'), ["I study the arts. It's less glamorous than it sounds.",
                                                                                               "Magic. Years of study for one good spell, and then you start again."]),
    (('noble',), ["My family's affairs keep me busy enough. Not that I'd expect you to understand.",
                  "Trade? I don't have a trade. I have interests."]),
    (('servant', 'slave'), ["I serve this house. Cooking, cleaning, whatever I'm told.",
                            "I do as I'm told. It's safer that way."]),
    (('pauper', 'beggar'), ["Trade? I beg. Some days I eat.", "Nobody pays for what I do, which is mostly waiting."]),
    (('warrior', 'barbarian', 'knight', 'crusader', 'mercenary', 'champion', 'drillmaster', 'master-at-arms'),
     ["I fight for whoever pays. Right now, nobody's paying.", "Sword-work. It's the only thing I've ever been any good at."]),
    (('thief', 'smuggler', 'rogue', 'agent', 'nightblade', 'assassin', 'acrobat'),
     ["My trade is my own business.", "I move things from where they are to where they're wanted. Don't ask what."]),
    (('pilgrim',), ["I walk from shrine to shrine. My feet hate me.", "I'm on pilgrimage. The road is the prayer, they say."]),
    (('commoner', 'baker', 'caretaker', 'laborer', 'labourer', 'worker'),
     ["Bits of everything. Whatever puts food on the table.", "I work. Same as everyone in {town}."]),
]
TRADE_ANY = ["I get by. That's about all I can say for it.", "Work is work. I do what I'm paid for.",
             "Nothing you'd find interesting, {s}."]

# ---------------------------------------------------------------- someone in particular
# (about another person of the cast; {o} their name, {of} their first name, {ot} what they do, {he} {his} {him})
ABOUT_KIN = {
    'spouse': ["{of} is my {kin}. {He} has more patience with me than I deserve.", "My {kin}, {of}. Don't tell {him} I said so, but {he}'s the clever one.",
               "You'll want my {kin}, {of}, if it's anything to do with money."],
    'sibling': ["{of}? My {kin}. We fight like guar, but family is family.", "My {kin} {of} lives here too. {He} {ot}.",
                "Ask my {kin}, {of}. {He} remembers everything, especially my mistakes."],
    'cousin': ["{of} is my cousin. Came to stay a season and never left.", "My cousin {of}. {He}'s all right, once you get to know {him}."],
}
ABOUT_HEAD = ["This is {o}'s house. I'd mind my manners, if I were you.", "{o} is the one in charge here. {He} {ot}.",
              "You want {o}. {He} decides everything under this roof."]
ABOUT_SERVANT = ["{of} keeps the house. {He} sees more than {he} lets on.", "That's {of}. {He} works for us. Quiet, which I like.",
                 "{of}? {He} cooks. Badly, but {he} cooks."]
ABOUT_MASTER = ["I work for {o}. {He}'s fair, mostly.", "{o} is my master. I've had worse.", "{o}? Don't cross {him}. That's all I'll say."]
ABOUT_FRIEND = ["{o} is a friend of mine. If you see {him}, tell {him} I still owe {him} a drink.", "{of}? Good sort. {He} {ot}.",
                "You've met {of}? {He}'s the only honest one around here."]
ABOUT_RIVAL = ["{o}? I'd not trust {him} with a broken spoon.", "Don't mention {of} to me. We don't speak.",
               "{of} {ot}, or claims to. I have my doubts."]
ABOUT_WORK = ["{o} {ot}. You'll find {him} about.", "Ask {of}. {He} {ot}.", "There's {o}. {He} {ot}, if you need that sort of thing."]
WHAT_THEY_DO = [
    (('publican',), 'keeps this place'), (('smith', 'armorer'), 'works the forge'), (('clothier',), 'makes clothes'),
    (('apothecary', 'alchemist'), 'mixes potions'), (('enchanter',), 'enchants things'), (('bookseller',), 'sells books'),
    (('pawnbroker',), 'buys and sells anything'), (('trader', 'merchant'), 'trades'), (('healer',), 'heals the sick'),
    (('priest', 'monk', 'acolyte'), 'serves the Temple'), (('guard', 'ordinator', 'legion'), 'keeps watch'), (('miner',), 'works the mine'),
    (('farmer', 'herder'), 'works the land'), (('fisher', 'sailor'), 'works the water'), (('hunter', 'scout'), 'hunts'),
    (('mage', 'sorcerer', 'wizard', 'battlemage', 'witch'), 'studies magic'), (('noble',), 'manages the family affairs'),
    (('servant', 'slave'), 'keeps the house'), (('pauper',), 'gets by, somehow'), (('warrior', 'barbarian', 'knight'), 'fights for coin'),
    (('thief', 'smuggler', 'rogue', 'agent'), 'keeps odd hours'), (('pilgrim',), 'is on pilgrimage'),
]

# ---------------------------------------------------------------- little secret and rumours
SECRET_ABOUT = ["Between you and me, {of} drinks more than {he} lets on.", "Don't repeat this, but {of} owes money to half of {town}.",
                "{of} talks in {his} sleep. You'd be amazed what I've heard.", "I think {of} is hiding something in {his} room. {He} keeps it locked.",
                "{of} wasn't always called {of}, if you take my meaning.", "{of} has a sweetheart in another town. Nobody's supposed to know.",
                "I've seen {of} slip out at night. Never says where {he} goes."]
SECRET_SELF = ["I've been putting a little aside. One day I'll leave {town} and never look back.",
               "I can't read. Don't tell anyone. I just nod and look serious.",
               "I'm afraid of netch. All of them. Even the small ones.",
               "I once met a Telvanni wizard. I still have nightmares about the hat."]
RUMOR_PLACE = ["They say {place} was built over something older. You can hear it some nights, if you listen.",
               "Folk say the last owner of {place} left in a hurry. Nobody knows why.",
               "There's talk of smugglers using the coast near {town}. The guards pretend not to know.",
               "A trader came through recently saying the roads past {town} aren't safe. Bandits, or worse.",
               "Prices are up all over {town}. Someone's getting rich, and it isn't me.",
               "They say there's an old tomb near {town} that nobody goes into twice."]


# ---------------------------------------------------------------- filling them in
def tone_of(p, setting):
    low = (p.get('cls') or '').lower()
    if setting in ('cave', 'hideout', 'stronghold', 'daedric', 'dwemer', 'tomb', 'ruin', 'sewer', 'tower'):
        return 'outlaw'
    for tone, words in (('publican', ('publican',)), ('guard', ('guard', 'ordinator', 'legion', 'warden')),
                        ('priest', ('priest', 'monk', 'healer', 'acolyte', 'cleric')),
                        ('servant', ('servant', 'slave')), ('poor', ('pauper', 'beggar')),
                        ('trader', ('trader', 'merchant', 'smith', 'clothier', 'apothecary', 'alchemist', 'enchanter', 'bookseller', 'pawnbroker')),
                        ('noble', ('noble',)), ('scholar', ('mage', 'scholar', 'savant', 'scribe', 'wizard', 'sorcerer', 'bookseller')),
                        ('fighter', ('warrior', 'barbarian', 'knight', 'crusader', 'mercenary', 'champion'))):
        if any(w in low for w in words):
            return tone
    if p.get('band') == 'poor':
        return 'poor'
    if p.get('band') == 'rich':
        return 'noble'
    return 'common'


def what_they_do(p):
    low = (p.get('cls') or '').lower()
    for words, t in WHAT_THEY_DO:
        if any(w in low for w in words):
            return t
    return 'lives here'


def _clean(name):
    """A place's name as people say it: Tamriel Rebuilt's working prefixes left out ("TR_HOLD_Meralag")."""
    name = re.sub(r'^(?:[A-Za-z]{1,4}_)+(?:hold_|HOLD_)?', '', name.strip()) if '_' in name else name.strip()
    return name.replace('_', ' ').strip()


def town_of(place):
    return _clean(place.split(',')[0] if ',' in place else place.split(':')[0])


def house_of(place):
    """What a place is called on its own: "Meer-Ei's Apartment" for "Narsis, Meer-Ei's Apartment: Attic"."""
    part = place.split(',', 1)[1] if ',' in place else place
    return _clean(part.split(':')[0]) or _clean(place)


def pronouns(female):
    return {'He': 'She', 'he': 'she', 'His': 'Her', 'his': 'her', 'Him': 'Her', 'him': 'her'} if female else \
        {'He': 'He', 'he': 'he', 'His': 'His', 'his': 'his', 'Him': 'Him', 'him': 'him'}


KHAJIIT_VERBS = ('know', 'think', 'hear', 'sell', 'keep', 'see', 'work', 'want', 'like', 'need', 'mind', 'take', 'make', 'sleep', 'live',
                 'hope', 'wish', 'fear', 'trust', 'remember', 'stand', 'watch', 'fight', 'pray', 'heal', 'listen', 'dig', 'hunt', 'buy',
                 'study', 'serve', 'move', 'walk', 'get', 'owe', 'pour', 'count', 'put', 'bind', 'copy', 'read', 'nod', 'tend', 'dress',
                 'lose', 'give', 'deal', 'cook', 'look', 'run', 'wait', 'beg', 'fish', 'farm', 'guard', 'mine', 'brew', 'eat', 'drink')


def khajiit(text):
    """A line said the way the game's Khajiit speak: of themselves as "this one"."""
    t = text
    for a, b in ((r"\bI'm\b", 'this one is'), (r"\bI am\b", 'this one is'), (r"\bI've\b", 'this one has'), (r"\bI have\b", 'this one has'),
                 (r"\bI was\b", 'this one was'), (r"\bI'd\b", 'this one would'), (r"\bI'll\b", 'this one will'), (r"\bI do\b", 'this one does'),
                 (r"\bI can't\b", 'this one cannot'), (r"\bI don't\b", 'this one does not'), (r"\bI\b", 'this one'), (r"\bmyself\b", 'this one'),
                 (r"\bmy\b", "this one's"), (r"\bMy\b", "This one's"), (r"\bme\b", 'this one')):
        t = re.sub(a, b, t)
    t = re.sub(r'\bthis one (%s)\b' % '|'.join(KHAJIIT_VERBS), lambda m: 'this one ' + (m.group(1) + 'es' if m.group(1).endswith(('ch', 'sh', 's', 'x')) else m.group(1) + 's'), t)
    t = re.sub(r'(^|[.!?]\s+)this one', lambda m: m.group(1) + 'This one', t)
    return t


def fill(text, p, others, ctx, rng, about=None, kin=''):
    """A template with its blanks filled: the speaker's oath and word for a stranger, the place and town,
    and (for a line about someone) their name, what they do and their pronouns."""
    race = (p.get('race') or '').lower()
    d = {'s': rng.choice(STRANGER.get(race, ('stranger', 'friend', 'traveler'))), 'oath': rng.choice(OATHS.get(race, OATHS['imperial'])),
         'place': ctx['place_short'], 'town': ctx['town'], 'first': first_name(p), 'pc': '%PCName', 'kin': kin}
    if about:
        pr = pronouns(about.get('female'))
        d.update(o=about['name'], of=first_name(about), ot=what_they_do(about), **pr)
    out = text
    for k, v in d.items():
        out = out.replace('{' + k + '}', v)
    # (no "this one" for the Khajiit: Project Tamriel's dialogue guide, "TES3 Khajiit do not refer to themselves
    # using 'this one' as they do in later games"; 41 of the game's 2,096 Khajiit lines say it, 2026-10-24.
    # khajiit() stays for a line you ask it of)
    return out


def first_name(p):
    import castsurvey
    f = castsurvey._split_name(p.get('name') or '', p.get('race'))[0]
    return f or p.get('name') or ''


def kin_word(a, b, rng, kinds):
    """What b is to a, in a household's family: a spouse (the first of the other sex near a's age), else a
    brother or sister, or a cousin; the same either way round (kinds keeps what each pair is)."""
    pair = tuple(sorted((a['key'], b['key'])))
    if pair not in kinds:
        if a.get('spouse') == b['key'] or b.get('spouse') == a['key']:
            kinds[pair] = 'spouse'           # (the cast made them a married pair: a home of two)
        elif a.get('spouse') or b.get('spouse'):
            kinds[pair] = 'sibling' if rng.random() < 0.7 else 'cousin'
        elif b.get('female') != a.get('female') and abs((b.get('level') or 1) - (a.get('level') or 1)) <= 8 and \
                not any(a['key'] in k or b['key'] in k for k, v in kinds.items() if v == 'spouse'):
            kinds[pair] = 'spouse'
        else:
            kinds[pair] = 'sibling' if rng.random() < 0.7 else 'cousin'
    kind = kinds[pair]
    word = {'spouse': 'wife' if b.get('female') else 'husband', 'sibling': 'sister' if b.get('female') else 'brother'}.get(kind, 'cousin')
    return kind, word


def lines_for(people, place, setting, rng):
    """{person key: [{'topic', 'text', 'when'}]} for a cast: 'when' is 'first' or 'again' for the greetings
    (said on a first meeting or later), 'liked' for a secret (disposition 60 or more), else ''."""
    ctx = {'place_short': house_of(place), 'town': town_of(place)}
    out = {}
    kinds = {}
    used = set()

    def pick(templates):
        """A template no one else in this cast has said yet, where there is one."""
        fresh = [t for t in templates if t not in used] or list(templates)
        t = rng.choice(fresh)
        used.add(t)
        return t
    # friends and rivals among those who aren't kin: a few pairs
    loose = [p for p in people if p.get('relation') not in ('family',)]
    ties = {}
    for i, a in enumerate(loose):
        for b in loose[i + 1:]:
            if rng.random() < 0.3:
                kind = 'friend' if rng.random() < 0.65 else 'rival'
                ties.setdefault(a['key'], []).append((b, kind))
                ties.setdefault(b['key'], []).append((a, kind))
    for p in people:
        tone = tone_of(p, setting)
        L = []
        L.append({'topic': 'greeting', 'when': 'first', 'text': fill(pick(GREET_FIRST[tone]), p, people, ctx, rng)})
        L.append({'topic': 'greeting', 'when': 'again', 'text': fill(pick(GREET_AGAIN[tone]), p, people, ctx, rng)})
        low = (p.get('cls') or '').lower()
        trade = next((ts for words, ts in TRADES if any(w in low for w in words)), TRADE_ANY)
        L.append({'topic': 'my trade', 'when': '', 'text': fill(pick(trade), p, people, ctx, rng)})
        # someone in particular: up to two of the others, the closest first
        abouts = []
        for o in people:
            if o is p:
                continue
            if p.get('relation') in ('head', 'family') and o.get('relation') in ('head', 'family'):
                kind, word = kin_word(p, o, rng, kinds)
                abouts.append((0, o, ABOUT_KIN[kind], word))
            elif o.get('relation') == 'head' and p.get('relation') == 'servant':
                abouts.append((1, o, ABOUT_MASTER, ''))
            elif o.get('relation') == 'head':
                abouts.append((2, o, ABOUT_HEAD, ''))
            elif o.get('relation') == 'servant' and p.get('relation') in ('head', 'family'):
                abouts.append((2, o, ABOUT_SERVANT, ''))
        for o, kind in ties.get(p['key'], []):
            abouts.append((1, o, ABOUT_FRIEND if kind == 'friend' else ABOUT_RIVAL, ''))
        if not abouts:
            for o in people:
                if o is not p:
                    abouts.append((3, o, ABOUT_WORK, ''))
        abouts.sort(key=lambda a: (a[0], rng.random()))
        seen = set()
        said = []
        for _r, o, templates, word in abouts:
            if o['key'] in seen or len(said) >= 2:
                continue
            seen.add(o['key'])
            said.append(fill(pick(templates), p, people, ctx, rng, about=o, kin=word))
        if said:
            L.append({'topic': 'someone in particular', 'when': '', 'text': ' '.join(said)})
        # a little secret (to someone they like): about one of the others, else about themselves
        if rng.random() < 0.75:
            others = [o for o in people if o is not p]
            if others and rng.random() < 0.7:
                o = rng.choice(others)
                L.append({'topic': 'little secret', 'when': 'liked', 'text': fill(pick(SECRET_ABOUT), p, people, ctx, rng, about=o)})
            else:
                L.append({'topic': 'little secret', 'when': 'liked', 'text': fill(pick(SECRET_SELF), p, people, ctx, rng)})
        if setting not in ('cave', 'hideout', 'tomb', 'dwemer', 'daedric', 'ruin') and rng.random() < 0.6:
            L.append({'topic': 'latest rumors', 'when': '', 'text': fill(pick(RUMOR_PLACE), p, people, ctx, rng)})
        out[p['key']] = L
    return out
