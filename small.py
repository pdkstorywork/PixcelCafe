"""Small game patches: window art, recipe book, UI performance, staff art, rare guest dialog."""
# ======================================================================
# window_art
# ======================================================================
# Detailed seasonal window art, keeping the recovered weather animation.
from functools import lru_cache
from pathlib import Path
import math
import pygame
import detail_render as dr

ROOT = Path(__file__).resolve().parent
SEASONS = ('season_spring', 'season_summer', 'season_autumn', 'season_winter')


@lru_cache(maxsize=1)
def sheet():
    return pygame.image.load(str(ROOT / 'assets' / 'window-seasons.png')).convert()


@lru_cache(maxsize=128)
def landscape(season, weather, darkness, size):
    source = sheet()
    row = SEASONS.index(season) if season in SEASONS else 0
    strip = source.subsurface((0, row * source.get_height() // 4,
                               source.get_width(), source.get_height() // 4))

    def build(scale):
        w, h = size[0] * scale, size[1] * scale
        image = pygame.transform.scale(strip, (w, h)).copy()
        dark = max(0, min(1, darkness / 16))
        overcast = {'weather_cloud': .10, 'weather_rain': .21,
                    'weather_storm': .36, 'weather_snow': .08}.get(weather, 0)
        tint = (int(255 * (1 - .62 * dark - overcast)),
                int(255 * (1 - .51 * dark - overcast)),
                int(255 * (1 - .30 * dark - overcast)))
        image.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
        if dark > .45 and weather in ('weather_clear', 'weather_cloud'):
            # Small moon and stars share the landscape's pixel grid.
            pygame.draw.circle(image, (255, 235, 179), (w * 3 // 5, 4 * scale), 2 * scale)
            for x, y in ((27, 3), (46, 6), (79, 2), (95, 5)):
                image.fill((228, 223, 191), (x * scale, y * scale, scale, scale))
        return image

    return dr.register(build(1), build)


def paint_window(surface, rect, t, dark, weather, season):
    """Draw weather at furniture resolution without clouds covering nearby trees."""
    x, y, w, h = rect
    background = landscape(season, weather, round(max(0, min(1, dark)) * 16), (w, h))

    def build(scale):
        image = dr.detail(background, scale).copy()
        width, height = image.get_size()
        # Fine precipitation shares the sprite pixel grid, not large UI blocks.
        if weather in ('weather_rain', 'weather_storm'):
            storm = weather == 'weather_storm'
            for i in range(36 if storm else 22):
                px = int((i * 29 - t * (13 if storm else 3)) % w * scale)
                py = int(((i * 17 + t * (37 if storm else 24)) % (h + 6) - 3) * scale)
                pygame.draw.line(image, (156, 192, 200), (px, py),
                                 (px - scale, py + 2 * scale), max(1, scale // 2))
        elif weather == 'weather_snow':
            for i in range(24):
                px = int((i * 23 + math.sin(t + i) * 3) % w * scale)
                py = int((i * 13 + t * 5) % h * scale)
                pygame.draw.rect(image, (231, 240, 230), (px, py, max(1, scale // 2), max(1, scale // 2)))
        elif weather == 'weather_fog':
            mist = pygame.Surface((width, height), pygame.SRCALPHA)
            mist.fill((191, 207, 198, 65))
            image.blit(mist, (0, 0))
        # Restrained lake glints sit on water below the opposite shore.
        if weather in ('weather_clear', 'weather_cloud') and dark < .65:
            for i in range(4):
                px = int((w * (.36 + i * .09)) * scale)
                py = int((h * (.56 + (i % 3) * .11)) * scale)
                if math.sin(t * 1.4 + i * 2) > .5:
                    pygame.draw.line(image, (199, 224, 204), (px, py), (px + 2 * scale, py))
        return image

    surface.blit(dr.register(build(1), build), (x, y))


def install_window_art(cafe):
    if getattr(cafe, '_cute_window_installed', False):
        return
    cafe._cute_window_installed = True
    old_frame = cafe.scenery.frame
    original_render = cafe.render_scene
    cafe.scenery.backdrop = landscape
    cafe.scenery.paint = paint_window

    @lru_cache(maxsize=4)
    def frame(season):
        original = old_frame(season)

        def build(scale):
            high = pygame.transform.scale(original, (118 * scale, 35 * scale))
            # Carved wood moulding in the same warm palette as the furniture.
            def box(color, rect, width=0):
                pygame.draw.rect(high, color, tuple(v * scale for v in rect), width * scale)
            box((71, 44, 33), (0, 0, 118, 33))
            box((119, 72, 43), (1, 1, 116, 31))
            box((207, 151, 85), (1, 1, 116, 1))
            box((238, 192, 120), (2, 2, 114, 1))
            box((164, 105, 58), (2, 3, 114, 28), 1)
            box((86, 51, 37), (3, 3, 112, 27), 1)
            high.fill((0, 0, 0, 0), (4 * scale, 4 * scale, 110 * scale, 25 * scale))
            box((232, 185, 117), (1, 30, 116, 1))
            box((173, 112, 63), (0, 31, 118, 1))
            box((80, 48, 35), (0, 32, 118, 1))
            # Fine grain uses subpixels at 2x and 3x, never blurry scaling.
            for x in range(8, 109, 13):
                pygame.draw.line(high, (182, 122, 69),
                                 (x * scale, 1 * scale + 1), ((x + 6) * scale, 1 * scale + 1))
                pygame.draw.line(high, (123, 74, 44),
                                 (x * scale, 31 * scale + 1), ((x + 4) * scale, 31 * scale + 1))
            # Keep the original seasonal sill ornaments and trailing greenery.
            high.blit(pygame.transform.scale(original, high.get_size()), (0, 0),
                      (0, 33 * scale, 118 * scale, 2 * scale))
            return high

        return dr.register(build(1), build)

    cafe.scenery.frame = frame

    def render(game, scene, *args, **kwargs):
        # Weather paint needs the same detail surfaces as furniture sprites.
        if not cafe._layers:
            cafe._layers.update(sky=dr.DetailSurface((cafe.SW, cafe.SH)),
                                lighting=pygame.Surface((cafe.SW, cafe.SH)),
                                glows=pygame.Surface((cafe.SW, cafe.SH)))
        elif not isinstance(cafe._layers['sky'], dr.DetailSurface):
            cafe._layers['sky'] = dr.DetailSurface((cafe.SW, cafe.SH))
        return original_render(game, scene, *args, **kwargs)

    cafe.render_scene = render
    cafe._shell_cache.clear()


# ======================================================================
# recipe_book
# ======================================================================
# Dedicated recipe collection tab and explicit sequential unlock requirements.
def prerequisite(cafe, rid):
    index = next(i for i, recipe in enumerate(cafe.RECIPES) if recipe['id'] == rid)
    return cafe.RECIPES[index - 1] if index else None


def install_recipe_book(cafe):
    if getattr(cafe, '_recipe_book_installed', False):
        return
    cafe._recipe_book_installed = True
    UI, Game = cafe.UI, cafe.Game
    book_tab = len(cafe.TABS)
    cafe.TABS.append('도감')
    original_rows, original_draw = UI.rows, UI.draw
    original_buy, original_row = Game.buy_recipe, UI.draw_row

    def buy_recipe(self, rid):
        return original_buy(self, rid)

    def rows(self):
        if getattr(self, '_drawing_book', False) or self.tab == book_tab:
            result = []
            for recipe in cafe.RECIPES:
                rid = recipe['id']
                level = self.g.rlv[rid]
                if level:
                    sub = recipe['desc']
                    price = f"해금 완료 · Lv.{level}"
                else:
                    sub = '??? · 시간이 지나면 자동으로 열려요'
                    price = f"{recipe['unlock_day']}일차 해금 (현재 {self.g.day()}일차)"
                result.append(dict(kind='none', id=rid, name=recipe['name'],
                    sub=sub, price=price, ok=False,
                    state='owned' if level else 'locked',
                    icon=cafe.icon_for('recipe', rid, 'owned' if level else 'hidden')))
            return result
        result = original_rows(self)
        if self.tab == 1:
            # Keep the next locked recipe visible with its actual prerequisite.
            for row in result:
                if row.get('state') == 'hidden':
                    recipe = cafe.RECIPE[row['id']]
                    row['name'] = recipe['name']
        return result

    def draw_row(self, surface, rect, row, mouse, area):
        if not getattr(self, '_drawing_book', False):
            return original_row(self, surface, rect, row, mouse, area)
        else:
            cafe.pygame.draw.rect(surface,
                (255, 246, 226) if row['state'] == 'owned' else (226, 208, 176), rect)
            cafe.pygame.draw.rect(surface, (54, 34, 24), rect, 2)
            icon_rect = cafe.pygame.Rect(rect.x + 6, rect.y + 6, 52, 52)
            cafe.pygame.draw.rect(surface, (232, 214, 180), icon_rect)
            cafe.pygame.draw.rect(surface, (170, 130, 90), icon_rect, 2)
            surface.blit(row['icon'], row['icon'].get_rect(center=icon_rect.center))
            # Fit the entire condition even for the longest recipe names.
            font_size = 12
            while font_size > 9 and cafe.font(font_size).size(row['sub'])[0] > rect.w - 76:
                font_size -= 1
            cafe.pygame.draw.rect(surface,
                (255, 246, 226) if row['state'] == 'owned' else (226, 208, 176),
                (rect.x + 64, rect.y + 3, rect.w - 68, rect.h - 6))
            cafe.text(surface, row['name'], 14, (84, 52, 34), rect.x + 66, rect.y + 7, True)
            cafe.text(surface, row['sub'], font_size, (110, 76, 52), rect.x + 66, rect.y + 28)
            cafe.text(surface, row['price'], 12,
                      (91, 125, 76) if row['state'] == 'owned' else (130, 100, 76),
                      rect.x + 66, rect.y + 49, True)

    def footer(self, surface, mouse):
        if cafe.PORTRAIT:
            rect = cafe.pygame.Rect(0, cafe.H - cafe.BOT_H, cafe.W, cafe.BOT_H)
        else:
            y = cafe.TOP + cafe.SH * cafe.Z
            rect = cafe.pygame.Rect(0, y, cafe.PANEL_X, cafe.H - y)
        cafe.pygame.draw.rect(surface, (96, 62, 42), rect)
        cafe.pygame.draw.rect(surface, (54, 34, 24), rect, 2)
        self.hit = [hit for hit in self.hit if not rect.collidepoint(hit[0].center)]
        got = sum(level > 0 for level in self.g.rlv.values())
        message = self.g.toasts[-1][0] if self.g.toasts else f'빵 도감 {got}/{len(cafe.RECIPES)} · 도감 탭에서 확인'
        cafe.text(surface, message, 13, (255, 226, 130), rect.x + 12, rect.y + 7, True)
        for i, (label, action) in enumerate((('설정', 'settings'),
                ('가로' if cafe.PORTRAIT else '세로', 'orient'), ('미니(M)', 'mini'))):
            button = cafe.pygame.Rect(rect.right - 306 + i * 100, rect.bottom - 30, 94, 24)
            self.btn(surface, label, button, action, mouse, False)

    def draw(self, surface, mouse):
        is_book = self.tab == book_tab
        self.tip = None
        self._drawing_book = is_book
        settings = self.settings_open
        self.settings_open = False
        if is_book:
            # Reuse the runtime's recipe-card layout and scrolling, then restore
            # the real tab before input handling and mouse-wheel events.
            self.tab = 1
            self.scroll[1], self.scroll[book_tab] = self.scroll[book_tab], self.scroll[1]
        try:
            original_draw(self, surface, mouse)
        finally:
            self.settings_open = settings
            self._drawing_book = False
            if is_book:
                self.scroll[1], self.scroll[book_tab] = self.scroll[book_tab], self.scroll[1]
                self.tab = book_tab
        if is_book:
            px, py, pw = cafe.PANEL_X, cafe.PANEL_Y, cafe.PANEL_W
            # Refresh the selected tab styling after the reused renderer.
            tw = (pw - 16) // len(cafe.TABS)
            for i, name in enumerate(cafe.TABS):
                rect = cafe.pygame.Rect(px + 8 + i * tw, py + 8, tw - 2, 40)
                active = i == book_tab
                cafe.pygame.draw.rect(surface, (232, 150, 70) if active else (214, 184, 140), rect)
                cafe.pygame.draw.rect(surface, (54, 34, 24), rect, 2)
                cafe.text(surface, name, 15 if cafe.PORTRAIT else 12,
                    (255, 255, 255) if active else (84, 52, 34),
                    rect.centerx, rect.centery, True, 'mc')
            cafe.pygame.draw.rect(surface, (250, 232, 196), (px + 4, py + 52, pw - 8, 36))
            got = sum(level > 0 for level in self.g.rlv.values())
            cafe.text(surface, f"빵 도감 {got}/{len(cafe.RECIPES)} · 잠긴 빵은 일차에 따라 자동 해금", 12,
                      (110, 76, 52), px + 12, py + 62, True)
        footer(self, surface, mouse)
        if settings:
            self.draw_settings(surface, mouse)

    # The old icon strip is replaced by the dedicated collection cards.
    UI.draw_dex = lambda self, *args, **kwargs: None
    UI.rows, UI.draw, UI.draw_row = rows, draw, draw_row
    Game.buy_recipe = buy_recipe
    cafe.BOT_H = 62
    cafe.set_layout(cafe.PORTRAIT, cafe.H)


# ======================================================================
# ui_performance
# ======================================================================
# Load static interior thumbnails without rendering complete cafe shells.
import json
from pathlib import Path


def install_ui_performance(cafe):
    if hasattr(cafe, '_original_shop_icon'):
        return
    original = cafe.icon_for
    cafe._original_shop_icon = original
    root = Path(__file__).resolve().parent / 'assets'
    rectangles = json.loads((root / 'decor-icons.json').read_text(encoding='utf-8'))
    atlas = None

    def icon_for(kind, key, state='norm'):
        nonlocal atlas
        if kind != 'int' or key not in rectangles:
            return original(kind, key, state)
        cache_key = (kind, key, state)
        if cache_key not in cafe.icon_cache:
            if atlas is None:
                atlas = cafe.pygame.image.load(str(root / 'decor-icons.png')).convert_alpha()
            cafe.icon_cache[cache_key] = atlas.subsurface(rectangles[key])
        return cafe.icon_cache[cache_key]

    cafe.icon_for = icon_for


# ======================================================================
# staff_art
# ======================================================================
# Use complete animal staff art without the legacy human chef hat overlay.
from functools import lru_cache


def install_staff_art(cafe):
    art = cafe.art
    original = art.animated

    @lru_cache(maxsize=512)
    def animated(key, frame=0, facing=1):
        if key.startswith('staff/'):
            return art.walk(art.image(key), frame, facing)
        return original(key, frame, facing)

    art.animated = animated


# ======================================================================
# rare_dialog
# ======================================================================
# Rare-guest speech bubbles + original character names.
#
# Only tiers listed in SPEAK_TIERS talk (family guests never do). Remove 'legend' to
# silence the three legendary guests again.
#
# LINES[key][situation] = list of variants; a variant is a string or a tuple of strings
# (a tuple plays as several bubbles in a row). Situations: enter / happy / bye.
import random

SPEAK_TIERS = ('rare', 'legend')
BUBBLE_TIME = 2.4

NAMES = {
    'chiikawa': '치이카와', 'usagi': '우사기', 'hachiware': '하치와레',
    'kitty': '헬로키티', 'melody': '마이멜로디', 'kuromi': '쿠로미', 'cinna': '시나모롤',
    'purin': '폼폼푸린', 'ganadi': '가나디', 'loopy': '잔망 루피', 'ryan': '라이언',
    'apeach': '어피치', 'pororo': '뽀로로', 'pikachu': '피카츄', 'chunsik': '춘식이',
}

LINES = {
    # ---- legend (off by default) ----------------------------------------------------
    'chiikawa': dict(enter=[('와…', '*두리번두리번*')], happy=[('으응!', '*냠냠냠*', '와아~!')],
                     bye=[('*꾸벅*', '으, 으응!')]),
    'usagi': dict(enter=[('야하!', '우라!')], happy=[('우라라라라~!', '야하~!')], bye=['푸이!']),
    'hachiware': dict(enter=[('안녕하세요! 와, 좋은 냄새다~',)], happy=[('맛있다! 치이카와도 좋아하겠다!',)],
                      bye=['다음엔 같이 올게요!']),
    # ---- rare: sanrio / character cafe regulars -------------------------------------
    'kitty': dict(enter=['안녕… 빵 하나 주세요.'], happy=['맛있다… 고마워.'], bye=['또 올게, 안녕~']),
    'melody': dict(enter=['엄마 쿠키 같은 냄새야~'], happy=['맛있다! 이거 좋아해~'], bye=['또 올게, 안녕~']),
    'kuromi': dict(enter=['흥, 빵 하나 줘봐.'], happy=['나쁘지 않네. 그냥 그렇다고.'],
                   bye=['다시 올 건 아니거든!']),
    'cinna': dict(enter=['귀로 날아 왔어요~'], happy=['와아~ 너무 맛있어요!'], bye=['또 올게요~']),
    'purin': dict(enter=['푸딩 있어요? 빵도 좋아요.'], happy=['음~ 맛있네요.'], bye=['낮잠 시간이라 가볼게요.']),
    'ganadi': dict(enter=['멍! 안녕하세요~'], happy=['맛있어요! 최고예요!'], bye=['또 와도 되죠? 멍!']),
    'loopy': dict(enter=['루피 왔어요~'], happy=['루피는 이 빵이 제일 좋아!'], bye=['루피는 이제 놀러 갈래~']),
    'ryan': dict(enter=['…빵 하나.'], happy=['…괜찮네.'], bye=['…간다.']),
    'apeach': dict(enter=['어피치 왔어요~'], happy=['복숭아 빵은 없어요?'], bye=['엉덩이 흔들며 갈게요~']),
    'pororo': dict(enter=['뽀로로가 놀러 왔어!'], happy=['와, 맛있다! 같이 놀자~'], bye=['다음에 또 놀자!']),
    'pikachu': dict(enter=['피카피카!'], happy=['피카~! 피이카츄~!'], bye=['피카츄~!']),
    'chunsik': dict(enter=['춘식이 왔어요~ 야옹.'], happy=['고구마빵은 없어요? 야옹.'], bye=['또 올게요, 야옹~']),
    # ---- rare: new additions --------------------------------------------------------
    'totoro': dict(enter=['우오오오~!'], happy=['으하하하~!'], bye=['*도토리를 놓고 감*']),
    'stitch': dict(enter=['스티치! 스티치 왔다!'], happy=['나쁜 아이 아니야, 맛있어!'], bye=['또 올 거야, 오하나!']),
    'pooh': dict(enter=['꿀 들어간 빵이 있으려나…'], happy=['아, 이건 정말 맛있네요.'],
                 bye=['생각해 보니 배가 불러요.']),
    'rilakkuma': dict(enter=['나른~ 빵 주세요~'], happy=['맛있다~ 더 누워 있을래~'], bye=['집에서 쉴래~']),
    'snoopy': dict(enter=['(오늘도 좋은 날이군)'], happy=['(이 빵… 나쁘지 않아)'], bye=['(날아가 볼까)']),
    'kaonashi': dict(enter=['아…'], happy=[('아… 아…', '*금을 내민다*')], bye=['아… (사라짐)']),
    'kumamon': dict(enter=['쿠마몬이다몬~'], happy=['맛있다몬~!'], bye=['또 올 거다몬~']),
    'gudetama': dict(enter=['…빵. 귀찮지만.'], happy=['…이 정도면 됐다.'], bye=['…움직이기 귀찮다.']),
}


def _pick(key, situation):
    variants = LINES.get(key, {}).get(situation)
    if not variants:
        return []
    v = random.choice(variants)
    return [v] if isinstance(v, str) else list(v)


def _talks(customer):
    return getattr(customer, 'tier', '') in SPEAK_TIERS and customer.name in LINES


def _queue(customer, situation):
    customer.say_q = getattr(customer, 'say_q', []) + _pick(customer.name, situation)


def install_rare_dialog(cafe):
    specials, Game, Customer = cafe.specials, cafe.Game, cafe.Customer
    specials.SPECIAL.update({k: v for k, v in NAMES.items() if k in specials.SPECIAL})

    spawn, paid, update = Game.spawn_customer, Game.customer_paid, Customer.update

    def spawn_customer(self, *args, **kw):
        before = len(self.customers)
        result = spawn(self, *args, **kw)
        for c in self.customers[before:]:
            if _talks(c):
                _queue(c, 'enter')
        return result

    def customer_paid(self, customer, *args, **kw):
        first = not customer.paid
        result = paid(self, customer, *args, **kw)
        if first and _talks(customer):
            _queue(customer, 'happy')
            _queue(customer, 'bye')
        return result

    def update_customer(self, dt, game):
        q = getattr(self, 'say_q', None)
        if q and not self.say:
            self.say = [q.pop(0), BUBBLE_TIME]
        return update(self, dt, game)

    Game.spawn_customer, Game.customer_paid, Customer.update = spawn_customer, customer_paid, update_customer

