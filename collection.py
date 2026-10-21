"""Collection layer: guest dex (rare / family / legendary), bread variants, gift drops.

Art is optional. Drop PNGs into assets/guests/ and they replace the code-drawn
placeholders automatically:
  assets/guests/<id>.png                 rare guest, 22x26 (larger is scaled down)
  assets/guests/family_<occasion>.png    family overlay, 24x34, transparent
  assets/guests/family_<1-9>_<occasion>.png  per-appearance overlay (optional)
  assets/guests/named_<name>.png         named human family guest, 24x34
Set PIXELCAFE_DATE=YYYY-MM-DD to preview a seasonal/anniversary occasion.
"""
import datetime
import os
import random
from pathlib import Path

import detail_render as dr

from progression import nice_number, staff_target, _hours, _nonnegative
from game_data import (
    LEGEND_P, RARE_P, FAMILY_P, LEGEND_MULT, RARE_MULT, FAMILY_MULT, LEGEND,
    STEPS, FRIEND_BONUS, VARIANT_BONUS, DROP_P, DROP_MULT, VARIANTS,
    MATE_RULES, MATE_MAX_LV, MATE_LV_BONUS, ACH_SUB, ACH_CAT, ACH_ALL,
    choose_collectible, record_discovery, normalize_pity, read_save, write_save,
)

NAMED_FAMILY = {
    '도야니': (10, 'named_doyani.png'),
    '셔니': (11, 'named_syeoni.png'),
}
NEW_RARE = {
    'totoro': '토토로', 'stitch': '스티치', 'pooh': '곰돌이 푸', 'rilakkuma': '리락쿠마',
    'snoopy': '스누피', 'kaonashi': '가오나시', 'kumamon': '쿠마몬', 'gudetama': '구데타마',
}
PLACEHOLDER = {   # body, belly, accent
    'totoro': ((128, 134, 148), (236, 232, 220), (60, 60, 70)),
    'stitch': ((74, 120, 214), (150, 190, 240), (30, 40, 110)),
    'pooh': ((238, 190, 70), (250, 220, 130), (200, 50, 50)),
    'rilakkuma': ((150, 104, 70), (214, 170, 130), (90, 60, 40)),
    'snoopy': ((250, 250, 250), (250, 250, 250), (30, 30, 30)),
    'kaonashi': ((40, 36, 48), (40, 36, 48), (240, 240, 240)),
    'kumamon': ((40, 40, 44), (240, 236, 224), (220, 50, 50)),
    'gudetama': ((250, 214, 70), (255, 240, 170), (250, 250, 250)),
}
VARIANT_COLOR = {'strawberry': (255, 150, 170), 'choco': (170, 120, 90),
                 'gold': (255, 215, 90), 'rainbow': (200, 170, 255)}
OCCASIONS = ('spring', 'summer', 'autumn', 'winter', 'newyear', 'valentine', 'halloween', 'christmas')
OCC_NAME = {'spring': '봄나들이 손님', 'summer': '여름휴가 손님', 'autumn': '단풍놀이 손님',
            'winter': '겨울나기 손님', 'newyear': '새해맞이 손님', 'valentine': '발렌타인 손님',
            'halloween': '할로윈 손님', 'christmas': '크리스마스 손님'}
OCC_HINT = {'spring': '3~5월에 방문', 'summer': '6~8월에 방문', 'autumn': '9~11월에 방문',
            'winter': '12~2월에 방문', 'newyear': '1월 1~7일에 방문', 'valentine': '2월 7~14일에 방문',
            'halloween': '10월 24~31일에 방문', 'christmas': '12월 18~26일에 방문'}
OCC_COLOR = {'spring': (255, 160, 200), 'summer': (250, 210, 90), 'autumn': (220, 120, 40),
             'winter': (120, 170, 240), 'newyear': (230, 60, 60), 'valentine': (255, 90, 140),
             'halloween': (240, 130, 20), 'christmas': (210, 40, 40)}
SPECIES_NAME = {'cat': '고양이', 'dog': '강아지', 'rabbit': '토끼', 'bear': '곰', 'hamster': '햄스터',
                'fox': '여우', 'mouse': '쥐'}
FUR_NAME = {'cat': ('주황', '검정', '흰색', '회색'), 'dog': ('갈색', '크림', '흰색', '검정'),
            'rabbit': ('흰색', '갈색', '회색'), 'bear': ('갈색', '흰색', '검정'),
            'hamster': ('베이지', '흰색', '회색'), 'fox': ('주황', '흰색'),
            'mouse': ('파랑', '회색', '분홍')}
CATS = (('guest', '손님'), ('ach', '업적'))      # companions ('mate') live in the crew tab (cafe.TABS 직원 -> 동료)
SUBTABS = {'guest': (('normal', '일반'), ('rare', '희귀'), ('family', '가족 손님'), ('legend', '전설')),
           'mate': (('m_normal', '일반'), ('m_rare', '희귀'), ('m_family', '가족 손님'), ('m_legend', '전설')),
           'ach': (('ach_list', '달성 목록'), ('ach_skin', '툴바 디자인'))}
FUSION = {'anbutter', 'eggtoast', 'frenchtoast', 'sandwich', 'avotoast', 'omelet', 'sausage',
          'burger', 'pizza', 'benedict', 'brunch'}   # breads that mix two foods

# one-line look hints shown for guests that were not met yet
GUEST_HINT = {
    'chiikawa': '하얗고 동글동글, 볼이 발그레한 아이',
    'usagi': '토끼 귀를 단 노란 병아리 같은 친구',
    'hachiware': '뾰족한 귀에 회색·하얀 얼굴을 한 아이',
    'kitty': '빨간 리본을 단 하얀 고양이',
    'melody': '분홍빛 두건을 쓴 하얀 토끼',
    'kuromi': '까만 두건에 분홍 해골 장식을 단 친구',
    'cinna': '귀가 길게 늘어진 하얀 강아지',
    'purin': '머리에 캐러멜 모자를 쓴 노란 강아지',
    'ganadi': '곱슬한 크림색 털에 스카프를 한 강아지',
    'loopy': '분홍 뺨의 둥글둥글한 분홍 곰',
    'ryan': '둥근 귀와 큰 얼굴의 주황 친구',
    'apeach': '복숭아처럼 동글한 분홍 아이',
    'pororo': '비행 모자와 고글을 쓴 주황 아이',
    'pikachu': '줄무늬 꼬리의 주황 다람쥐',
    'chunsik': '주황 줄무늬 고양이',
    'totoro': '숲속에 사는 커다란 회색 정령',
    'stitch': '큰 귀를 가진 파란 장난꾸러기',
    'pooh': '빨간 셔츠를 입은 노란 곰',
    'rilakkuma': '느긋하게 뒹구는 갈색 곰',
    'snoopy': '귀가 까만 하얀 강아지',
    'kaonashi': '하얀 가면을 쓴 검은 그림자',
    'kumamon': '붉은 볼의 까만 곰',
    'gudetama': '축 늘어진 노른자 친구',
}
# companions ("동료"): a guest met in the cafe can be invited to stay for a permanent income bonus.
#   tier: (bonus each, friendship Lv needed, gold = best bread price x this, companions needed first)
# normal: just meet them and pay.  rare: become true friends (max friendship) first.
# family: befriend that seasonal family (Lv.3).  legend: one visit is enough, but you must already
# run a crew of rare/family companions and pay a fortune -- the endgame gold sink.
MATE_ZONE = (112, 66, 228, 84)      # back aisle between the counter and the oven: no furniture stands here
MATE_TIER_NAME = {'normal': '일반 손님', 'rare': '희귀 손님', 'family': '가족 손님', 'legend': '전설 손님'}

# who a named family guest belongs to, shown while they are still undiscovered
FAMILY_HINT = {     # guess shown while a named family guest is still undiscovered
    '도경가족': '도경의 가족인 것 같다',
    '미예언니가족': '미예언니의 가족인 것 같다',
    '지현가족': '지현의 가족인 것 같다',
    '지영가족': '지영의 가족인 것 같다',
    '진예가족': '진예의 가족인 것 같다',
    '배지가족': '배지의 가족인 것 같다',
    '도야니': '도경의 동생인 것 같다',
    '셔니': '지현의 동생인 것 같다',
}
# which family each generic look (1-9) belongs to
FAMILY_LOOKS = {1: '배지가족', 2: '지현가족', 3: '도경가족', 4: '진예가족', 5: '지영가족',
                6: '미예언니가족', 7: '도경가족', 8: '배지가족', 9: '지현가족'}
FAMILY_ASSETS = {
    '도경가족': 'family_dokyeong.png', '배지가족': 'family_baeji.png',
    '지현가족': 'family_jihyeon.png', '진예가족': 'family_jinye.png',
    '지영가족': 'family_jiyeong.png',
    '미예언니가족': 'family_miye.png',
}

# mini bar designs: unlocked by achievements (colors only, no art needed)
SKINS = (
    dict(id='brown', name='기본 갈색', ach=None, fill=(112, 74, 52), edge=(58, 36, 26), text=(255, 240, 200),
         light=(150, 106, 78), btn=(226, 196, 150), inc=(255, 214, 120)),
    dict(id='mint', name='민트 소다', ach='a_normal', fill=(78, 150, 132), edge=(34, 86, 74), text=(240, 255, 248),
         light=(128, 196, 176), btn=(214, 240, 226), inc=(255, 238, 150)),
    dict(id='pink', name='벚꽃 핑크', ach='a_rare', fill=(214, 130, 160), edge=(122, 58, 86), text=(255, 244, 248),
         light=(240, 170, 196), btn=(255, 226, 236), inc=(255, 246, 190)),
    dict(id='navy', name='밤하늘 네이비', ach='a_legend', fill=(62, 82, 148), edge=(28, 38, 92), text=(232, 238, 255),
         light=(104, 126, 196), btn=(200, 212, 246), inc=(255, 226, 130)),
    dict(id='cream', name='크림 베이커리', ach='a_breads', fill=(232, 206, 164), edge=(140, 100, 60), text=(92, 58, 36),
         light=(248, 232, 200), btn=(255, 248, 232), inc=(150, 84, 20)),
    dict(id='gold', name='골든 바', ach='a_variants', fill=(206, 158, 48), edge=(112, 76, 12), text=(255, 250, 214),
         light=(240, 200, 100), btn=(255, 238, 178), inc=(255, 252, 230)),
    dict(id='black', name='블랙 골드', ach='a_all', fill=(46, 42, 58), edge=(226, 186, 76), text=(255, 226, 130),
         light=(78, 72, 96), btn=(236, 214, 150), inc=(255, 226, 130)),
)
SKIN_BY_ID = {k['id']: k for k in SKINS}
# achievement rewards: permanent income bonus + one-time gold (x best bread price)


def occasion(today=None):
    if today is None:
        raw = os.environ.get('PIXELCAFE_DATE', '')
        try:
            today = datetime.date.fromisoformat(raw) if raw else datetime.date.today()
        except ValueError:
            today = datetime.date.today()
    m, d = today.month, today.day
    if m == 1 and d <= 7:
        return 'newyear'
    if m == 2 and 7 <= d <= 14:
        return 'valentine'
    if m == 10 and d >= 24:
        return 'halloween'
    if m == 12 and 18 <= d <= 26:
        return 'christmas'
    if 3 <= m <= 5:
        return 'spring'
    if 6 <= m <= 8:
        return 'summer'
    if 9 <= m <= 11:
        return 'autumn'
    return 'winter'


def _asset_dirs():
    here = Path(__file__).resolve().parent
    dirs = [here / 'assets' / 'guests', Path.cwd() / 'assets' / 'guests']
    import sys
    base = getattr(sys, '_MEIPASS', None)
    if base:
        dirs.insert(0, Path(base) / 'assets' / 'guests')
    return dirs


def _load_png(pygame, filename, size):
    for folder in _asset_dirs():
        path = folder / filename
        if path.is_file():
            try:
                image = pygame.image.load(str(path)).convert_alpha()
            except pygame.error:
                continue
            if image.get_size() != size:
                image = pygame.transform.scale(image, size)

            def detail(scale, source=image, directory=folder):
                variant = directory / f'{Path(filename).stem}@{scale}x.png'
                expected = (size[0] * scale, size[1] * scale)
                if variant.is_file():
                    high = pygame.image.load(str(variant)).convert_alpha()
                    if high.get_size() != expected:
                        raise ValueError(f'{variant}: expected {expected}, got {high.get_size()}')
                    return high
                return pygame.transform.scale(source, expected)

            return dr.register(image, detail)
    return None


def _blank_state():
    return dict(guests={}, variants={}, new=[], recipes=None, ach=[], skin='brown',
                mates=[], mate_lv={}, mate_work={}, rep=None, pity={})


def install(cafe):
    if getattr(cafe, '_collection_installed', False):
        return
    cafe._collection_installed = True
    pygame = cafe.pygame
    specials = cafe.specials
    Game, UI, Customer = cafe.Game, cafe.UI, cafe.Customer
    book_tab = cafe.TABS.index('도감')
    staff_tab = cafe.TABS.index('직원')
    cafe.TABS[staff_tab] = '동료'          # staff + companions share this tab
    for key, name in NEW_RARE.items():
        specials.SPECIAL.setdefault(key, name)
    cafe.RARE_P, cafe.FAMILY_P = RARE_P, FAMILY_P
    cafe.RARE_MULT, cafe.FAMILY_MULT = RARE_MULT, FAMILY_MULT
    legend_ids = [k for k in LEGEND if k in specials.SPECIAL]
    rare_ids = [k for k in specials.SPECIAL if k not in LEGEND]
    specials.FAMILY_NAMES = tuple(dict.fromkeys((*specials.FAMILY_NAMES, *NAMED_FAMILY)))
    famnames = list(specials.FAMILY_NAMES)
    named_looks = {look: (name, filename) for name, (look, filename) in NAMED_FAMILY.items()}
    famlooks = [*range(1, 10), *named_looks]
    save_path = os.path.join(cafe.SAVE_DIR, 'collection.json')

    # ---- art: file first, code-drawn placeholder second --------------------
    original_special, original_family = specials.special_surf, specials.family_surf
    cache = {}

    def placeholder(key, frame):
        body, belly, accent = PLACEHOLDER[key]
        s = pygame.Surface((22, 26), pygame.SRCALPHA)
        up = -1 if frame else 0
        pygame.draw.ellipse(s, body, (4, 11 + up, 14, 14))
        pygame.draw.ellipse(s, belly, (7, 14 + up, 8, 9))
        pygame.draw.circle(s, body, (11, 8 + up), 7)
        for ex in (4, 18):
            pygame.draw.circle(s, accent if key != 'kaonashi' else body, (ex, 3 + up), 3)
        if key == 'kaonashi':
            pygame.draw.ellipse(s, accent, (6, 3 + up, 10, 11))
        pygame.draw.circle(s, (20, 20, 20), (8, 8 + up), 1)
        pygame.draw.circle(s, (20, 20, 20), (14, 8 + up), 1)
        if key == 'kumamon':
            pygame.draw.circle(s, accent, (6, 11 + up), 2)
            pygame.draw.circle(s, accent, (16, 11 + up), 2)
        if key == 'pooh':
            pygame.draw.rect(s, accent, (5, 15 + up, 12, 5))
        return s

    def special_surf(name, frame=0, facing=1):
        if name not in NEW_RARE:
            return original_special(name, frame, facing)
        key = ('sp', name, frame % 3, facing)
        if key not in cache:
            image = _load_png(pygame, name + '.png', (22, 26))
            if image is None:
                image = placeholder(name, frame & 1)
            else:
                image = cafe.art.walk(image, frame % 3, facing)
            cache[key] = image
        return cache[key]

    def family_composite(appearance, frame, facing, occ):
        key = ('fam', appearance, frame, facing, occ)
        if key in cache:
            return cache[key]
        if appearance in named_looks:
            _, filename = named_looks[appearance]
            base = _load_png(pygame, filename, (24, 34))
            if base is None:
                raise FileNotFoundError(f'Named family guest asset missing: {filename}')
            image = cafe.art.walk(base, frame % 3, facing)
            cache[key] = image
            return image
        filename = FAMILY_ASSETS.get(FAMILY_LOOKS.get(appearance))
        base = _load_png(pygame, filename, (24, 34)) if filename else None
        base = (cafe.art.walk(base, frame % 3, facing) if base is not None
                else original_family(appearance, frame, facing))
        w, h = base.get_size()
        over = (_load_png(pygame, f'family_{appearance}_{occ}.png', (w, h))
                or _load_png(pygame, f'family_{occ}.png', (w, h)))
        if over is None:
            over = pygame.Surface((w, h), pygame.SRCALPHA)
            col = OCC_COLOR[occ]
            pygame.draw.rect(over, col, (w // 2 - 5, 1, 10, 3))
            pygame.draw.rect(over, (255, 255, 255), (w // 2 - 5, 0, 10, 1))
            pygame.draw.circle(over, col, (w // 2 + 4, 4), 2)
        def compose(scale):
            image = (base if scale == 1 else dr.detail(base, scale)).copy()
            image.blit(over if scale == 1 else dr.detail(over, scale), (0, 0))
            return image

        image = dr.register(compose(1), compose)
        cache[key] = image
        return image

    def family_surf(appearance, frame=0, facing=1):
        return family_composite(appearance, frame, facing, occasion())

    specials.special_surf, specials.family_surf = special_surf, family_surf

    # ---- state -------------------------------------------------------------
    original_init, original_save, original_load = Game.__init__, Game.save, Game.load
    original_paid, original_price = Game.customer_paid, Game.price

    def entry(game, key):
        return game.col['guests'].setdefault(key, dict(v=0, lv=0, gift=0))

    def init(self):
        self.col = _blank_state()
        original_init(self)

    def flag(game, key):
        if key not in game.col['new']:
            game.col['new'].append(key)

    def seen(game, key):
        return game.col['guests'].get(key, {}).get('v', 0) > 0

    def reward_of(aid):
        return ACH_ALL if aid == 'a_all' else ACH_CAT if aid in ('a_guests', 'a_breads', 'a_variants') else ACH_SUB

    _ach = []

    def ach_defs():
        """[(id, name, have(game), total)] -- built once; keys come from live game data."""
        if _ach:
            return _ach
        normals = [f'n_{sp}_{v}' for sp, looks in cafe.SPECIES.items() for v in range(len(looks))]
        groups = [('a_normal', '일반 손님 박사', normals), ('a_rare', '희귀 손님 수집가', list(rare_ids)),
                  ('a_legend', '전설을 만난 자', list(legend_ids)),
                  ('a_famev', '사계절 손님 앨범', ['fam_' + o for o in OCCASIONS]),
                  ('a_famname', '가족 이름 대장', ['famn_' + n for n in famnames]),
                  ('a_famlook', '가족 외형 대장', [f'fama_{i}' for i in famlooks])]
        defs = []
        for aid, name, keys in groups:
            defs.append((aid, name, (lambda g, keys=keys: sum(seen(g, k) for k in keys)), len(keys)))
        basic = [r['id'] for r in cafe.RECIPES if r['id'] not in FUSION]
        fusion = [r['id'] for r in cafe.RECIPES if r['id'] in FUSION]
        for aid, name, ids in (('a_basic', '기본 빵 마스터', basic), ('a_fusion', '퓨전 빵 마스터', fusion)):
            defs.append((aid, name, (lambda g, ids=ids: sum(g.rlv.get(i, 0) > 0 for i in ids)), len(ids)))
        for vid, vname, _c, _m in VARIANTS:
            defs.append((f'a_v_{vid}', f'{vname} 변종 수집가',
                         (lambda g, vid=vid: sum(vid in g.col['variants'].get(r['id'], {}) for r in cafe.RECIPES)),
                         len(cafe.RECIPES)))
        by = {d[0]: d for d in defs}

        def merge(aid, name, ids):
            parts = [by[i] for i in ids]
            defs.append((aid, name, (lambda g, parts=parts: sum(p[2](g) for p in parts)), sum(p[3] for p in parts)))
            by[aid] = defs[-1]
        merge('a_guests', '손님 도감 완성', [g[0] for g in groups])
        merge('a_breads', '빵 도감 완성', ['a_basic', 'a_fusion'])
        merge('a_variants', '특별빵 도감 완성', [f'a_v_{v[0]}' for v in VARIANTS])
        defs.append(('a_all', '도감 대장', (lambda g: by['a_guests'][2](g) + by['a_breads'][2](g) + by['a_variants'][2](g)),
                     by['a_guests'][3] + by['a_breads'][3] + by['a_variants'][3]))
        _ach.extend(defs)
        return _ach

    def skin_ok(game, skin):
        return skin['ach'] is None or skin['ach'] in game.col['ach']

    def real_skin(game):
        skin = SKIN_BY_ID.get(game.col.get('skin'), SKINS[0])
        return skin if skin_ok(game, skin) else SKINS[0]

    def skin_palette(game):
        shown = SKIN_BY_ID.get(getattr(game, 'skin_preview', None))      # un-confirmed click in the skin list
        if shown:
            return shown
        skin = SKIN_BY_ID.get(game.col.get('skin'), SKINS[0])
        return skin if skin_ok(game, skin) else SKINS[0]

    def check(game):
        owned = {r for r, lv in game.rlv.items() if lv > 0}
        if game.col['recipes'] is None:
            game.col['recipes'] = sorted(owned)           # existing saves: nothing counts as new
        else:
            for rid in sorted(owned - set(game.col['recipes'])):
                flag(game, 'b:' + rid)
            game.col['recipes'] = sorted(owned)
        for aid, name, have, total in ach_defs():
            if aid in game.col['ach'] or have(game) < total:
                continue
            pct_, gold_mult = reward_of(aid)
            best = max((original_price(game, r) for r in cafe.RECIPES if game.rlv[r['id']] > 0), default=40)
            gold = round(best * gold_mult)
            game.col['ach'].append(aid)
            game.money += gold
            game.total += gold
            flag(game, 'a:' + aid)
            skin = next((k for k in SKINS if k['ach'] == aid), None)
            if skin:
                flag(game, 's:' + skin['id'])
            game.toast(f'업적 달성! {name} · 수익 +{pct_ * 100:g}% · +{cafe.fmt(gold)}'
                       + (f' · 디자인 {skin["name"]}' if skin else ''))

    def mate_tier(key):
        return ('normal' if key.startswith(('n_', 'fam_')) else 'family' if key.startswith('famn_') else
                'legend' if key in legend_ids else 'rare')

    def fam_look(name):
        """Generic or named look used to draw a family name (e.g. 도경가족)."""
        if name in NAMED_FAMILY:
            return NAMED_FAMILY[name][0]
        return next((k for k, v in FAMILY_LOOKS.items() if v == name), 1)

    def fam_label(key):
        return key[5:] if key.startswith('famn_') else OCC_NAME[key[4:]]

    def fam_image(key, frame=0, facing=1):
        if key.startswith('famn_'):
            return family_composite(fam_look(key[5:]), frame, facing, occasion())
        return family_composite(1 + OCCASIONS.index(key[4:]), frame, facing, key[4:])

    def mate_lv(col, key):
        return max(1, min(MATE_MAX_LV, col.get('mate_lv', {}).get(key, 1)))

    def mate_bonus(col, key):
        return MATE_RULES[mate_tier(key)][0] * (1 + MATE_LV_BONUS * (mate_lv(col, key) - 1))

    def bonus(game):
        col = getattr(game, 'col', None)
        if not col:
            return 1.0
        friend = sum(e.get('lv', 0) for e in col['guests'].values())
        found = sum(len(v) for v in col['variants'].values())
        mates = sum(mate_bonus(col, k) for k in col.get('mates', ()))
        return (1.0 + FRIEND_BONUS * friend + VARIANT_BONUS * found + mates
                + sum(reward_of(a)[0] for a in col.get('ach', ())))

    def price(self, recipe):
        return round(original_price(self, recipe) * bonus(self))

    def save(self):
        original_save(self)
        try:
            write_save(save_path, self.col)
        except (OSError, TypeError, ValueError):
            pass

    def load(self):
        original_load(self)
        self.col = _blank_state()
        data = read_save(save_path)
        self.col['pity'] = normalize_pity(data.get('pity'))
        guests, variants = data.get('guests', {}), data.get('variants', {})
        if isinstance(guests, dict):
            for key, e in guests.items():
                if isinstance(e, dict):
                    self.col['guests'][str(key)] = dict(
                        v=int(_nonnegative(e.get('v', 0))),
                        lv=min(len(STEPS), int(_nonnegative(e.get('lv', 0)))),
                        gift=int(_nonnegative(e.get('gift', 0))))
        if isinstance(data.get('new'), list):
            self.col['new'] = [str(k) for k in data['new']]
        if isinstance(data.get('recipes'), list):
            self.col['recipes'] = [str(k) for k in data['recipes']]
        if isinstance(data.get('ach'), list):
            self.col['ach'] = [str(k) for k in data['ach']]
        if isinstance(data.get('mates'), list):
            self.col['mates'] = list(dict.fromkeys(str(k) for k in data['mates']))
        for field in ('mate_lv', 'mate_work'):
            raw = data.get(field)
            if isinstance(raw, dict):
                for key, value in raw.items():
                    number = _nonnegative(value)
                    if key in self.col['mates']:
                        self.col[field][str(key)] = (min(MATE_MAX_LV, max(1, int(number))) if field == 'mate_lv'
                                                     else number)
        if data.get('rep') in self.col['mates']:
            self.col['rep'] = data['rep']
        if isinstance(data.get('skin'), str):
            self.col['skin'] = data['skin']
        if isinstance(variants, dict):
            for rid, found in variants.items():
                if isinstance(found, dict) and rid in cafe.RECIPE:
                    self.col['variants'][rid] = {v[0]: max(1, int(_nonnegative(found[v[0]]))) for v in VARIANTS
                                                 if v[0] in found}
        self.sync_staff()

    # ---- spawning: legend / rare / family / normal -------------------------
    def pick_guest(game, keys, pool, weights=None):
        discovered = {key for key, value in game.col['guests'].items() if value['v'] > 0}
        return choose_collectible(keys, discovered, game.col['pity'], pool, weights=weights)

    def spawn(self, plan):
        roll = random.random()
        family_p, rare_p = cafe.FAMILY_P, cafe.RARE_P
        if roll < LEGEND_P and legend_ids:
            name = pick_guest(self, legend_ids, 'legend')
            c = Customer(self, plan, 'rare', name)
            c.mult, c.tier = LEGEND_MULT, 'legend'
            self.customers.append(c)
            self.toast(f'★ 전설 손님 {specials.SPECIAL[name]} 등장! 빵 값의 {LEGEND_MULT}배를 내요')
        elif roll < LEGEND_P + family_p:
            key = pick_guest(self, ['famn_' + n for n in famnames], 'family_name')
            name = key[5:]
            occ = occasion()
            count = 1      # family guests arrive one at a time
            for i in range(count):
                c = Customer(self, plan if i == 0 else (self.make_plan() or list(plan)), 'family', name)
                c.tier, c.occ = 'family', occ
                if name in NAMED_FAMILY:
                    c.appearance = NAMED_FAMILY[name][0]
                    c.species = 'human'
                else:
                    looks = [k for k, v in FAMILY_LOOKS.items() if v == name]
                    if looks:
                        key = pick_guest(self, [f'fama_{look}' for look in looks], 'family_look')
                        c.appearance = int(key[5:])
                c.y += i * 6
                self.customers.append(c)
            self.toast(f'{OCC_NAME[occ]}({name})이 왔어요! 빵 값의 {cafe.FAMILY_MULT}배를 내요')
        elif roll < LEGEND_P + family_p + rare_p:
            name = pick_guest(self, rare_ids, 'rare')
            c = Customer(self, plan, 'rare', name)
            c.tier = 'rare'
            self.customers.append(c)
            self.toast(f'희귀 손님 {specials.SPECIAL[name]} 등장! 빵 값의 {cafe.RARE_MULT}배를 내요')
        else:
            customer = Customer(self, plan)
            looks = [(sp, var) for sp, variants in cafe.SPECIES.items() for var in range(len(variants))]
            key = pick_guest(self, [f'n_{sp}_{var}' for sp, var in looks], 'normal',
                             weights=[1 / len(cafe.SPECIES[sp]) for sp, _ in looks])
            _, customer.species, var = key.split('_')
            customer.var = int(var)
            self.customers.append(customer)

    def friend_reward(game, level, tier='rare'):
        best = max((original_price(game, r) for r in cafe.RECIPES if game.rlv[r['id']] > 0), default=40)
        return round(best * 3 * level * (2 if tier == 'legend' else 1))

    def normal_label(sp, var):
        names = FUR_NAME.get(sp, ())
        fur = names[var] + ' ' if var < len(names) else ''
        return f'{fur}{SPECIES_NAME.get(sp, sp)}'

    def visit(game, customer, amount):
        tier = getattr(customer, 'tier', 'normal')
        if tier == 'normal' or customer.kind == 'normal':
            nkey = f'n_{customer.species}_{customer.var}'
            e = entry(game, nkey)
            record_discovery(game.col['pity'], 'normal', e['v'] == 0)
            e['v'] += 1
            if e['v'] == 1:
                flag(game, 'g:' + nkey)
                game.toast(f'도감 등록! {normal_label(customer.species, customer.var)}')
            return
        key = 'fam_' + getattr(customer, 'occ', occasion()) if tier == 'family' else customer.name
        label = OCC_NAME.get(key[4:], key) if tier == 'family' else specials.SPECIAL.get(key, key)
        e = entry(game, key)
        if tier != 'family':
            record_discovery(game.col['pity'], tier, e['v'] == 0)
        e['v'] += 1
        if e['v'] == 1:
            flag(game, 'g:' + key)
            game.toast(f'도감 등록! {label}')
        if tier == 'family':        # family name / look dex: registration only, no friendship
            for xkey, xlabel in (('famn_' + str(customer.name), str(customer.name)),
                                 (f'fama_{customer.appearance}', f'가족 외형 {customer.appearance}')):
                xe = entry(game, xkey)
                record_discovery(game.col['pity'], 'family_name' if xkey.startswith('famn_')
                                 else 'family_look', xe['v'] == 0)
                xe['v'] += 1
                if xe['v'] == 1:
                    flag(game, 'g:' + xkey)
                    game.toast(f'도감 등록! {xlabel}')
        while e['lv'] < len(STEPS) and e['v'] >= STEPS[e['lv']]:
            e['lv'] += 1
            reward = friend_reward(game, e['lv'], tier)
            game.money += reward
            game.total += reward
            game.toast(f'{label} 우정 Lv.{e["lv"]}! 선물 +{cafe.fmt(reward)} · 수익 +{FRIEND_BONUS * 100:.1f}%')
        if random.random() < DROP_P.get(tier, 0):
            gift = round(amount * DROP_MULT)
            game.money += gift
            game.total += gift
            e['gift'] += 1
            game.toast(f'{label}이(가) 선물을 두고 갔어요! +{cafe.fmt(gift)}')

    def paid(self, customer):
        if customer.paid:
            return original_paid(self, customer)
        cart = [rid for rid in customer.cart if self.rlv.get(rid, 0) > 0]
        before = self.money
        original_paid(self, customer)
        amount = self.money - before
        extra = 0.0
        for rid in cart:
            roll, picked = random.random(), None
            for vid, vname, chance, vmult in VARIANTS:
                if roll < chance:
                    picked = (vid, vname, vmult)
                    break
                roll -= chance
            if not picked:
                continue
            vid, vname, vmult = picked
            # Auto-display only sells the priciest breads, so the variant lands on any
            # unlocked bread; otherwise cheap breads could never get a variant.
            eligible = [r for r, lv in self.rlv.items() if lv > 0 and r in cafe.RECIPE]
            discovered = {r for r, found in self.col['variants'].items() if vid in found}
            rid = choose_collectible(eligible, discovered, self.col['pity'], f'variant:{vid}')
            gain = round(original_price(self, cafe.RECIPE[rid]) * bonus(self) * (vmult - 1) * customer.mult)
            extra += gain
            found = self.col['variants'].setdefault(rid, {})
            first = vid not in found
            record_discovery(self.col['pity'], f'variant:{vid}', first)
            found[vid] = found.get(vid, 0) + 1
            self.popups.append([customer.sx, customer.sy - 52,
                                f'{vname} {cafe.RECIPE[rid]["name"]}! +{cafe.fmt(gain)}',
                                0.0, VARIANT_COLOR[vid]])
            if first:
                flag(self, f'v:{vid}_{rid}')
                self.toast(f'변종 발견! {vname} {cafe.RECIPE[rid]["name"]} (수익 +{VARIANT_BONUS * 100:.1f}%)')
        if extra:
            self.money += extra
            self.total += extra
        visit(self, customer, amount + extra)

    # ---- legendary tag over the head --------------------------------------
    original_label = Customer.draw_label

    def rainbow(t, i):
        color = pygame.Color(0)
        color.hsva = ((t * 0.12 + i * 38) % 360, 55, 100, 100)
        return color.r, color.g, color.b

    def draw_label(self, s):
        if getattr(self, 'tier', '') != 'legend':
            return original_label(self, s)
        name = specials.SPECIAL.get(self.name, self.name)
        font = cafe.font(10, True)
        widths = [font.size(ch)[0] for ch in name]
        x, t = self.sx - sum(widths) // 2, pygame.time.get_ticks()
        for i, ch in enumerate(name):
            cafe.text(s, ch, 10, rainbow(t, i), x, self.sy + 2, True, 'tl', shadow=cafe.INK)
            x += widths[i]

    # ---- dex tab -----------------------------------------------------------
    original_rows, original_draw, original_click = UI.rows, UI.draw, UI.click

    def silhouette(image):
        mask = pygame.mask.from_surface(image)
        return mask.to_surface(setcolor=(52, 40, 40, 255), unsetcolor=(0, 0, 0, 0))

    def fit(image, box=46):
        w, h = image.get_size()
        scale = min(box / w, box / h)
        return pygame.transform.scale(image, (max(1, int(w * scale)), max(1, int(h * scale))))

    def pct(p):
        return f'{p * 100:.2f}'.rstrip('0').rstrip('.') + '%'

    def cond(tier, hint=''):
        if tier == 'legend':
            return '전설 손님'
        if tier == 'rare':
            return '희귀 손님'
        if tier == 'family':
            return f'등장: {hint}'
        return '일반 손님'

    def guest_row(game, key, name, image, hint, kind_label, tier='rare'):
        e = game.col['guests'].get(key)
        if not e or e['v'] <= 0:
            if tier in ('rare', 'legend') and key in GUEST_HINT:
                return dict(kind='none', id=key, name='???', sub=GUEST_HINT[key],
                            price=f'{kind_label} · 미발견', ok=False, state='locked',
                            icon=fit(silhouette(image)))
            return dict(kind='none', id=key, name='???', sub=cond(tier, hint), price=f'{kind_label} · 미발견',
                        ok=False, state='locked', icon=fit(silhouette(image)))
        lv = e['lv']
        nxt = f'다음 우정까지 {STEPS[lv] - e["v"]}회' if lv < len(STEPS) else '우정 최대'
        return dict(kind='none', id=key, name=f'{name}  우정 Lv.{lv}', sub=f'방문 {e["v"]}회 · {nxt}',
                    price=f'선물 {e["gift"]}회 · {cond(tier, hint)}', ok=False, state='owned',
                    icon=fit(image))

    def animal_icon(sp, var):
        s = pygame.Surface((40, 40), pygame.SRCALPHA)
        cafe.draw_animal(s, 20, 36, sp, var, cafe.CUST_SHIRTS[0], None, 0, 1)
        return s.subsurface(s.get_bounding_rect()).copy()

    def normal_rows(game):
        rows = []
        for sp, looks in cafe.SPECIES.items():
            for var in range(len(looks)):
                e = game.col['guests'].get(f'n_{sp}_{var}')
                image = animal_icon(sp, var)
                if not e or e['v'] <= 0:
                    rows.append(dict(kind='none', id=f'n_{sp}_{var}', name='???',
                                     sub=cond('normal'),
                                     price='일반 손님 · 미발견', ok=False, state='locked',
                                     icon=fit(silhouette(image))))
                else:
                    rows.append(dict(kind='none', id=f'n_{sp}_{var}', name=normal_label(sp, var),
                                     sub=f'방문 {e["v"]}회', price=cond('normal'),
                                     ok=False, state='owned', icon=fit(image)))
        return rows

    def simple_row(game, key, name, image, label, hint=''):
        e = game.col['guests'].get(key)
        if not e or e['v'] <= 0:
            return dict(kind='none', id=key, name='???', sub=hint or '어딘가 낯익은 분위기의 가족 손님이다',
                        price=f'{label} · 미발견', ok=False, state='locked', icon=fit(silhouette(image)))
        return dict(kind='none', id=key, name=name, sub=f'방문 {e["v"]}회', price=label,
                    ok=False, state='owned', icon=fit(image))

    def dex_rows(game, sub):
        if sub == 'normal':
            return [*normal_rows(game), dict(kind='hdr', name='계절·기념일 손님'), *dex_rows(game, 'fam_occasion')]
        if sub in ('rare', 'legend'):
            ids = rare_ids if sub == 'rare' else legend_ids
            label = '희귀 손님' if sub == 'rare' else '전설 손님'
            return [guest_row(game, k, specials.SPECIAL[k], special_surf(k, 0, 1),
                              '', label, sub) for k in ids]
        if sub == 'family':          # family names and looks share one tab
            return [dict(kind='hdr', name='가족 이름'), *dex_rows(game, 'famname'),
                    dict(kind='hdr', name='가족 외형'), *dex_rows(game, 'famlook')]
        if sub == 'famname':
            return [simple_row(game, 'famn_' + n, n,
                               family_composite(NAMED_FAMILY[n][0] if n in NAMED_FAMILY else 1 + i,
                                                0, 1, occasion()), '가족 손님', FAMILY_HINT.get(n, ''))
                    for i, n in enumerate(famnames)]
        if sub == 'famlook':
            return [simple_row(game, f'fama_{i}', named_looks[i][0] if i in named_looks else f'가족 외형 {i}',
                               family_composite(i, 0, 1, occasion()), '가족 손님',
                               FAMILY_HINT.get(named_looks[i][0] if i in named_looks else FAMILY_LOOKS.get(i), ''))
                    for i in famlooks]
        return [guest_row(game, 'fam_' + o, OCC_NAME[o], family_composite(1 + i, 0, 1, o),
                          OCC_HINT[o], '일반 손님', 'family') for i, o in enumerate(OCCASIONS)]

    def mate_cost(game, tier):
        best = max((original_price(game, r) for r in cafe.RECIPES if game.rlv[r['id']] > 0), default=40)
        return int(nice_number(best * MATE_RULES[tier][2]))

    def mate_block(game, key, tier):
        """Why this guest cannot be invited yet ('' when every condition is met)."""
        _b, need_lv, _g, need_mates = MATE_RULES[tier]
        e = game.col['guests'].get(key, {})
        if key.startswith('famn_'):      # family names gain no friendship level: visits stand in for it
            if e.get('v', 0) < STEPS[need_lv - 1]:
                return f'방문 {STEPS[need_lv - 1]}회 필요 (지금 {e.get("v", 0)}회)'
        elif e.get('lv', 0) < need_lv:
            return f'우정 Lv.{need_lv} 필요 (지금 Lv.{e.get("lv", 0)} · 방문 {e.get("v", 0)}회)'
        crew = sum(mate_tier(k) in ('rare', 'family') for k in game.col['mates'])
        if crew < need_mates:
            return f'희귀·가족 동료 {need_mates}명 필요 (지금 {crew}명)'
        return ''

    STAFF_GUEST = {'apprentice': '제빵사 손님', 'clerk': '회사원 손님', 'barista': '바리스타 손님', 'rider': '배민 손님',
                   'patissier': '파티시에 손님', 'chef': '수석 셰프 손님'}

    def staff_rows(game):
        """The old staff hires, now listed first among the normal guests (hire id 'staff:<sid>')."""
        rows = []
        for sd in cafe.STAFF:
            sid, level = sd['id'], game.staff_n[sd['id']]
            name = STAFF_GUEST.get(sid, sd['name'])
            icon = fit(cafe.icon_for('staff', sid))
            if level == 0:
                cost = cafe.staff_cost(sd, 0)
                rows.append(dict(kind='mate', id='staff:' + sid, name=name, icon=icon, state='buy',
                                 ok=game.money >= cost, price=f'영입 {cafe.fmt(cost)}', sub=sd['desc']))
                continue
            work = (f'근무 {_hours(game.staff_work[sid])}/{_hours(staff_target(level))}'
                    if level < sd['max'] else '최대 성장')
            rows.append(dict(kind='mate', id='staff:' + sid, name=f'★ {name}  Lv.{level}/{sd["max"]}',
                             icon=icon, state='owned', ok=False, price=work,
                             sub=f'수익 +{int(sd["bonus"] * level * 100)}%'))
        return rows

    def mate_rows(game, sub):
        tier = sub[2:]
        bonus_each = MATE_RULES[tier][0]
        if tier == 'normal':
            items = [(f'n_{sp}_{v}', normal_label(sp, v), animal_icon(sp, v))
                     for sp, looks in cafe.SPECIES.items() for v in range(len(looks))]
            items += [(k, fam_label(k), fam_image(k)) for k in ['fam_' + o for o in OCCASIONS]]
        elif tier == 'family':
            items = [(k, fam_label(k), fam_image(k)) for k in ['famn_' + n for n in famnames]]
        else:
            items = [(k, specials.SPECIAL[k], special_surf(k, 0, 1)) for k in (rare_ids if tier == 'rare' else legend_ids)]
        cost = mate_cost(game, tier)
        rows = staff_rows(game) if tier == 'normal' else []
        for key, name, image in items:
            if key in game.col['mates']:
                lv = mate_lv(game.col, key)
                work = (f'근무 {_hours(game.col["mate_work"].get(key, 0))}/{_hours(staff_target(lv))}'
                        if lv < MATE_MAX_LV else '최대 성장')
                is_rep = game.col.get('rep') == key
                rows.append(dict(kind='mate', id=key, name=f'{"◆ 대표" if is_rep else "★"} {name}  Lv.{lv}/{MATE_MAX_LV}',
                                 state='owned', ok=False, icon=fit(image), price=work,
                                 sub=f'수익 +{mate_bonus(game.col, key) * 100:.2g}% · ' +
                                     ('눌러서 쉬게 하기' if is_rep else '눌러서 대표로 세우기')))
            elif not seen(game, key):
                rows.append(dict(kind='mate', id=key, name='???', state='locked', ok=False,
                                 icon=fit(silhouette(image)), price=MATE_TIER_NAME[tier] + ' · 미발견',
                                 sub='가게 방문 후 동료 해금'))
            else:
                why = mate_block(game, key, tier)
                rows.append(dict(kind='mate', id=key, name=name, icon=fit(image), ok=not why and game.money >= cost,
                                 state='locked' if why else 'buy', price=f'영입 {cafe.fmt(cost)}',
                                 sub=why or f'수익 +{bonus_each * 100:g}%'))
        return rows

    def mate_name(key):
        tier = mate_tier(key)
        if key.startswith(('fam_', 'famn_')):
            return fam_label(key)
        if tier == 'normal':
            _n, sp, var = key.split('_')
            return normal_label(sp, int(var))
        return specials.SPECIAL.get(key, key)

    def mate_image(key, frame, facing):
        """Walking sprite of a companion, as (surface, feet offset y) -- same art the guest has in the cafe."""
        tier = mate_tier(key)
        if key.startswith(('fam_', 'famn_')):
            return fam_image(key, frame, facing), 12, 32
        if tier == 'normal':
            _n, sp, var = key.split('_')
            surf = pygame.Surface((40, 44), pygame.SRCALPHA)
            cafe.draw_animal(surf, 20, 36, sp, int(var), cafe.CUST_SHIRTS[0], None, frame, facing)
            return surf, 20, 36
        if tier == 'family':
            return fam_image(key, frame, facing), 12, 32
        return special_surf(key, frame, facing), 11, 24

    class Mate(cafe.Staff):
        """The representative companion: wanders the back aisle like the old cafe staff did."""

        def __init__(self, key, game):
            self.mate_key, self.game = key, game
            super().__init__(dict(id='mate', zone=MATE_ZONE, look={}), game.staff)

        def can_stand(self, x, y, coworkers):
            body = self.body_rect(x, y).inflate(4, 4)
            if body.colliderect(pygame.Rect(cafe.OWNER_POS[0] - 12, cafe.OWNER_POS[1] - 31, 24, 35)):
                return False
            g = self.game
            solid = [cafe.furn_rect(cafe.FURN_BY_ID[i]) for i in g.furn if i in cafe.FURN_BY_ID]
            solid += [pygame.Rect(d['x'], d['y'], d['w'], d['h'])
                      for d in (cafe.STAND_BY_ID[i] for i in g.stands if i in cafe.STAND_BY_ID)]
            if any(r.bottom > cafe.WALL_B + 4 and body.colliderect(r) for r in solid):
                return False
            return not any(body.colliderect(self.body_rect(p.x, p.y)) for p in coworkers if p is not self)

        def draw(self, s, t=0):
            frame = 1 + self.frame % 2 if self.moving else 0
            image, ox, oy = mate_image(self.mate_key, frame, self.facing)
            cafe._shadow(s, int(self.x) - 7, int(self.y) - 3, 14, 5, 60)
            s.blit(image, (int(self.x) - ox, int(self.y) - oy))

    def sync_staff(self):
        """The hired staff no longer stand in the cafe: only the chosen representative companion does."""
        key = self.col.get('rep') if getattr(self, 'col', None) else None
        if key not in (self.col['mates'] if getattr(self, 'col', None) else ()):
            key = None
        if key is None:
            self.staff.clear()
        elif not (len(self.staff) == 1 and getattr(self.staff[0], 'mate_key', None) == key):
            self.staff[:] = [Mate(key, self)]

    def set_rep(game, key):
        game.col['rep'] = None if game.col.get('rep') == key else key
        game.toast(f'{mate_name(key)}이(가) 대표 동료로 가게에 나와요' if game.col['rep'] else '대표 동료를 쉬게 했어요')
        game.sync_staff()

    def invite(game, key):
        if key in game.col['mates']:
            set_rep(game, key)
            return
        tier = mate_tier(key)
        cost = mate_cost(game, tier)
        if key in game.col['mates'] or not seen(game, key) or mate_block(game, key, tier):
            return
        if game.money < cost:
            game.toast(f'골드가 부족해요 ({cafe.fmt(cost)} 필요)')
            return
        game.money -= cost
        game.col['mates'].append(key)
        game.col['mate_lv'][key] = 1
        if not game.col.get('rep'):
            game.col['rep'] = key
        if key.startswith(('fam_', 'famn_')):
            name = fam_label(key)
        elif tier == 'normal':
            _n, sp, var = key.split('_')
            name = normal_label(sp, int(var))
        else:
            name = specials.SPECIAL.get(key, key)
        game.toast(f'{name}이(가) 동료가 되었어요! 수익 +{MATE_RULES[tier][0] * 100:g}%')
        game.recalc()      # also puts the representative in the cafe

    def crew_mate(self):
        return self.tab == staff_tab

    def valid_sub(cat, sub):
        # A stale tab-strip hit can store another category's sub id; fall back to the first tab.
        return sub if any(sub == sid for sid, _ in SUBTABS[cat]) else SUBTABS[cat][0][0]

    def mate_sub(self):
        return valid_sub('mate', getattr(self, 'dex_subs', {}).get('mate'))

    def cat_sub(self):
        cat = 'mate' if self.tab == staff_tab else getattr(self, 'dex_cat', 'guest')
        if cat not in SUBTABS:
            cat = 'guest'
        return cat, valid_sub(cat, getattr(self, 'dex_subs', {}).get(cat))

    def trophy_icon(done):
        icon = pygame.Surface((46, 46), pygame.SRCALPHA)
        body, edge = ((250, 200, 70), (150, 100, 20)) if done else ((190, 176, 160), (130, 116, 100))
        pygame.draw.circle(icon, edge, (23, 23), 21)
        pygame.draw.circle(icon, body, (23, 23), 18)
        star = []
        for k in range(10):
            vec = pygame.math.Vector2(12 if k % 2 == 0 else 5, 0).rotate(-90 + k * 36)
            star.append((23 + vec.x, 23 + vec.y))
        pygame.draw.polygon(icon, (255, 255, 255) if done else (225, 214, 200), star)
        return icon

    def skin_icon(skin):
        icon = pygame.Surface((46, 30), pygame.SRCALPHA)
        pygame.draw.rect(icon, skin['edge'], (0, 0, 46, 30), border_radius=6)
        pygame.draw.rect(icon, skin['fill'], (3, 3, 40, 24), border_radius=4)
        pygame.draw.circle(icon, skin['text'], (12, 15), 4)
        pygame.draw.rect(icon, skin['text'], (21, 11, 18, 8), border_radius=2)
        return icon

    def ach_rows(game, sub):
        done_ids = set(game.col['ach'])
        names = {d[0]: d[1] for d in ach_defs()}
        rows = []
        if sub == 'ach_list':
            for aid, name, have, total in ach_defs():
                done = aid in done_ids
                pct_, mult = reward_of(aid)
                skin = next((k for k in SKINS if k['ach'] == aid), None)
                reward = f'수익 +{pct_ * 100:g}% · 골드' + (f' · {skin["name"]}' if skin else '')
                rows.append(dict(kind='none', id=aid, name=('★ ' if done else '') + name,
                                 sub='달성 완료' if done else f'진행 {min(have(game), total)}/{total}',
                                 price=reward, ok=False, state='owned' if done else 'locked',
                                 icon=trophy_icon(done)))
            return rows
        for skin in SKINS:
            if skin_ok(game, skin):
                using = real_skin(game)['id'] == skin['id']
                rows.append(dict(kind='skin', id=skin['id'], name=skin['name'],
                                 sub='사용 중' if using else '눌러서 미리보기', price='툴바',
                                 ok=False, state='owned', icon=skin_icon(skin)))
            else:
                rows.append(dict(kind='none', id=skin['id'], name=skin['name'],
                                 sub=f'업적 "{names[skin["ach"]]}" 달성 시 해금', price='잠김',
                                 ok=False, state='locked', icon=skin_icon(skin)))
        return rows

    def prefix(cat, sub):
        return {'guest': 'g:', 'mate': 'm:'}.get(cat) or ('a:' if sub == 'ach_list' else 's:')

    def build_rows(ui, cat, sub):
        return (ach_rows(ui.g, sub) if cat == 'ach' else
                mate_rows(ui.g, sub) if cat == 'mate' else dex_rows(ui.g, sub))

    def badged(icon):
        if min(icon.get_size()) < 24:
            return icon
        icon = icon.copy()
        pygame.draw.circle(icon, (255, 255, 255), (8, 8), 8)
        pygame.draw.circle(icon, (220, 50, 50), (8, 8), 7)
        cafe.text(icon, 'N', 10, (255, 255, 255), 8, 8, True, 'mc', False, False)
        return icon

    def flag_loc(key):
        kind, _, rest = key.partition(':')
        if kind in ('v', 'b'):
            return ('recipe', '')
        if kind == 'a':
            return ('ach', 'ach_list')
        if kind == 's':
            return ('ach', 'ach_skin')
        sub = ('normal' if rest.startswith(('n_', 'fam_')) else
               'family' if rest.startswith(('famn_', 'fama_')) else
               'legend' if rest in legend_ids else 'rare')
        return ('guest', sub)

    def rows(self):
        if getattr(self, '_drawing_book', False) or self.tab == book_tab or crew_mate(self):
            cat, sub = cat_sub(self)
            fresh = set(self.g.col['new'])
            out = []
            n = 0
            for row in build_rows(self, cat, sub):
                if row.get('kind') == 'hdr':
                    out.append(row)
                    n = 0
                    continue
                n += 1
                row = dict(row, name=f'No.{n:02d} {row["name"]}')
                if prefix(cat, sub) + row['id'] in fresh and row['state'] == 'owned':
                    row['icon'] = badged(row['icon'])
                out.append(row)
            return out
        result = original_rows(self)
        if self.tab == 1 and recipe_sub(self) != 'normal':
            return variant_rows(self.g, recipe_sub(self))
        if self.tab == 1:
            fresh = recipe_fresh(self.g)
            for i, row in enumerate(result):
                if row.get('kind') == 'recipe' and row.get('state') == 'owned':
                    if row['id'] in fresh:
                        row['icon'] = badged(row['icon'])
                    result[i] = row
        return result

    RECIPE_SUBS = (('normal', '일반'),) + tuple((v[0], v[1]) for v in reversed(VARIANTS))   # 일반·딸기·초코·황금·무지개

    def recipe_sub(self):
        return getattr(self, 'recipe_sub_id', 'normal')

    STRAWBERRY_STICKER = ('..gg.gg..', '...ggg...', '.rrrrrrr.', 'rrrwrrwrr', 'rrrrrrrrr',
                          'rwrrrwrrr', '.rrrrrrr.', '..rrwrr..', '...rrr...')
    STICKER_PIXELS = {'g': (96, 178, 84), 'r': (232, 64, 84), 'w': (255, 214, 220)}
    RAINBOW_BANDS = ((236, 72, 72), (255, 160, 60), (255, 226, 80), (92, 190, 100), (80, 150, 240))
    sticker_cache = {}

    def sticker_art(vid):
        if vid == 'strawberry':
            art = pygame.Surface((9, 9), pygame.SRCALPHA)
            for y, row in enumerate(STRAWBERRY_STICKER):
                for x, ch in enumerate(row):
                    if ch in STICKER_PIXELS:
                        art.set_at((x, y), STICKER_PIXELS[ch])
        elif vid == 'choco':
            art = pygame.Surface((9, 9), pygame.SRCALPHA)
            art.fill((126, 78, 50))
            for x, y, w, h in ((0, 0, 4, 4), (5, 0, 4, 4), (0, 5, 4, 4), (5, 5, 4, 4)):
                art.fill((168, 112, 76), (x, y, w, 1))
                art.fill((168, 112, 76), (x, y, 1, h))
            art.fill((84, 48, 32), (4, 0, 1, 9))
            art.fill((84, 48, 32), (0, 4, 9, 1))
        else:
            art = pygame.Surface((13, 7), pygame.SRCALPHA)
            for y in range(7):
                for x in range(13):
                    d = ((x - 6) ** 2 + (y - 6) ** 2) ** .5
                    if 2.5 <= d < 7.5:
                        art.set_at((x, y), RAINBOW_BANDS[int(d - 2.5)])
        return art

    def sticker_for(vid):
        if vid not in sticker_cache:
            art = sticker_art(vid)
            w, h = art.get_size()
            sheet = pygame.Surface((w + 4, h + 4), pygame.SRCALPHA)
            mask = pygame.mask.from_surface(art)
            for radius, color in ((2, (70, 44, 32, 255)), (1, (255, 255, 255, 255))):
                shape = mask.to_surface(setcolor=color, unsetcolor=(0, 0, 0, 0))
                for dx in range(-radius, radius + 1):
                    for dy in range(-radius, radius + 1):
                        sheet.blit(shape, (2 + dx, 2 + dy))
            sheet.blit(art, (2, 2))
            sticker_cache[vid] = sheet
        return sticker_cache[vid]

    def variant_icon(rid, vid):
        """Base bread icon with the variant sticker on its bottom-right corner."""
        icon = cafe.icon_for('recipe', rid)
        if vid not in ('strawberry', 'choco', 'rainbow'):
            return icon
        key = ('variant', rid, vid)
        if key not in cafe.icon_cache:
            sticker = sticker_for(vid)
            out = icon.copy()
            out.blit(sticker, (out.get_width() - sticker.get_width(), out.get_height() - sticker.get_height()))
            cafe.icon_cache[key] = out
        return cafe.icon_cache[key]

    cafe.variant_icon = variant_icon

    def variant_rows(game, vid):
        v = next(x for x in VARIANTS if x[0] == vid)
        rows = []
        for recipe in cafe.RECIPES:
            rid = recipe['id']
            if game.rlv[rid] <= 0:
                continue
            n = game.col['variants'].get(rid, {}).get(vid, 0)
            icon = variant_icon(rid, vid)
            if n:
                rows.append(dict(kind='none', id=rid, name=f'{v[1]} {recipe["name"]}',
                                 sub=f'{n}회 발견 · 판매가 {v[3]:g}배',
                                 price='발견 완료', ok=False, state='owned', icon=icon))
            else:
                rows.append(dict(kind='none', id=rid, name='???',
                                 sub=f'{v[1]} {recipe["name"]} · 판매 시 {v[2] * 100:g}% 확률로 등장',
                                 price='미발견', ok=False, state='locked',
                                 icon=cafe.icon_for('recipe', rid, 'hidden')))
        return rows

    def recipe_sub_counts(game):
        owned = sum(game.rlv[r['id']] > 0 for r in cafe.RECIPES)
        out = {'normal': f'{owned}/{len(cafe.RECIPES)}'}
        for vid, *_ in VARIANTS:
            out[vid] = f'{sum(vid in f for f in game.col["variants"].values())}/{owned}'
        return out

    def recipe_subtabs(self, surface):
        px, py, pw = cafe.PANEL_X, cafe.PANEL_Y, cafe.PANEL_W
        label, cur = recipe_sub_counts(self.g), recipe_sub(self)
        band = pygame.Rect(px + 4, py + 88, pw - 8, 30)
        pygame.draw.rect(surface, (250, 232, 196), band)
        bw = (band.w - 4) // len(RECIPE_SUBS)
        for i, (sid, name) in enumerate(RECIPE_SUBS):
            rect = pygame.Rect(band.x + 2 + i * bw, band.y + 3, bw - 3, 24)
            active = sid == cur
            pygame.draw.rect(surface, (232, 150, 70) if active else (214, 184, 140), rect)
            pygame.draw.rect(surface, (54, 34, 24), rect, 2)
            caption = f'{name} {label[sid]}'
            size = 11
            while size > 8 and cafe.font(size, True).size(caption)[0] > rect.w - 8:
                size -= 1
            cafe.text(surface, caption, size, (255, 255, 255) if active else (84, 52, 34),
                      rect.centerx, rect.centery, True, 'mc')
            self._dex_hits.append((rect, 'rsub', sid))

    def recipe_fresh(game):
        return {k[2:] if k[0] == 'b' else k.partition('_')[2] for k in game.col['new'] if k[:2] in ('b:', 'v:')}

    def counts(game):
        guests = game.col['guests']
        normals = [f'n_{sp}_{v}' for sp, looks in cafe.SPECIES.items() for v in range(len(looks))]
        seen = lambda k: guests.get(k, {}).get('v', 0) > 0
        fam = ['fam_' + o for o in OCCASIONS]
        groups = dict(normal=normals + fam, rare=rare_ids, family=[], legend=legend_ids,
                      famname=['famn_' + n for n in famnames], famlook=[f'fama_{i}' for i in famlooks])
        out = {k: f'{sum(seen(i) for i in v)}/{len(v)}' for k, v in groups.items()}
        every = groups['family'] + groups['famname'] + groups['famlook']
        out['family'] = f'{sum(seen(i) for i in every)}/{len(every)}'
        total = sum(map(len, groups.values()))
        out['guest'] = f'{sum(seen(i) for v in groups.values() for i in v)}/{total}'
        defs = ach_defs()
        out['ach'] = out['ach_list'] = f'{sum(d[0] in game.col["ach"] for d in defs)}/{len(defs)}'
        mates = game.col['mates']
        tiers = dict(m_normal=normals + fam, m_rare=rare_ids, m_family=groups['famname'], m_legend=legend_ids)
        for sid, ids in tiers.items():
            out[sid] = f'{sum(i in mates for i in ids)}/{len(ids)}'
        out['mate'] = f'{len(mates)}/{sum(map(len, tiers.values()))}'
        out['ach_skin'] = f'{sum(skin_ok(game, k) for k in SKINS)}/{len(SKINS)}'
        return out

    SUB_H = 34

    original_draw_row = UI.draw_row

    def draw_row(self, ui, rect, r, mouse, area):
        result = original_draw_row(self, ui, rect, r, mouse, area)
        if r.get('sub2'):       # condition continues on a second line instead of being cut off
            cafe.text(ui, r['sub2'], 12, (130, 100, 76), rect.x + 66, rect.y + 41)
        if r.get('kind') == 'skin':
            self._skin_hits.append((rect.clip(area), r['id']))
        elif r.get('kind') == 'none' and r.get('state') == 'locked' and r.get('id') in SKIN_BY_ID:
            self._skin_hits.append((rect.clip(area), r['id']))
        elif r.get('kind') == 'mate' and r.get('state') in ('buy', 'owned'):
            self._mate_hits.append((rect.clip(area), r['id']))
            if r['state'] == 'buy':
                self._mate_info[r['id']] = (r['name'], r.get('icon'))
                # the green hire box drawn by the base row: bottom-right, sized by its label
                width = min(rect.w - 76, max(110, cafe.font(13, True).size('구매 ' + r['price'])[0] + 20))
                box = pygame.Rect(rect.right - width - 8, rect.bottom - 26, width, 22)
                self._mate_btn[r['id']] = box.inflate(8, 6).clip(area)
        if r.get('id') in SKIN_BY_ID and r.get('kind') in ('skin', 'none'):
            using = r.get('state') == 'owned' and 'using' in r and r['using']
            locked = r.get('state') == 'locked'
            using = r.get('sub') == '사용 중'
            label = '잠김' if locked else ('사용 중' if using else '적용')
            width = min(rect.w - 76, max(80, cafe.font(13, True).size(label)[0] + 20))
            box = pygame.Rect(rect.right - width - 8, rect.bottom - 26, width, 22)
            on = not locked and not using
            pygame.draw.rect(ui, (214, 238, 206) if on else (226, 214, 190), box)
            pygame.draw.rect(ui, (70, 170, 90) if on else (150, 130, 100), box, 2)
            cafe.text(ui, label, 13, (40, 100, 55) if on else (130, 110, 86), box.centerx, box.centery, True, 'mc')
            self._skin_btn[r['id']] = box.inflate(8, 6).clip(area) if on else pygame.Rect(0, 0, 0, 0)
        mark = None
        if r.get('kind') in ('skin', 'none') and r.get('id') in SKIN_BY_ID:
            mark = 'skin' if getattr(self, 'preview', None) == ('skin', r['id']) else None
        elif r.get('kind') == 'mate' and getattr(self, 'preview', None) == ('mate', r['id']):
            mark = 'mate'
        if mark:
            box = rect.clip(area)
            pygame.draw.rect(ui, (70, 170, 90), box, 3)
        return result

    def recipe_banner(self, surface):
        game = self.g
        got = sum(game.rlv[r['id']] > 0 for r in cafe.RECIPES)
        found = sum(len(f) for f in game.col['variants'].values())
        pygame.draw.rect(surface, (250, 232, 196), (cafe.PANEL_X + 4, cafe.PANEL_Y + 52, cafe.PANEL_W - 8, 36))
        cafe.text(surface, f'빵 {got}/{len(cafe.RECIPES)} · 특별빵 {found}/{len(VARIANTS) * len(cafe.RECIPES)}'
                           ' · 판매하면 빵 레벨이 올라요', 12, (110, 76, 52), cafe.PANEL_X + 12, cafe.PANEL_Y + 62, True)

    def crew_strips(self, surface):
        px, py, pw = cafe.PANEL_X, cafe.PANEL_Y, cafe.PANEL_W
        label = counts(self.g)
        pygame.draw.rect(surface, (250, 232, 196), (px + 4, py + 52, pw - 8, 36))
        cafe.text(surface, f'동료 {label["mate"]} · 근무하면 성장', 12,
                  (110, 76, 52), px + 12, py + 62, True)

        def strip(y, items, current, kind, names):
            band = pygame.Rect(px + 4, y, pw - 8, 30)
            pygame.draw.rect(surface, (250, 232, 196), band)
            bw = (band.w - 4) // len(items)
            for i, (sid, name) in enumerate(items):
                rect = pygame.Rect(band.x + 2 + i * bw, band.y + 3, bw - 3, 24)
                active = sid == current
                pygame.draw.rect(surface, (232, 150, 70) if active else (214, 184, 140), rect)
                pygame.draw.rect(surface, (54, 34, 24), rect, 2)
                caption = f'{name} {names.get(sid, "")}'.strip()
                size = 12
                while size > 8 and cafe.font(size, True).size(caption)[0] > rect.w - 8:
                    size -= 1
                cafe.text(surface, caption, size, (255, 255, 255) if active else (84, 52, 34),
                          rect.centerx, rect.centery, True, 'mc')
                self._dex_hits.append((rect, kind, sid))

        strip(py + 88, SUBTABS['mate'], cat_sub(self)[1], 'sub', label)

    def draw(self, surface, mouse):
        self._skin_hits, self._mate_hits, self._mate_info, self._mate_btn = [], [], {}, {}
        self._skin_btn = {}
        in_book = self.tab == book_tab
        if getattr(self, 'preview', None) and (self.tab, self.preview[0]) not in (
                (staff_tab, 'mate'), (book_tab, 'skin')):
            self.preview = None
        saved = cafe.LIST_OFF
        if in_book or self.tab == 1:
            cafe.LIST_OFF = saved + SUB_H
        elif self.tab == staff_tab:
            cafe.LIST_OFF = saved + SUB_H
        try:
            original_draw(self, surface, mouse)
        finally:
            cafe.LIST_OFF = saved
        self.g.skin_preview = self.preview[1] if getattr(self, 'preview', None) and self.preview[0] == 'skin' else None
        self._dex_hits = []
        view = cat_sub(self) if in_book else None
        last = getattr(self, '_dex_view', None)
        if last and last != view:      # the player left a list: its N marks are seen now
            ids = {prefix(*last) + r['id'] for r in build_rows(self, *last) if 'id' in r}
            self.g.col['new'] = [k for k in self.g.col['new'] if k not in ids]
        self._dex_view = view
        if self.tab == 1:
            recipe_banner(self, surface)
            recipe_subtabs(self, surface)
        elif getattr(self, '_recipe_seen', False):     # left the recipe tab: its N marks are seen now
            self.g.col['new'] = [k for k in self.g.col['new'] if k[:2] not in ('b:', 'v:')]
        self._recipe_seen = self.tab == 1
        if self.tab == staff_tab:
            crew_strips(self, surface)
            pv = getattr(self, 'preview', None)
            if pv and pv[1] in self._mate_info:
                name, icon = self._mate_info[pv[1]]
                strip = pygame.Rect(cafe.PANEL_X + 4, cafe.PANEL_Y + 52, cafe.PANEL_W - 8, 36)
                pygame.draw.rect(surface, (214, 238, 206), strip)
                if icon is not None:
                    h = 32
                    surface.blit(pygame.transform.smoothscale(icon, (max(1, icon.get_width() * h // icon.get_height()), h)),
                                 (strip.x + 6, strip.y + 2))
                cafe.text(surface, f'미리보기 · {name}', 12, (40, 120, 60),
                          strip.x + 50, strip.centery, True, 'ml')
            return
        if not in_book:
            if recipe_fresh(self.g):
                tw = (cafe.PANEL_W - 16) // len(cafe.TABS)
                rect = pygame.Rect(cafe.PANEL_X + 8 + tw, cafe.PANEL_Y + 8, tw - 2, 40)
                pygame.draw.circle(surface, (255, 255, 255), (rect.right - 6, rect.y + 6), 6)
                pygame.draw.circle(surface, (220, 50, 50), (rect.right - 6, rect.y + 6), 5)
            return
        fresh = [flag_loc(k) for k in self.g.col['new']]
        px, py, pw = cafe.PANEL_X, cafe.PANEL_Y, cafe.PANEL_W
        cat, sub = cat_sub(self)
        label = counts(self.g)

        def buttons(y, h, items, current, kind):
            band = pygame.Rect(px + 4, y, pw - 8, h + 6)
            pygame.draw.rect(surface, (250, 232, 196), band)
            bw = (band.w - 4) // len(items)
            for i, (sid, name) in enumerate(items):
                rect = pygame.Rect(band.x + 2 + i * bw, band.y + 3, bw - 3, h)
                active = sid == current
                pygame.draw.rect(surface, (232, 150, 70) if active else (214, 184, 140), rect)
                pygame.draw.rect(surface, (54, 34, 24), rect, 2)
                caption = f'{name} {label[sid]}'
                size = 12 if kind == 'cat' else 11
                while size > 8 and cafe.font(size, True).size(caption)[0] > rect.w - 8:
                    size -= 1                  # long tab names shrink instead of being clipped
                cafe.text(surface, caption, size,
                          (255, 255, 255) if active else (84, 52, 34), rect.centerx, rect.centery, True, 'mc')
                self._dex_hits.append((rect, kind, sid))
                if any((loc[0] == sid) if kind == 'cat' else (loc == (cat, sid)) for loc in fresh):
                    pygame.draw.circle(surface, (255, 255, 255), (rect.right - 6, rect.y + 6), 6)
                    pygame.draw.circle(surface, (220, 50, 50), (rect.right - 6, rect.y + 6), 5)

        buttons(py + 52, 30, CATS, cat, 'cat')
        buttons(py + 88, 24, SUBTABS[cat], sub, 'sub')

    def click(self, pos, game, scene_clicks):
        if self.tab == 1:
            for rect, kind, sid in getattr(self, '_dex_hits', ()):
                if kind == 'rsub' and rect.collidepoint(pos):
                    self.recipe_sub_id = sid
                    self.scroll[1] = 0
                    return
        if self.tab in (book_tab, staff_tab):
            for rect, kind, sid in getattr(self, '_dex_hits', ()):
                if rect.collidepoint(pos):
                    if kind == 'cat':
                        self.dex_cat = sid
                    else:
                        cat = 'mate' if self.tab == staff_tab else getattr(self, 'dex_cat', 'guest')
                        self.dex_subs = dict(getattr(self, 'dex_subs', {}), **{cat: sid})
                    self.scroll[self.tab] = 0
                    self.preview = None
                    return
            for rect, key in getattr(self, '_mate_hits', ()):
                if rect.collidepoint(pos):
                    if key in self._mate_info and not self._mate_btn[key].collidepoint(pos):
                        self.preview = ('mate', key)         # the row previews; only the hire box hires
                        return
                    self.preview = None
                    if key.startswith('staff:'):
                        game.hire(key[6:])
                    else:
                        invite(game, key)
                    return
            for rect, sid in getattr(self, '_skin_hits', ()):
                if rect.collidepoint(pos):
                    if self._skin_btn.get(sid, rect).collidepoint(pos) and skin_ok(game, SKIN_BY_ID[sid]):
                        self.preview = None
                        game.col['skin'] = sid       # only the apply box applies; the row previews
                    else:
                        self.preview = ('skin', sid)
                    return
            on_tab_strip = any(kind == 'tab' and rect.collidepoint(pos) for rect, kind, *_ in self.hit)
            if crew_mate(self) and not on_tab_strip:
                return                  # companion rows are not staff hires
        return original_click(self, pos, game, scene_clicks)

    original_update = Game.update

    def update(self, dt, *args, **kwargs):
        result = original_update(self, dt, *args, **kwargs)
        work = dt if 0 < dt <= 1.0 else 0.0         # same rule as staff: no growth during stalls
        if work and self.col['mates']:
            grown = False
            for key in self.col['mates']:
                lv = mate_lv(self.col, key)
                if lv >= MATE_MAX_LV:
                    continue
                done = self.col['mate_work'].get(key, 0.0) + work
                while lv < MATE_MAX_LV and done >= staff_target(lv):
                    done -= staff_target(lv)
                    lv += 1
                    grown = True
                    self.toast(f'{mate_name(key)} 근무 성장 Lv.{lv}!')
                self.col['mate_work'][key] = 0.0 if lv >= MATE_MAX_LV else done
                self.col['mate_lv'][key] = lv
            if grown:
                self.recalc()
        self._col_t = getattr(self, '_col_t', 0.0) + dt
        if self._col_t >= 1.0:
            self._col_t = 0.0
            check(self)
        return result

    Game.update = update
    Game.sync_staff = sync_staff
    Game.skin_palette = skin_palette
    Game.__init__, Game.price, Game.save, Game.load = init, price, save, load
    Game.spawn_customer, Game.customer_paid = spawn, paid
    Customer.draw_label = draw_label
    UI.rows, UI.draw, UI.click, UI.draw_row = rows, draw, click, draw_row
