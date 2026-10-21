"""Seasonal theme packs: 70 pieces from assets/themes wired into the game.

Per theme (spring / summer / autumn / winter / golden):
  furniture  table -> table slot (2~4 seats like tableL2), seat -> tableR2 spot,
             decoration -> big plant spot, corner -> small plant spot,
             stand -> "display skin" that restyles every stand
  interior   wall, floor, sign, light  (wall/floor/sign/light shop categories)
  character  hair, outfit_1/2 (tops), accessory_1/2 (acc)

Furniture can be owned several at once per slot; the one you bought last (or
re-applied from the shop row) is shown. Prices/bonuses are the PRICE / BONUS
tables below. Art loads from assets/themes/<theme>/native/<part>.png.
"""
import os
import sys
from functools import lru_cache
from pathlib import Path
from game_data import THEME_ITEM_IDS, read_save, write_save

THEMES = ('spring', 'summer', 'autumn', 'winter', 'golden')
THEME_NAME = {'spring': '벚꽃 봄', 'summer': '바다 여름', 'autumn': '단풍 가을',
              'winter': '겨울 크리스마스', 'golden': '골든 베이커리'}
NAMES = {
    'spring': ('벚꽃 티테이블', '꽃 벤치', '화분 아치', '도시락 소품 코너', '벚꽃 매대', '꽃살 벽지',
               '꽃잎 바닥', '꽃 간판', '등롱 조명', '꽃머리 헤어', '한복풍 앞치마', '봄 원피스', '꽃핀', '양산'),
    'summer': ('비치 테이블', '해먹 좌석', '파라솔', '서핑보드 코너', '바다 매대', '줄무늬 벽',
               '모래 바닥', '닻 간판', '조개 조명', '밀짚모자 헤어', '하와이안 셔츠', '수영복 앞치마', '튜브', '선글라스'),
    'autumn': ('낙엽 테이블', '통나무 벤치', '호박 장식', '허수아비 코너', '단풍 매대', '목재 벽',
               '낙엽 바닥', '호박 간판', '잭오랜턴 조명', '땋은 머리 헤어', '니트 조끼', '망토', '호박 모자', '마녀 모자'),
    'winter': ('트리 테이블', '벽난로 소파', '선물 더미', '눈사람 코너', '크리스마스 매대', '별무늬 벽',
               '눈 바닥', '리스 간판', '오너먼트 조명', '털모자 헤어', '산타 의상', '패딩 조끼', '목도리', '루돌프 머리띠'),
    'golden': ('샹들리에 테이블', '벨벳 소파', '금장 카운터 장식', '케이크 타워', '골든 베이커리 매대', '대리석 벽',
               '금빛 바닥', '금박 간판', '샹들리에 조명', '은발 웨이브 헤어', '연미복 셰프복', '금장 앞치마', '모노클', '셰프 모자'),
}
PARTS = ('table', 'seat', 'decoration', 'corner', 'stand', 'wall', 'floor', 'sign', 'light',
         'hair', 'outfit_1', 'outfit_2', 'accessory_1', 'accessory_2')
# Match the base shop economy; golden pieces cost x2.2 and grant x1.5 bonus.
PRICE = dict(table=2400, seat=3800, decoration=2100, corner=1300, stand=3000,
             wall=2200, floor=2200, sign=4500, light=2500, hair=3300,
             outfit_1=3000, outfit_2=3600, accessory_1=2400, accessory_2=3000)
BONUS = dict(table=.02, seat=.01, decoration=.01, corner=.01, stand=.01, wall=.01, floor=.01,
             sign=.01, light=.01, hair=.01, outfit_1=.01, outfit_2=.01, accessory_1=.01, accessory_2=.01)
PREMIUM_PRICE, PREMIUM_BONUS = 2.2, 1.5

FURN_SLOT = {'table': 'tableL', 'seat': 'tableR', 'decoration': 'plant2', 'corner': 'plant',
             'stand': 'stand_skin'}
FURN_HINT = {'table': '', 'seat': '', 'decoration': '',
             'corner': '', 'stand': ''}
WALL_TINT = {  # wall palette helpers: stripe a/b, trim, wainscot, curtain
    'spring': ((247, 235, 206), (233, 174, 185), (113, 74, 52), (223, 201, 163), (247, 235, 206)),
    'summer': ((247, 235, 206), (145, 190, 208), (113, 74, 52), (227, 201, 155), (247, 235, 206)),
    'autumn': ((213, 138, 66), (166, 93, 53), (65, 46, 40), (189, 135, 87), (247, 235, 206)),
    'winter': ((247, 235, 206), (203, 105, 96), (65, 46, 40), (113, 145, 107), (247, 235, 206)),
    'golden': ((52, 62, 88), (53, 45, 50), (157, 117, 55), (215, 179, 106), (247, 235, 206)),
}
SIGN_TEXT = {  # (centre x, centre y, colour) of the plaque; None = no plaque to write on
    'spring': (32, 12, (113, 74, 52)), 'summer': None, 'autumn': (45, 15, (247, 235, 206)),
    'winter': None, 'golden': (32, 12, (215, 179, 106)),
}
SIZE = {'table': (52, 32), 'seat': (50, 24), 'decoration': (24, 42), 'corner': (32, 32),
        'stand': (64, 36)}
CENTRE = ('hair', 'outfit_1', 'outfit_2', 'accessory_1', 'accessory_2')   # parts drawn on the 24x34 body canvas
ON_FACE = {('summer', 'accessory_2'), ('golden', 'accessory_1')}   # glasses sit over the eyes
LIGHT_X = (98, 150, 205)    # hanging fixtures: x centres, drawn on the wall band
LIGHT_Y = 0


def _asset_dirs():
    here = Path(__file__).resolve().parent
    dirs = [here / 'assets' / 'themes', Path.cwd() / 'assets' / 'themes']
    base = getattr(sys, '_MEIPASS', None)
    if base:
        dirs.insert(0, Path(base) / 'assets' / 'themes')
    return dirs


def install(cafe):
    if getattr(cafe, '_themes_installed', False):
        return
    cafe._themes_installed = True
    pygame, art, dr = cafe.pygame, cafe.art, cafe.art.dr
    Game, UI = cafe.Game, cafe.UI
    state = {'game': None}
    save_path = os.path.join(cafe.SAVE_DIR, 'themes.json')

    # ---- art ---------------------------------------------------------------
    raw = {}

    def load(theme, part):
        key = (theme, part)
        if key not in raw:
            raw[key] = None
            for folder in _asset_dirs():
                path = folder / theme / 'native' / f'{part}.png'
                if path.is_file():
                    try:
                        raw[key] = pygame.image.load(str(path)).convert_alpha()
                    except pygame.error:
                        pass
                    break
        return raw[key]

    def present(theme, part):
        return any((folder / theme / 'native' / f'{part}.png').is_file() for folder in _asset_dirs())

    @lru_cache(maxsize=None)
    def sprite(theme, part):
        """Detail-aware surface: crisp nearest-neighbour scaling at 2x/3x."""
        src = load(theme, part)
        if src is None:
            return None
        w, h = src.get_size()

        def detail(scale):
            expected = (w * scale, h * scale)
            for folder in _asset_dirs():
                path = folder / theme / 'native' / f'{part}@{scale}x.png'
                if path.is_file():
                    image = pygame.image.load(str(path)).convert_alpha()
                    if image.get_size() != expected:
                        raise ValueError(f'{path}: expected {expected}, got {image.get_size()}')
                    return image
            return pygame.transform.scale(src, expected)

        return dr.register(src, detail)

    sign_cache = {}

    def tinted_text(theme, part='sign'):
        """Sign with CAFE written on plaque-style signs."""
        spot = SIGN_TEXT.get(theme)
        base = sprite(theme, part)
        if base is None or spot is None:
            return base
        cx, cy, color = spot
        if theme not in sign_cache:
            out = dr.DetailSurface(base.get_size(), pygame.SRCALPHA)
            out.blit(base, (0, 0))
            cafe.text(out, 'CAFE', 9, color, cx, cy - 4, True, 'tc')
            sign_cache[theme] = out
        return sign_cache[theme]

    # ---- shop tables -------------------------------------------------------
    themed = {}          # id -> dict(theme, part)
    new_furn, new_int = [], {'wall': [], 'floor': [], 'sign': [], 'light': []}
    new_hero = {'hair': [], 'top': [], 'acc': []}
    material = {}        # 'wall6' -> (theme, part)
    base_item = {s['id']: s for s in cafe.FURN}

    def cost(theme, part):
        from progression import COST_UNIT, FURN_COST_MULT, SHOP_COST_MULT
        mult = FURN_COST_MULT if part in FURN_SLOT else SHOP_COST_MULT   # same repricing as the base shop
        value = PRICE[part] * mult * COST_UNIT * (PREMIUM_PRICE if theme == 'golden' else 1)
        from progression import shop_price
        return shop_price(value)

    def bonus(theme, part):
        return max(.01, round(BONUS[part] * (PREMIUM_BONUS if theme == 'golden' else 1), 2))

    def furn_drawer(theme, part, pos):
        def draw(s, t):
            img = sprite(theme, part)
            if img is not None:
                s.blit(img, pos)
        return draw

    def make_sign(theme):
        def draw(s, ox, oy, t):
            img = tinted_text(theme)
            if img is not None:
                s.blit(img, (ox, oy))
        return draw

    for theme in THEMES:
        names = NAMES[theme]
        label = THEME_NAME[theme]
        for pi, part in enumerate(PARTS):
            name = names[pi]
            if not present(theme, part):
                continue
            ident = f'{theme}_{part}'
            themed[ident] = dict(theme=theme, part=part)
            desc = f'{label} 테마'
            if part in FURN_SLOT:
                slot = FURN_SLOT[part]
                item = dict(id=ident, name=name, desc=f'{desc} · {FURN_HINT[part]}' if FURN_HINT[part] else desc, slot=slot, tier=1,
                            cost=cost(theme, part), bonus=bonus(theme, part), themed=True)
                if part == 'table':
                    ref = base_item['tableL2']
                    item.update(by=ref['by'], seats=list(ref['seats']))
                    pos = art.FURN_POS['tableL2']
                elif part == 'seat':
                    ref = base_item['tableR2']
                    item.update(by=ref['by'], seats=list(ref['seats']))
                    pos = art.FURN_POS['tableR2']
                elif part == 'decoration':
                    item['by'] = base_item['plant2']['by']
                    pos = art.FURN_POS['plant2']
                elif part == 'corner':
                    item['by'] = base_item['plant1']['by']
                    pos = (6, 170)
                else:                                   # stand skin: preview over the first stand
                    item['by'] = 120
                    pos = (60, 90)
                w, h = SIZE[part]
                item['rect'] = (pos[0], pos[1], w, h)
                item['draw'] = furn_drawer(theme, part, pos)
                new_furn.append(item)
            elif part in new_int:
                cat = part
                iid = THEME_ITEM_IDS[theme][part]
                item = dict(id=iid, name=name, desc=desc, cost=cost(theme, part),
                            bonus=bonus(theme, part), themed=True)
                themed[iid] = dict(theme=theme, part=part)
                if cat in ('wall', 'floor'):
                    material[iid] = (theme, part)
                elif cat == 'sign':
                    item['draw'] = make_sign(theme)
                else:
                    item['draw'] = None                       # filled in below
                    item['glow'] = [(x + 11, LIGHT_Y + 22, 0.9) for x in LIGHT_X]
                    item['_theme'] = theme
                new_int[cat].append(item)
            else:
                cat = {'hair': 'hair', 'outfit_1': 'top', 'outfit_2': 'top',
                       'accessory_1': 'acc', 'accessory_2': 'acc'}[part]
                hid = THEME_ITEM_IDS[theme][part]
                themed[hid] = dict(theme=theme, part=part)
                tag = f'T:{theme}:{part}'
                if cat == 'hair':
                    value = (tag, (110, 70, 46))
                elif cat == 'top':
                    value = (tag, (250, 250, 250))
                else:
                    value = tag
                new_hero[cat].append(dict(id=hid, name=name, desc=desc, cost=cost(theme, part),
                                          bonus=bonus(theme, part), v=value, themed=True))
    def make_light(theme):
        def draw(s, t):
            img = sprite(theme, 'light')
            for x in LIGHT_X:
                s.blit(img, (x, LIGHT_Y))
        return draw

    for item in new_int['light']:
        item['draw'] = make_light(item.pop('_theme'))

    # ---- wall palettes + material tiles -----------------------------------
    for iid, (theme, part) in material.items():
        if part == 'wall':
            a, b, trim, wain, curt = WALL_TINT[theme]
            cafe.ROOM_PAL[iid] = {'a': a, 'b': b, 'rail': trim, 'wain': wain,
                                  'wain2': tuple(max(0, c - 14) for c in wain), 'trim': trim,
                                  'top': tuple(min(255, c + 14) for c in a), 'cut': a,
                                  'frame': (247, 235, 206), 'curt': curt, 'kind': 'stripe'}
    original_tile = art.material_tile
    tile_cache = {}

    def material_tile(key, flip_x=False, flip_y=False):
        spec = material.get(key)
        if spec is None:
            return original_tile(key, flip_x, flip_y)
        ck = (key, bool(flip_x), bool(flip_y))
        if ck not in tile_cache:
            src = load(*spec)
            fx, fy = bool(flip_x), bool(flip_y)
            w, h = src.get_size()
            flat = pygame.transform.flip(src.convert(), fx, fy)
            tile = sprite(*spec)
            tile_cache[ck] = dr.register(flat, lambda scale: pygame.transform.flip(
                dr.detail(tile, scale).convert(), fx, fy))
        return tile_cache[ck]

    art.material_tile = material_tile

    # ---- register shop items ----------------------------------------------
    for item in new_furn:
        cafe.FURN.append(item)
        cafe.FURN_BY_ID[item['id']] = item
        cafe.FURN_SORTED.append(item)
    for cat, items in new_int.items():
        for item in items:
            cafe.INTERIOR[cat].append(item)
            cafe.INT_BY_ID[item['id']] = (cat, item)
    for cat, items in new_hero.items():
        for item in items:
            cafe.HERO[cat].append(item)
            cafe.HERO_BY_ID[item['id']] = (cat, item)

    # build_sprites() re-runs art_runtime.install, which binds atlas art to every
    # furniture/sign/light entry; themed entries bring their own art, so hide them meanwhile.
    original_build = cafe.build_sprites

    def build_sprites(*args, **kwargs):
        hidden = [(cafe.FURN, [i for i in cafe.FURN if i.get('themed')])]
        hidden += [(cafe.INTERIOR[c], [i for i in cafe.INTERIOR[c] if i.get('themed')])
                   for c in ('sign', 'light')]
        for lst, items in hidden:
            lst[:] = [i for i in lst if i not in items]
        try:
            return original_build(*args, **kwargs)
        finally:
            for lst, items in hidden:
                lst.extend(items)

    cafe.build_sprites = build_sprites

    by_slot = {}
    for item in cafe.FURN:
        by_slot.setdefault(item['slot'], []).append(item)

    # ---- furniture equip: the choice is stored in game.theme_eq ------------
    def blank(self):
        self.theme_eq = {}

    original_init, original_save, original_load = Game.__init__, Game.save, Game.load
    original_owned, original_buy = Game.owned_furn, Game.buy_furn

    def init(self):
        blank(self)
        original_init(self)
        state['game'] = self

    def owned_furn(self, slot):
        have = [f for f in by_slot.get(slot, ()) if f['id'] in self.furn]
        if not have:
            return None
        if len(have) == 1:
            return have[0]
        eq = getattr(self, 'theme_eq', {}).get(slot)
        for f in have:
            if f['id'] == eq:
                return f
        plain = [f for f in have if not f.get('themed')] or have
        return max(plain, key=lambda f: f['tier'])

    def buy_furn(self, fid):
        item = cafe.FURN_BY_ID[fid]
        if not item.get('themed'):
            return original_buy(self, fid)
        slot = item['slot']
        if fid in self.furn:
            if self.theme_eq.get(slot) == fid:
                return False
            self.theme_eq[slot] = fid
            self.toast(f"{item['name']} 적용!")
            return True
        if self.money < item['cost']:
            return False
        self.money -= item['cost']
        self.furn.add(fid)
        self.theme_eq[slot] = fid
        self.toast(f"{item['name']} 구매! 수익 +{int(item['bonus'] * 100 + .5)}%")
        return True

    def save(self):
        original_save(self)
        try:
            write_save(save_path, dict(furn_eq=self.theme_eq))
        except (OSError, TypeError, ValueError):
            pass

    def load_game(self):
        original_load(self)
        self.theme_eq = {}
        try:
            data = read_save(save_path)
            for slot, fid in data.get('furn_eq', {}).items():
                if not isinstance(fid, str):
                    continue
                item = cafe.FURN_BY_ID.get(fid)
                if item and item.get('themed') and item['slot'] == slot and fid in self.furn:
                    self.theme_eq[slot] = fid
        except (OSError, ValueError, AttributeError):
            pass

    Game.__init__, Game.owned_furn, Game.buy_furn = init, owned_furn, buy_furn
    Game.save, Game.load = save, load_game

    # ---- shop rows: owned themed furniture can be re-applied ---------------
    original_furn_rows = UI.furn_rows

    def furn_rows(self, rows, slots):
        start = len(rows)
        original_furn_rows(self, rows, slots)
        g = self.g
        for row in rows[start:]:
            item = cafe.FURN_BY_ID.get(row.get('id'))
            if row.get('kind') == 'furn' and item and item.get('themed') and row['id'] in g.furn:
                on = owned_furn(g, item['slot']) is item
                row.update(price='사용중' if on else '적용하기', state='equipped' if on else 'own',
                           ok=not on)
        if 'plant' in slots and 'plant2' in slots:      # accessory list: split window / corner decorations
            groups = (('plant2', '창가 장식'), ('plant', '구석 장식'))
            own = rows[start:]
            slot_of = lambda row: (cafe.FURN_BY_ID.get(row.get('id')) or {}).get('slot')
            tail = [r for r in own if slot_of(r) not in ('plant2', 'plant')]
            head = []
            for slot, title in groups:
                part = [r for r in own if slot_of(r) == slot]
                if part:
                    head += [dict(kind='hdr', name=title), *part]
            rows[start:] = head + tail
        return None

    UI.furn_rows = furn_rows

    original_rows = UI.rows

    def rows(self):
        result = original_rows(self)
        if self.tab == 2:
            result.append(dict(kind='hdr', name='진열대 스킨 (모든 판매대에 적용)'))
            self.furn_rows(result, {'stand_skin'})
        return result

    UI.rows = rows

    # ---- stand skins -------------------------------------------------------
    original_layers = art.stand_layers
    skin_cache = {}

    original_preview = UI.preview_game

    def preview_game(self):
        view = original_preview(self)
        state['view'] = view if view is not self.g else None
        return view

    UI.preview_game = preview_game

    def stand_layers(key):
        game = state.get('view') or state['game']
        skin = None
        if game is not None:
            owned = owned_furn(game, 'stand_skin')
            if owned is not None:
                skin = owned['id']
        if skin is None:
            return original_layers(key)
        if skin not in skin_cache:
            theme = themed[skin]['theme']
            base = sprite(theme, 'stand')
            front = dr.register(pygame.Surface(base.get_size(), pygame.SRCALPHA),
                                lambda scale: pygame.Surface((base.get_width() * scale,
                                                              base.get_height() * scale),
                                                             pygame.SRCALPHA))
            skin_cache[skin] = (base, front)
        return skin_cache[skin]

    art.stand_layers = stand_layers

    # ---- hero: themed hair / outfit / accessory ----------------------------
    original_hero = art.hero

    def parse(tag):
        _, theme, part = tag.split(':')
        return theme, part

    hair_browns = {(117, 63, 43), (106, 61, 43), (130, 72, 47), (109, 73, 54)}
    face_masks = {}

    def face_of(head, scale):
        """Eyes, cheeks and mouth of the base head, so a themed hair piece never covers the face."""
        if 'mask' not in face_masks:
            base = art.image('player/base/short')
            mask = pygame.Surface((24, 34), pygame.SRCALPHA)
            for y in range(10, 18):
                for x in range(8, 17):
                    c = base.get_at((x, y))
                    if c.a and tuple(c)[:3] not in hair_browns:
                        mask.set_at((x, y), (255, 255, 255, 255))
            face_masks['mask'] = mask
        mask = face_masks['mask']
        if scale > 1:
            mask = pygame.transform.scale(mask, (24 * scale, 34 * scale))
        face = head.copy()
        face.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return face

    def bald_of(head, scale):
        """Base head with its own brown hair removed, so themed hair never shows it underneath."""
        if 'hair' not in face_masks:
            base = art.image('player/base/short')
            mask = pygame.Surface((24, 34), pygame.SRCALPHA)
            mask.fill((255, 255, 255, 255))
            fill = []
            for y in range(0, 34):
                for x in range(0, 24):
                    c = base.get_at((x, y))
                    if c.a and tuple(c)[:3] in hair_browns:
                        mask.set_at((x, y), (0, 0, 0, 0))
                        if 5 <= x <= 18 and 6 <= y <= 18:
                            fill.append((x, y))
            face_masks['hair'] = mask
            face_masks['fill'] = fill
        mask = face_masks['hair']
        if scale > 1:
            mask = pygame.transform.scale(mask, (24 * scale, 34 * scale))
        bald = head.copy()
        bald.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        # Patch the forehead with skin so no see-through holes remain under the themed hair.
        skin = head.get_at((10 * scale, 16 * scale))
        for x, y in face_masks['fill']:
            bald.fill(skin, (x * scale, y * scale, scale, scale))
        return bald

    def hero(hair, top, accessory, frame, facing):
        hair_tag =hair[0] if str(hair[0]).startswith('T:') else None
        top_tag = top[0] if str(top[0]).startswith('T:') else None
        acc_tag = accessory if str(accessory).startswith('T:') else None
        if not (hair_tag or top_tag or acc_tag):
            return original_hero(hair, top, accessory, frame, facing)
        style = 'short' if hair_tag else hair[0]

        def atlas(key, scale):
            return art.image(key) if scale == 1 else art.native_image(key, scale)

        def compose(scale):
            high = atlas('player/base/' + style, scale).copy()
            head = high.copy()
            if hair_tag:
                head = bald_of(head, scale)
                high = head.copy()
            high.fill((0, 0, 0, 0), (5 * scale, 19 * scale, 14 * scale, 14 * scale))
            # Keep a skin bridge under the collar, including when mixing a themed
            # hairstyle with a legacy outfit. The collar and chin draw over it.
            skin = head.get_at((10 * scale, 16 * scale))
            high.fill(skin, (10 * scale, 18 * scale, 4 * scale, 5 * scale))
            if top_tag:
                piece = sprite(*parse(top_tag))
                high.blit(dr.detail(piece, scale) if scale > 1 else piece, (0, 0))
            else:
                high.blit(atlas('player/outfit/' + top[0], scale),
                          (3 * scale, 19 * scale))
            high.blit(head, (0, 0), (0, 0, 24 * scale, 19 * scale))
            if style in ('long', 'twin', 'bob', 'curly', 'pony'):
                for x, w in ((0, 6), (18, 6)):
                    high.blit(head, (x * scale, 19 * scale),
                              (x * scale, 19 * scale, w * scale, 8 * scale))
            if hair_tag:
                piece = sprite(*parse(hair_tag))
                high.blit(dr.detail(piece, scale) if scale > 1 else piece, (0, 0))
                high.blit(face_of(head, scale), (0, 0))
            if acc_tag:
                piece = sprite(*parse(acc_tag))
                high.blit(dr.detail(piece, scale) if scale > 1 else piece, (0, 0))
                if parse(acc_tag) not in ON_FACE:
                    high.blit(face_of(head, scale), (0, 0))
            elif accessory not in (None, 'none'):
                x, y = art.ACCESSORY_POS[accessory]
                high.blit(atlas('player/accessory/' + accessory, scale),
                          (x * scale, y * scale))
            return high

        out = dr.register(compose(1), compose)
        return art.walk(out, frame, facing)

    art.hero = hero

    # ---- shop thumbnails for themed hero parts -----------------------------
    original_icon = cafe.icon_for

    def icon_for(kind, key, state_='norm'):
        info = themed.get(key)
        if kind != 'hero' or info is None or info['part'] not in (
                'hair', 'outfit_1', 'outfit_2', 'accessory_1', 'accessory_2'):
            return original_icon(kind, key, state_)
        ck = (kind, key, state_)
        if ck not in cafe.icon_cache:
            piece = sprite(info['theme'], info['part'])
            box = piece.get_bounding_rect().inflate(2, 2).clip(piece.get_rect())
            cat = cafe.HERO_BY_ID[key][0]
            hair = cafe.HERO['hair'][0]['v']
            top = cafe.HERO['top'][0]['v']
            if cat == 'hair':
                hair = cafe.HERO_BY_ID[key][1]['v']
                box = pygame.Rect(2, 0, 20, 22)
            elif cat == 'top':
                top = cafe.HERO_BY_ID[key][1]['v']
                box = pygame.Rect(0, 17, 24, 17)
            elif cat == 'acc':
                # Waist rings, scarf tails and parasol handles extend below the face.
                box = piece.get_bounding_rect().union(pygame.Rect(0, 0, 24, 24))
                box = box.inflate(2, 2).clip(piece.get_rect())
            image = cafe.hero_surf(hair, top, cafe.HERO_BY_ID[key][1]['v'] if cat == 'acc' else 'none', 0, 1)
            cafe.icon_cache[ck] = cafe.scale_fit(art.dr.crop(image, box))
        return cafe.icon_cache[ck]

    cafe.icon_for = icon_for
