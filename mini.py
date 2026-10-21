"""Mini mode / taskbar bar / window behaviour / monitor 2 placement."""
# ======================================================================
# mini_view
# ======================================================================
# Show the crisp 2x mini render in a smaller real window.
#
# Mini mode only has pixel-perfect art at 2x (640x456). That is too big to leave
# running, so the game still draws a 640x456 logical frame offscreen and each
# flip smooth-downscales it into a window of VIEW times that size. Mouse
# positions are scaled back to the logical frame so the game's own hit tests keep
# working.
VIEW = 0.5   # 0.5 -> 320x228 window (exact 2:1 box downscale, no shimmer); 1.0 -> 640x456
LOGICAL = (640, 456)


def install_mini_view(cafe):
    if getattr(cafe, '_mini_view_installed', False) or VIEW >= 1:
        return
    cafe._mini_view_installed = True
    pg = cafe.pygame
    real = pg.display.set_mode
    real_get_surface = pg.display.get_surface
    real_flip, real_update = pg.display.flip, pg.display.update
    real_get_pos = pg.mouse.get_pos
    real_event_get, real_event_poll = pg.event.get, pg.event.poll
    state = cafe._mini_view_state = {'logical': None, 'window': None, 'size': None}

    def bar():
        mini_bar = getattr(cafe, '_bar_api', None)
        return mini_bar if mini_bar and mini_bar.active() else None

    def to_logical(pos):
        if state['logical'] is None:
            return pos
        if bar():
            # the strip is drawn on the real window; keep the game's hidden mini frame
            # from hit-testing the cursor (hovering x5/x10 popped up a guest/dex card)
            return (-1000, -1000)
        return (int(pos[0] / VIEW), int(pos[1] / VIEW))

    def set_mode(size=(0, 0), flags=0, *args, **kwargs):
        if flags & pg.NOFRAME and tuple(size) == LOGICAL:
            w, h = int(LOGICAL[0] * VIEW), int(LOGICAL[1] * VIEW)
            if bar():
                w, h = bar().size
            state['window'] = real((w, h), flags, *args, **kwargs)
            state['size'] = (w, h)
            state['logical'] = pg.Surface(LOGICAL).convert()
            return state['logical']
        state['logical'] = state['window'] = None
        return real(size, flags, *args, **kwargs)

    def get_surface():
        return state['logical'] if state['logical'] is not None else real_get_surface()

    def present():
        if state['logical'] is not None and bar():
            bar().draw(state['window'], real_get_pos())
        elif state['logical'] is not None:
            window = state['window']
            pg.transform.smoothscale(state['logical'], state['size'], window)
            # Blended edge pixels would show as a pink fringe; snap them back to the
            # transparent colour key.
            pg.mask.from_threshold(window, cafe.KEY, (70, 70, 70, 255)).to_surface(
                window, setcolor=cafe.KEY, unsetcolor=None)

    def flip():
        present()
        real_flip()

    def update(*args, **kwargs):
        if state['logical'] is None:
            return real_update(*args, **kwargs)
        present()
        real_flip()

    def convert(event):
        if state['logical'] is not None and hasattr(event, 'pos'):
            data = dict(event.dict)
            data['pos'] = to_logical(event.pos)
            return pg.event.Event(event.type, data)
        return event

    pg.display.set_mode = set_mode
    pg.display.get_surface = get_surface
    pg.display.flip = flip
    pg.display.update = update
    pg.mouse.get_pos = lambda: to_logical(real_get_pos())
    mouse_keys = (pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP, pg.MOUSEMOTION, pg.MOUSEWHEEL,
                  pg.KEYDOWN, pg.KEYUP)

    def filter_events(events):
        result = []
        mini_bar = getattr(cafe, '_bar_api', None)
        for event in events:
            if mini_bar and state['logical'] is not None and event.type in mouse_keys:
                if bar():
                    mini_bar.handle(event)
                    continue
                if (event.type == pg.MOUSEBUTTONDOWN and event.button == 1
                        and mini_bar.mini_click(to_logical(event.pos))):
                    continue
                game = getattr(mini_bar, 'game', lambda: None)()
                if (event.type == pg.MOUSEBUTTONDOWN and event.button == 1 and game is not None
                        and game.mini and not game.bar
                        and to_logical(event.pos)[1] // 2 < ROW_Y - 2):
                    continue         # only the bottom bar grabs the window (game would start a native drag)
                if event.type in (pg.MOUSEBUTTONDOWN, pg.MOUSEMOTION, pg.MOUSEBUTTONUP) \
                        and mini_bar.mini_drag(event, to_logical(event.pos)):
                    continue
            result.append(convert(event))
        return result

    pg.event.get = lambda *a, **k: filter_events(real_event_get(*a, **k))
    pg.event.poll = lambda: (filter_events([real_event_poll()]) or [pg.event.Event(pg.NOEVENT)])[0]


# ======================================================================
# mini_bar
# ======================================================================
# Taskbar "bar" mode: a tiny strip (gold, x5, x10, restore) docked above the taskbar.
#
# Reached from the mini window's minimize button. The strip is drawn 1:1 on the
# real window by mini_view.present(). Collection unlocks and special guests show
# up as a speech bubble above the strip.
import ctypes
import math
import time

BAR_W, BAR_H = 320, 32
BUB_H = 42                      # transparent strip above the bar for the speech bubble
WIN_W, WIN_H = BAR_W, BAR_H + BUB_H
NOTE_SECONDS = 6.0
ALPHA_IDLE, ALPHA_HOVER = 150, 255   # bar opacity (0-255); fully opaque while hovered
NOTE_WORDS = ('도감', '손님', '등장', '우정', '변종', '선물', '업적', '새 레시피')
NOTE_NO_FACE = ('세일', '새 레시피')     # messages that are not about the guest who just paid
# lower = more important; only sale/unlock news (rank 4) is dropped when two notes are already waiting
NOTE_RANK = (('전설', 0), ('희귀', 1), ('업적', 2), ('우정', 2), ('변종', 2))
SALE_SECONDS = 2.5              # how long the "who bought what" text replaces the per-minute income
SCROLL_PX = 45                  # px/s a long payment line scrolls through the income slot
BIG_SALE_MULT, BIG_SALE_MIN, BIG_SALE_GAP = 4.0, 12, 90.0   # x average sale, sales needed, seconds between
# mini bar buttons (logical 320x228 coordinates): settings sits right of the gold amount,
# minimize takes the old settings slot.
MIN_RECT = (222, 210, 22, 16)
BTN_W, BTN_GAP, ROW_Y = 22, 2, 210   # every mini-bar button: same size, same gap
SPEED_W = (22, 22)              # x5 / x10 button widths in the mini window
GOLD_X, GOLD_X_NEW = 20, 8        # gold amount x: original (right of the coin) and without the coin
BUTTONS_X = 150                 # left edge of settings/x5/x10 (right-aligned against the minimize button)
SETTINGS_W = 22                 # settings button sits where x5 starts; x5/x10 shift right of it
BAR_COLOR = (96, 62, 42)


def install_mini_bar(cafe):
    if getattr(cafe, '_bar_api', None):
        return
    pg = cafe.pygame
    Game = cafe.Game
    Game.bar = False
    notes = []                  # [text, expires_at]
    ref = {'game': None, 'drag': None, 'btns': {}}

    def work_area():
        rect = cafe._RECT()
        ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)
        return rect

    def default_pos():
        try:
            r = work_area()
            return (r.right - WIN_W - 12, r.bottom - WIN_H)
        except Exception:
            return (100, 100)

    def mini_default_pos():
        # bottom-right corner of the work area, sized for the (scaled) mini window
        try:
            w, h = int(LOGICAL[0] * VIEW), int(LOGICAL[1] * VIEW)
            r = work_area()
            return (r.right - w - 8, r.bottom - h)
        except Exception:
            return None

    def active():
        game = ref['game']
        return bool(game is not None and game.mini and game.bar)

    def enter(game, keep_position=False):
        position = cafe.win_pos() if keep_position else None
        game._mini_pos_stash = position or game.mini_pos
        game.mini_pos = (position or game.mini_pos) if keep_position else default_pos()
        if keep_position and game.mini_pos is not None:
            # collapse toward the mini window's bottom edge: the bar's bottom lines up with it
            x, y = game.mini_pos
            game.mini_pos = (x, y + int(LOGICAL[1] * VIEW) - WIN_H)
        if game.mini_pos is None:
            game.mini_pos = default_pos()
        game.bar = True
        game.mode_dirty = True

    def leave(game):
        game.mini_pos = getattr(game, '_mini_pos_stash', None) or mini_default_pos()
        if ref['drag']:
            ctypes.windll.user32.ReleaseCapture()
            ref['drag'] = None
        game.bar = False
        game.mode_dirty = True
        del notes[:]

    # ---- mini window: minimize button --------------------------------------------
    original_draw_mini = cafe.draw_mini
    base_code = original_draw_mini.__code__
    DEFAULT_SKIN = dict(fill=(96, 62, 42), edge=(54, 34, 24), text=(255, 240, 200), btn=(214, 184, 140))
    INCOME_CONSTS = ((255, 226, 130), (255, 214, 120))

    speed_fn = cafe.draw_guest_speed_buttons
    speed_base = speed_fn.__code__
    speed_codes = {}

    def draw_speed(surface, game, mouse, x, y, mini=False):
        # the x5/x10 buttons are shared with the normal UI: recolour them for the mini bar only
        if not mini:
            return []
        # mini layout: settings button first (next to the gold), then narrower x5/x10
        skin = palette(game)
        # income / toast text takes the slot right of the gold; the buttons sit against the minimize button
        left = ref.get('gold_right', x - 6) + 4
        ref['income'] = (left, y + 8)
        x = MIN_RECT[0] - (BTN_W + BTN_GAP)      # settings sits directly left of the toolbar-mode button, same gap
        ref['settings_x'] = x
        x += SETTINGS_W + 2
        # speed buttons removed: fixed guest rate. The original draw_mini still reads
        # speed_buttons[-1][0].right, so hand it a zero-width (unclickable, invisible) anchor.
        buttons = [(pg.Rect(x - 2, y, 0, 16), 0)]
        ref['cx0'] = x + 2
        ref['region'] = (ref['income'][0], x - SETTINGS_W - 6)
        return buttons

    cafe.draw_guest_speed_buttons = draw_speed

    def palette(game):
        skin = getattr(game, 'skin_palette', None)
        return skin() if skin else dict(DEFAULT_SKIN, id='brown')

    def apply_skin(skin):
        """Recolour the mini bar by swapping its colour constants in draw_mini."""
        if ref.get('skin_id') == skin['id']:
            return
        ref['skin_id'] = skin['id']
        swap = {DEFAULT_SKIN[k]: skin[k] for k in DEFAULT_SKIN}
        swap.update({c: skin['inc'] for c in INCOME_CONSTS})
        original_draw_mini.__code__ = base_code.replace(co_consts=tuple(
            swap.get(value, value) if isinstance(value, tuple) else value for value in base_code.co_consts))
        speed_codes.setdefault(skin['id'], speed_base.replace(co_consts=tuple(
            swap.get(value, value) if isinstance(value, tuple) else value for value in speed_base.co_consts)))

    def draw_gear(surface, center, color, bg):
        """Standard 8-tooth settings cog, drawn 4x and smoothed down."""
        import math
        k, r_out, r_in = 4, 7, 5
        size = (r_out * 2 + 2) * k
        big = pg.Surface((size, size), pg.SRCALPHA)
        mid = size / 2
        points = []
        for i in range(8):
            a = math.radians(i * 45)
            for da, r in ((-17, r_in), (-10, r_out), (10, r_out), (17, r_in)):
                t = a + math.radians(da)
                points.append((mid + math.cos(t) * r * k, mid + math.sin(t) * r * k))
        pg.draw.polygon(big, color, points)
        pg.draw.circle(big, bg, (mid, mid), 2.2 * k)
        small = pg.transform.smoothscale(big, (r_out * 2 + 2, r_out * 2 + 2))
        surface.blit(small, small.get_rect(center=center))

    def draw_mini(screen, game, scene, mouse):
        ref['game'] = game
        skin = palette(game)
        apply_skin(skin)
        if game.bar:
            off = pg.Rect(-100, -100, 1, 1)
            return [], off, [], off
        # the original tooltip/hover for the old settings slot must not fire on the minimize button
        settings = pg.Rect(ref.get('settings_x', 83), 210, SETTINGS_W, 16)
        hidden = (-1000, -1000) if pg.Rect(MIN_RECT[0] - 1, ROW_Y - 2, screen.get_width(), 20).collidepoint(mouse) or settings.collidepoint(mouse) else mouse
        # the original draws income/toasts right of the buttons; redirect them to the slot next to the gold
        plain_text = cafe.text

        def text_hook(surface, string, size, color, x, y, *args, **kwargs):
            slot = ref.get('income')
            align = args[1] if len(args) > 1 else kwargs.get('align')
            if slot and y == slot[1] and size in (11, 12):
                left, right = ref['region']
                if string.startswith('+') and align == 'mr':
                    surface.set_clip(pg.Rect(left, y - 10, max(0, right - left), 20))
                    return plain_text(surface, string, size, color, left, y, args[0], 'ml', *args[2:], **kwargs)
                if align == 'ml' and size == 11:
                    surface.set_clip(pg.Rect(left, y - 10, max(0, right - left), 20))
                    return plain_text(surface, string, size, color, x - ref['cx0'] + left, y, *args, **kwargs)
            if size == 12 and x == GOLD_X and align == 'ml':
                rect = plain_text(surface, string, size, color, GOLD_X_NEW, y, *args, **kwargs)
                ref['gold_right'] = rect.right
                return rect
            return plain_text(surface, string, size, color, x, y, *args, **kwargs)

        plain_circle = pg.draw.circle
        plain_rect = pg.draw.rect

        def rect_hook(surface, color, rect, *args, **kwargs):
            # The recovered bar starts one row below the scene and rounds its top
            # corners, leaving colour-key holes along the join. Keep the bottom
            # corners rounded, but join the toolbar flush to the scene above it.
            box = pg.Rect(rect)
            if surface is screen and box == pg.Rect(0, cafe.SH + 1, cafe.MW, 19):
                box.y -= 1
                box.h += 1
                kwargs = dict(kwargs, border_top_left_radius=0, border_top_right_radius=0)
            return plain_rect(surface, color, box, *args, **kwargs)

        def circle_hook(surface, color, center, *args, **kwargs):
            if tuple(center) == (GOLD_X - 10, ROW_Y - 2 + 10):     # the yellow coin left of the gold amount
                return pg.Rect(center, (0, 0))
            return plain_circle(surface, color, center, *args, **kwargs)

        cafe.text = text_hook
        pg.draw.circle = circle_hook
        pg.draw.rect = rect_hook
        try:
            result = original_draw_mini(screen, game, scene, hidden)
        finally:
            cafe.text = plain_text
            pg.draw.circle = plain_circle
            pg.draw.rect = plain_rect
        top, bottom = screen.get_height() - 20, screen.get_height() - 2
        pg.draw.line(screen, skin['light'], (6, top + 1), (screen.get_width() - 7, top + 1))   # bevel
        pg.draw.line(screen, skin['edge'], (4, bottom), (screen.get_width() - 5, bottom))
        # repaint the right-hand buttons so all of them share one size and gap
        modes, _old_x, speeds, _old_settings = result
        # Use the palette directly: sampling can pick up overflowing income text.
        pg.draw.rect(screen, skin['fill'], (MIN_RECT[0] - 1, ROW_Y, screen.get_width() - MIN_RECT[0] - 3, 16))
        step = BTN_W + BTN_GAP
        mode_rects = [pg.Rect(MIN_RECT[0] + step * (i + 1), ROW_Y, BTN_W, 16) for i in range(len(modes))]
        xbtn = pg.Rect(MIN_RECT[0] + step * (len(modes) + 1), ROW_Y, BTN_W, 16)
        tips = []
        for box, (_old, portrait) in zip(mode_rects, modes):
            hov = box.collidepoint(mouse)
            pg.draw.rect(screen, cafe.ACCENT if hov else skin['btn'], box)
            pg.draw.rect(screen, cafe.INK, box, 1)
            icon = pg.Rect(0, 0, 7 if portrait else 12, 11 if portrait else 7)
            icon.center = box.center
            pg.draw.rect(screen, cafe.BROWN_D, icon, 1)
            if hov:
                tips.append('세로모드' if portrait else '가로모드')
        hov = xbtn.collidepoint(mouse)
        pg.draw.rect(screen, (214, 84, 76) if hov else skin['btn'], xbtn)
        pg.draw.rect(screen, (54, 34, 24), xbtn, 1)
        xc = (255, 255, 255) if hov else (84, 52, 34)
        pg.draw.line(screen, xc, (xbtn.x + 7, xbtn.y + 4), (xbtn.x + 14, xbtn.y + 11), 2)
        pg.draw.line(screen, xc, (xbtn.x + 14, xbtn.y + 4), (xbtn.x + 7, xbtn.y + 11), 2)
        if hov:
            tips.append('종료')
        if tips:
            cafe.draw_tooltip(screen, tips[0], mouse[0], ROW_Y - 29)
        modes = [(box, portrait) for box, (_old, portrait) in zip(mode_rects, modes)]
        settings = pg.Rect(ref.get('settings_x', 83), 210, SETTINGS_W, 16)
        rect = pg.Rect(MIN_RECT)
        for box, label in ((settings, 'gear'), (rect, None)):
            box_color = cafe.ACCENT if box.collidepoint(mouse) else skin['btn']
            pg.draw.rect(screen, box_color, box)
            pg.draw.rect(screen, cafe.INK, box, 1)
            if label:
                draw_gear(screen, box.center, cafe.BROWN_D, box_color)
            else:
                pg.draw.line(screen, cafe.BROWN_D, (box.x + 6, box.bottom - 5), (box.right - 7, box.bottom - 5), 2)
        for hover, label in ((rect, '툴바모드'), (settings, '설정')):
            if not hover.collidepoint(mouse):
                continue
            width = cafe.font(10, True).size(label)[0] + 10
            tip = pg.Rect(0, hover.y - 20, width, 16)
            tip.right = min(hover.right + (0 if hover is rect else 20), screen.get_width() - 2)
            pg.draw.rect(screen, (255, 250, 232), tip)
            pg.draw.rect(screen, cafe.INK, tip, 1)
            cafe.text(screen, label, 10, cafe.BROWN_D, tip.centerx, tip.centery, True, 'mc', False, False)
        result = (modes, xbtn, speeds, settings)
        return result

    cafe.draw_mini = draw_mini

    original_layered = cafe.set_layered

    def set_layered(on):
        result = original_layered(on)
        ref['alpha'] = None      # window attributes were reset; re-apply on next draw
        return result

    cafe.set_layered = set_layered

    def mini_click(logical_pos):
        """Called by mini_view with the 640x456 logical position. True = consumed."""
        game = ref['game']
        if game is None or not game.mini or game.bar:
            return False
        if pg.Rect(MIN_RECT).collidepoint(logical_pos[0] // 2, logical_pos[1] // 2):
            enter(game, keep_position=True)
            return True
        return False

    # ---- portrait / landscape: toolbar-mode button, landscape always windowed ------
    UI = cafe.UI
    original_click = UI.click
    original_ui_init = UI.__init__

    def ui_init(self, *args, **kwargs):
        original_ui_init(self, *args, **kwargs)
        ref['ui'] = self        # the bar's gear button opens this instance's settings dialog

    UI.__init__ = ui_init

    def click(self, pos, game, *args, **kwargs):
        if not self.settings_open:
            for hit in self.hit:
                if hit[1] == 'btn' and hit[2] == 'bar' and hit[0].collidepoint(pos):
                    game.mini = True
                    enter(game)
                    return True
        return original_click(self, pos, game, *args, **kwargs)

    UI.click = click

    original_apply_mode = cafe.apply_mode
    last_view = {}

    def apply_mode(game, *args, **kwargs):
        view = 'mini' if game.mini else ('portrait' if game.portrait else 'landscape')
        if view == 'landscape' and last_view.get('v') not in (None, 'landscape'):
            game.fullscreen = False          # switching to landscape opens a window, not fullscreen
        last_view['v'] = view
        return original_apply_mode(game, *args, **kwargs)

    cafe.apply_mode = apply_mode

    pg.K_m = -1      # the M-key shortcut to mini mode is gone (main() compares ev.key == pygame.K_m)

    # ---- notifications --------------------------------------------------------------
    original_toast = Game.toast
    original_paid = Game.customer_paid

    def josa(word, with_batchim, without):
        code = ord(word[-1]) - 0xAC00 if word else -1
        return with_batchim if 0 <= code < 11172 and code % 28 else without

    def sale_note(game, customer, amount):
        """Bar only: show 'who bought what' in the income slot; a rare big sale also gets a bubble."""
        cart = [rid for rid in customer.cart if rid in cafe.RECIPE]
        if not cart or amount <= 0:
            return
        who = cafe.guest_label(customer)
        top = max(cart, key=lambda rid: game.price(cafe.RECIPE[rid]))
        bread = cafe.RECIPE[top]['name'] + (f' 외 {len(cart) - 1}개' if len(cart) > 1 else '')
        gold = cafe.fmt(amount)
        # a talking guest's payment line replaces the plain sentence; '*action*' lines only if nothing else
        said = [line.strip() for line in getattr(customer, 'happy_say', None) or ()]
        said = next((line for line in said if not line.startswith('*')), said[0].strip('*') if said else '')
        face = None     # a talking guest shows just "name: line", no portrait
        ref['sale'] = dict(who=who, bread=bread, amount=gold, said=said, face=face, start=time.time())
        now = time.time()
        avg, count = ref.get('sale_avg', 0.0), ref.get('sale_count', 0)
        if (count >= BIG_SALE_MIN and amount >= avg * BIG_SALE_MULT
                and now - ref.get('big_at', 0.0) >= BIG_SALE_GAP):
            ref['big_at'] = now
            add_note(f'{who}{josa(who, "이", "가")} {bread}에 +{gold}를 썼어요', 4, face_of(customer))
        ref['sale_avg'] = avg + (amount - avg) / min(count + 1, 30)
        ref['sale_count'] = count + 1

    def customer_paid(self, customer, *args, **kwargs):
        ref['customer'] = customer      # lets toast() know who a dex/friendship toast is about
        first = not customer.paid
        self.last_sale = None
        try:
            return original_paid(self, customer, *args, **kwargs)
        finally:
            ref['customer'] = None
            sale = getattr(self, 'last_sale', None)
            if first and self.bar and sale and sale[0] is customer:
                try:
                    sale_note(self, customer, sale[1])
                except Exception:
                    pass

    Game.customer_paid = customer_paid

    def face_of(customer):
        """Head-and-shoulders crop of a customer sprite, doubled; None if unavailable."""
        try:
            canvas = pg.Surface((48, 48), pg.SRCALPHA)
            kind = customer.kind
            if kind == 'rare':
                col = cafe._collection
                if customer.name in col.NEW_RARE and col._load_png(pg, customer.name + '.png', (22, 26)) is None:
                    return None     # no art asset for this guest yet: only a code-drawn placeholder
                canvas.blit(cafe.specials.special_surf(customer.name, 0, 1), (13, 8))
            elif kind == 'family':
                img = cafe.specials.family_surf(customer.appearance, 0, 1)
                canvas.blit(img, (24 - img.get_width() // 2, 8))
            else:
                cafe.draw_animal(canvas, 24, 40, customer.species, customer.var,
                                 customer.shirt, customer.acc, 0, 1)
            full = canvas.get_bounding_rect()
            head = canvas.subsurface(pg.Rect(full.x, full.y, full.w, max(1, int(full.h * .5))))
            head = head.subsurface(head.get_bounding_rect()).copy()
            return pg.transform.scale(head, (head.get_width() * 2, head.get_height() * 2))
        except Exception:
            return None

    def add_note(msg, rank, face=None):
        """Queue a bar bubble; sale/unlock news (rank 4) is skipped when the queue is already busy."""
        if any(note[0] == msg for note in notes) or (len(notes) >= 2 and rank >= 4):
            return
        notes.append([msg, time.time() + NOTE_SECONDS, face])

    def variant_face(game):
        """The found variant's bread-with-sticker icon, so the bubble shows which variant it was."""
        found = getattr(game, 'last_variant', None)
        try:
            icon = cafe.variant_icon(found[0], found[1])
            return pg.transform.scale(icon, (28, 28)) if icon.get_width() != 28 else icon
        except Exception:
            return None

    def toast(self, msg):
        original_toast(self, msg)
        if self.bar and any(word in msg for word in NOTE_WORDS):
            if '새 레시피' in msg:      # "N일차 · 새 레시피 해금: ..." would be cut at the first " · "
                msg = '새 레시피 해금: ' + msg.split('새 레시피 해금:')[-1].strip()
            face = None
            if '변종 발견' in msg and getattr(self, 'last_variant', None):
                rid, vid, vname = self.last_variant     # "변종 발견! 딸기 식빵 (...)" would be cut at the "!"
                msg, face = f'변종 발견 {vname} {cafe.RECIPE[rid]["name"]}', variant_face(self)
            elif not any(word in msg for word in NOTE_NO_FACE):
                who = ref.get('customer') or (self.customers[-1] if self.customers else None)
                face = face_of(who) if who else None
            rank = next((rank for word, rank in NOTE_RANK if word in msg), 4 if any(w in msg for w in NOTE_NO_FACE) else 3)
            add_note(msg, rank, face)

    Game.toast = toast

    original_save = Game.save

    def save(self):
        if not self.bar:
            return original_save(self)
        shown, self.mini_pos = self.mini_pos, getattr(self, '_mini_pos_stash', None)
        try:
            return original_save(self)
        finally:
            self.mini_pos = shown

    Game.save = save

    # ---- drawing (real pixels, 1:1) -------------------------------------------------
    def one_line(text, size, width):
        text = text.split('!')[0] + '!' if '!' in text else text.split(' · ')[0]
        font = cafe.font(size, True)
        while len(text) > 1 and font.size(text)[0] > width:
            text = text[:-2].rstrip() + '…'
        return text

    def draw_bubble(win, text, cx=WIN_W // 2, face=None, skin=None):
        skin = skin or palette(ref['game'])
        back, ink = skin['btn'], tuple(int(c * .4) for c in skin['fill'])
        line = one_line(text, 12, WIN_W - 28 - (face.get_width() + 6 if face else 0))
        width = cafe.font(12, True).size(line)[0] + 20
        height = 22
        if face:
            width += face.get_width() + 6
            height = max(height, min(face.get_height(), 32) + 6)
        box = pg.Rect(0, 0, width, height)
        box.midbottom = (cx, BUB_H - 6)
        box.clamp_ip(pg.Rect(0, 0, WIN_W, BUB_H))
        pg.draw.rect(win, back, box, border_radius=7)
        pg.draw.rect(win, skin['edge'], box, 2, border_radius=7)
        tip = [(cx - 6, box.bottom - 1), (cx + 6, box.bottom - 1), (cx, box.bottom + 5)]
        pg.draw.polygon(win, back, tip)
        pg.draw.lines(win, skin['edge'], False, tip, 2)
        x = box.x + 10
        if face:
            win.blit(face, face.get_rect(midleft=(x, box.centery)))
            x += face.get_width() + 6
        cafe.text(win, line, 12, ink, x, box.centery, True, 'ml', False, True)

    bar_cache = {}

    def bar_surface(skin):
        """Rounded bar with a soft top-to-bottom gradient, top highlight and bottom shade."""
        if skin['id'] in bar_cache:
            return bar_cache[skin['id']]
        surf = pg.Surface((BAR_W, BAR_H), pg.SRCALPHA)
        for y in range(BAR_H):
            t = min(1.0, y / (BAR_H * 0.6))
            surf.fill(tuple(int(skin['light'][k] + (skin['fill'][k] - skin['light'][k]) * t) for k in range(3)) + (255,),
                      (0, y, BAR_W, 1))
        mask = pg.Surface((BAR_W, BAR_H), pg.SRCALPHA)
        pg.draw.rect(mask, (255, 255, 255, 255), (0, 0, BAR_W, BAR_H), border_radius=8)
        surf.blit(mask, (0, 0), special_flags=pg.BLEND_RGBA_MULT)
        pg.draw.line(surf, skin['light'], (8, 2), (BAR_W - 9, 2))
        pg.draw.line(surf, tuple(int(c * .8) for c in skin['fill']), (6, BAR_H - 3), (BAR_W - 7, BAR_H - 3))
        pg.draw.rect(surf, skin['edge'], (0, 0, BAR_W, BAR_H), 2, border_radius=8)
        bar_cache[skin['id']] = surf
        return surf

    def button(win, rect, label, hot, active_=False, fill=(214, 184, 140)):
        pg.draw.rect(win, cafe.ACCENT if (hot or active_) else fill, rect)
        pg.draw.rect(win, cafe.INK, rect, 2)
        if label:
            cafe.text(win, label, 12, (255, 255, 255) if active_ else cafe.BROWN_D,
                      rect.centerx, rect.centery, True, 'mc', False, True)

    def set_alpha(alpha):
        if ref.get('alpha') == alpha:
            return
        ref['alpha'] = alpha
        hwnd = pg.display.get_wm_info()['window']
        ctypes.windll.user32.SetLayeredWindowAttributes(
            hwnd, cafe.KEY[0] | cafe.KEY[1] << 8 | cafe.KEY[2] << 16, alpha, 3)

    def draw(win, mouse):
        game = ref['game']
        set_alpha(ALPHA_HOVER if pg.mouse.get_focused() or ref['drag'] else ALPHA_IDLE)
        win.fill(cafe.KEY)
        if game is None:
            return
        now = time.time()
        while notes and notes[0][1] < now:
            notes.pop(0)
        bar = pg.Rect(0, BUB_H, BAR_W, BAR_H)
        skin = palette(game)
        win.blit(bar_surface(skin), bar)
        gold = cafe.text(win, cafe.fmt(game.money), 14, skin['text'], 10, bar.centery, True, 'ml', False, True)
        per_min = f'+{cafe.fmt(game.inc * 60)}/분'
        left = (gold.right if gold else 60) + 6
        sale = ref.get('sale')
        if sale:
            # a purchase replaces the per-minute income for a moment; a talking guest's line gets a face and scrolls
            who, bread, amount, said, face = sale['who'], sale['bread'], sale['amount'], sale['said'], sale['face']
            shift = face.get_width() + 4 if face else 0
            room, font = BAR_W - 154 - 6 - left - shift, cafe.font(11, True)
            overflow, elapsed = 0, now - sale['start']
            if said:
                per_min = f'{who}: {said} +{amount}'
                overflow = max(0, font.size(per_min)[0] - room)
                life = 0.8 + overflow / SCROLL_PX + 1.4
            else:
                per_min = next((line for line in (
                    f'{who}{josa(who, "이", "가")} {bread}{josa(bread, "을", "를")} 사갔어요 +{amount}',
                    f'{who}{josa(who, "이", "가")} {bread} 구매 +{amount}', f'{who} · {bread} +{amount}',
                    f'{who} +{amount}') if font.size(line)[0] <= room), f'+{amount}')
                life = SALE_SECONDS
            if elapsed < life:
                if face:
                    win.blit(face, face.get_rect(midleft=(left, bar.centery)))
                win.set_clip(pg.Rect(left + shift, bar.y, room + 4, BAR_H))
                cafe.text(win, per_min, 11, skin['text'], left + shift - min(overflow, max(0, elapsed - 0.8) * SCROLL_PX),
                          bar.centery, True, 'ml', False, False)
                win.set_clip(None)
                per_min = None
            else:
                ref['sale'] = None
        if per_min:
            cafe.text(win, per_min, 11, skin['text'], left, bar.centery, True, 'ml', False, False)
        btns = {}
        x = 108
        rect = pg.Rect(BAR_W - 34, bar.y + 6, 22, 20)
        btns['quit'] = rect
        button(win, rect, 'X', rect.collidepoint(mouse), False, skin['btn'])
        # mode buttons, left to right: mini - landscape - portrait
        for key, offset, size in (('portrait', 64, (7, 11)), ('landscape', 94, (12, 7)), ('restore', 124, None),
                                  ('settings', 154, 'gear')):
            rect = pg.Rect(BAR_W - offset, bar.y + 6, 26, 20)
            btns[key] = rect
            button(win, rect, '', rect.collidepoint(mouse), False, skin['btn'])
            if size == 'gear':
                draw_gear(win, rect.center, cafe.BROWN_D, cafe.ACCENT if rect.collidepoint(mouse) else skin['btn'])
            elif size:
                icon = pg.Rect(0, 0, *size)
                icon.center = rect.center
                pg.draw.rect(win, cafe.BROWN_D, icon, 1)
            else:
                pg.draw.rect(win, cafe.BROWN_D, rect.inflate(-12, -10), 2)
        ref['btns'] = btns
        tip = None
        if pg.mouse.get_focused():
            for key, rect in btns.items():
                if not rect.collidepoint(mouse):
                    continue
                if key == 'settings':
                    tip = ('설정', rect.centerx)
                elif key == 'restore':
                    tip = ('미니모드', rect.centerx)
                elif key == 'landscape':
                    tip = ('가로모드', rect.centerx)
                elif key == 'portrait':
                    tip = ('세로모드', rect.centerx)
                elif key == 'quit':
                    tip = ('종료', rect.centerx)
                else:
                    tip = (f'손님 {key[1]}배', rect.centerx)
        if tip:
            draw_bubble(win, tip[0], tip[1], skin=skin)
        elif notes:
            draw_bubble(win, notes[0][0], face=notes[0][2], skin=skin)

    # ---- input (positions are real window pixels) -----------------------------------
    def handle(event):
        """Consume every event while in bar mode; drag moves the strip."""
        game = ref['game']
        if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
            for key, rect in ref['btns'].items():
                if rect.collidepoint(event.pos):
                    if key == 'restore':
                        leave(game)
                    elif key == 'settings':
                        # same as the mini window's gear: back to the normal window with the dialog open
                        leave(game)
                        game.mini = False
                        if ref.get('ui') is not None:
                            ref['ui'].open_settings()
                    elif key in ('landscape', 'portrait'):
                        leave(game)
                        game.portrait = key == 'portrait'
                        game.mini = False
                    elif key == 'quit':
                        pg.event.post(pg.event.Event(pg.QUIT))   # same path as closing the window
                    else:
                        game.toggle_guest_speed(key[1])
                    return
            pos = cafe.win_pos()      # None when the window handle is unavailable
            # Anchor to the original click, even when several events arrive in one batch.
            ref['drag'] = event.pos if pos is not None else None
            if ref['drag'] is not None:
                hwnd = pg.display.get_wm_info().get('window')
                if hwnd:
                    ctypes.windll.user32.SetCapture(ctypes.c_void_p(hwnd))
        elif event.type == pg.MOUSEMOTION and ref['drag']:
            point = _Point()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            dx, dy = ref['drag']
            game.mini_pos = (point.x - dx, point.y - dy)
            cafe.win_move(*game.mini_pos)
        elif event.type == pg.MOUSEBUTTONUP and event.button == 1 and ref['drag']:
            ref['drag'] = None
            ctypes.windll.user32.ReleaseCapture()
            game.mini_pos = cafe.win_pos() or getattr(game, 'mini_pos', None)

    # ---- mini window: drag from anywhere (guests and toolbar included) ---------------
    # The game only starts a native caption drag on empty background, so grabbing a guest or
    # a button moved nothing. Pressing and moving past a few pixels now drags the window.
    mini_drag_state = {'start': None, 'origin': None, 'moving': False}
    DRAG_THRESHOLD = 4

    def cursor():
        point = _Point()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def mini_drag(event, logical_pos=None):
        """True = event consumed by the drag. Only the bottom toolbar row starts a drag."""
        game = ref['game']
        st = mini_drag_state
        if game is None or not game.mini or game.bar:
            st.update(start=None, moving=False)
            return False
        if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
            on_bar = logical_pos is not None and logical_pos[1] // 2 >= ROW_Y - 2
            origin = cafe.win_pos() if on_bar else None
            st.update(start=cursor() if origin is not None else None, origin=origin, moving=False)
        elif event.type == pg.MOUSEMOTION and st['start'] is not None:
            x, y = cursor()
            sx, sy = st['start']
            if not st['moving'] and abs(x - sx) + abs(y - sy) < DRAG_THRESHOLD:
                return False
            st['moving'] = True
            ox, oy = st['origin']
            game.mini_pos = (ox + x - sx, oy + y - sy)
            cafe.win_move(*game.mini_pos)
            return True
        elif event.type == pg.MOUSEBUTTONUP and event.button == 1 and st['start'] is not None:
            moved = st['moving']
            st.update(start=None, moving=False)
            if moved:
                game.mini_pos = cafe.win_pos() or game.mini_pos
                return True          # a drag is not a click
        return False

    cafe._bar_api = type('MiniBar', (), dict(
        active=staticmethod(active), draw=staticmethod(draw), handle=staticmethod(handle),
        mini_drag=staticmethod(mini_drag), game=staticmethod(lambda: ref['game']),
        mini_click=staticmethod(mini_click), enter=staticmethod(enter), size=(WIN_W, WIN_H)))


class _Point(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


# ======================================================================
# mini_window
# ======================================================================
# Mini mode window behaviour.
#
# * The mini window / taskbar bar stay on top of other windows. The existing
#   settings toggle ("항상 위") turns that off; it now only concerns mini mode and
#   defaults to on (saves from before this change are switched on once).
# * Pressing the normal window's minimize button sends the game to the taskbar bar
#   instead of minimizing it for real.
import ctypes
import os


def install_mini_window(cafe):
    if getattr(cafe, '_mini_window_installed', False):
        return
    cafe._mini_window_installed = True
    pg = cafe.pygame
    Game = cafe.Game
    ref = {'game': None}
    user32 = ctypes.windll.user32

    # ---- always on top: mini / bar only --------------------------------------------
    original_set_topmost = cafe.set_topmost

    def set_topmost(on):
        game = ref['game']
        return original_set_topmost(bool(on and game is not None and game.mini))

    cafe.set_topmost = set_topmost

    original_init = Game.__init__

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        ref['game'] = self
        self.topmost = True

    Game.__init__ = __init__

    marker = os.path.join(cafe.SAVE_DIR, 'mini_topmost_v1')
    original_load = Game.load

    def load(self):
        original_load(self)
        ref['game'] = self
        if not os.path.exists(marker):          # one-time: older saves stored the old default (off)
            self.topmost = True
            try:
                os.makedirs(cafe.SAVE_DIR, exist_ok=True)
                open(marker, 'w').close()
            except OSError:
                pass

    Game.load = load

    # settings dialog wording: the toggle now applies to mini mode only
    draw = cafe.UI.draw_settings
    labels = {'항상 위: ': '미니·툴바모드 항상 위: ',
              '끄면 브라우저 등 다른 창 뒤로 가려집니다': '끄면 미니·툴바모드가 다른 창 뒤로 가려집니다'}
    draw.__code__ = draw.__code__.replace(co_consts=tuple(
        labels.get(v, v) if isinstance(v, str) else v for v in draw.__code__.co_consts))

    # ---- minimize button -> taskbar bar ----------------------------------------------
    real_get, real_poll = pg.event.get, pg.event.poll

    def hwnd():
        return pg.display.get_wm_info()['window']

    def watch(events):
        game = ref['game']
        if game is None:
            return events
        api = getattr(cafe, '_bar_api', None)
        try:
            if game.bar and user32.IsIconic(hwnd()):
                user32.ShowWindow(hwnd(), 9)       # SW_RESTORE: the bar window must stay visible
            for event in events:
                if event.type == pg.WINDOWMINIMIZED and api and not game.mini:
                    game.mini = True
                    api.enter(game)
                    user32.ShowWindow(hwnd(), 9)
                    break
        except Exception:
            pass
        return events

    pg.event.get = lambda *a, **k: watch(real_get(*a, **k))
    pg.event.poll = lambda: (watch([real_poll()]) or [pg.event.Event(pg.NOEVENT)])[0]


# ======================================================================
# monitor2
# ======================================================================
# Open every game window (normal / portrait / landscape / mini / bar) on monitor 2.
#
# Only active with 2+ monitors; with a single monitor nothing is touched. Monitor 2
# is the first non-primary monitor. After each display.set_mode the window is moved
# onto it if it landed elsewhere: frameless windows (mini / bar) keep their offset
# from the work area's bottom-right corner, framed windows are centred.
import ctypes
from ctypes import wintypes


_user32 = ctypes.WinDLL('user32')   # private handle: the game sets its own argtypes on ctypes.windll.user32


class _MONINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


def _monitors():
    """[(monitor rect, work rect, is_primary)] in Windows enumeration order."""
    found = []
    proc_t = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HANDLE, wintypes.HDC,
                                ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def cb(hmon, hdc, rect, lparam):
        mi = _MONINFO()
        mi.cbSize = ctypes.sizeof(mi)
        if _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            found.append((mi.rcMonitor, mi.rcWork, bool(mi.dwFlags & 1)))
        return 1

    _user32.EnumDisplayMonitors(None, None, proc_t(cb), 0)
    return found


def _second():
    mons = _monitors()
    if len(mons) < 2:
        return None
    others = [m for m in mons if not m[2]]
    return (others or mons[1:])[0]


def install_monitor2(cafe):
    if getattr(cafe, '_monitor2_installed', False):
        return
    cafe._monitor2_installed = True
    pg = cafe.pygame
    user32 = _user32
    real = pg.display.set_mode

    def relocate(flags):
        try:
            target = _second()
            if target is None:
                return
            mon, work, _ = target
            hwnd = pg.display.get_wm_info()['window']
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            w, h = r.right - r.left, r.bottom - r.top
            cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
            if mon.left <= cx < mon.right and mon.top <= cy < mon.bottom:
                return                                  # already on monitor 2
            src = None
            for m, wk, _p in _monitors():
                if m.left <= cx < m.right and m.top <= cy < m.bottom:
                    src = wk
                    break
            if flags & pg.NOFRAME and src is not None:
                x = work.right - (src.right - r.right)
                y = work.bottom - (src.bottom - r.bottom)
            else:
                x = (work.left + work.right - w) // 2
                y = (work.top + work.bottom - h) // 2
            x = max(work.left, min(x, work.right - w))
            y = max(work.top, min(y, work.bottom - h))
            user32.SetWindowPos(hwnd, None, int(x), int(y), 0, 0, 0x0001 | 0x0004)  # NOSIZE | NOZORDER
        except Exception:
            pass

    pending = {'flags': 0, 'on': False}
    real_win_move = cafe.win_move

    def win_move(x, y):
        # the game positions the window right after set_mode; redirect that first move
        if pending['on']:
            pending['on'] = False
            try:
                target = _second()
                hwnd = pg.display.get_wm_info()['window']
                r = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                w, h = r.right - r.left, r.bottom - r.top
                if target is not None and not (target[0].left <= x + w // 2 < target[0].right
                                               and target[0].top <= y + h // 2 < target[0].bottom):
                    for m, wk, _p in _monitors():
                        if m.left <= x + w // 2 < m.right and m.top <= y + h // 2 < m.bottom:
                            work = target[1]
                            if pending['flags'] & pg.NOFRAME:
                                x = work.right - (wk.right - (x + w))- w
                                y = work.bottom - (wk.bottom - (y + h)) - h
                            else:
                                x = (work.left + work.right - w) // 2
                                y = (work.top + work.bottom - h) // 2
                            x = max(work.left, min(x, work.right - w))
                            y = max(work.top, min(y, work.bottom - h))
                            break
            except Exception:
                pass
        return real_win_move(x, y)

    def set_mode(size=(0, 0), flags=0, *args, **kwargs):
        surface = real(size, flags, *args, **kwargs)
        relocate(flags)
        pending['flags'], pending['on'] = flags, True
        return surface

    pg.display.set_mode = set_mode
    cafe.win_move = win_move



# --- merged from tabs_merge.py: 꾸미기 tab folded into 가구 tab ---
DECOR_TAB = 3
FURN_TAB = 2
FURN_BAND = 58
# (id, chip label, header-name prefixes shown under that chip)
FURN_SUBS = (('stand', '판매대', ('판매대', '진열대 스킨')), ('table', '식탁·의자', ('식탁',)),
             ('kitchen', '주방', ('주방',)), ('scene', '창밖·계절', ('창밖', '계절')),
             ('acc', '장식', ('액세서리', '창가', '구석')), ('wall', '벽지', ('벽지',)),
             ('floor', '바닥', ('바닥',)), ('sign', '간판', ('벽 간판',)),
             ('light', '조명', ('조명',)), ('mat', '발매트', ('입구',)))


def install_merged_tabs(cafe):
    if getattr(cafe, '_merged_tabs_installed', False):
        return
    cafe._merged_tabs_installed = True
    UI = cafe.UI
    original_rows, original_draw = UI.rows, UI.draw

    def rows(self):
        result = original_rows(self)
        if self.tab == FURN_TAB:
            self.tab = DECOR_TAB
            try:
                result.extend(original_rows(self))
            finally:
                self.tab = FURN_TAB
            if not getattr(self, '_furn_all', False):
                result = furn_group(result, getattr(self, 'furn_sub', FURN_SUBS[0][0]))
        return result

    def furn_group(rows, sub):
        names = dict((sid, keys) for sid, _, keys in FURN_SUBS)[sub]
        out, keep = [], False
        for row in rows:
            if row.get('kind') == 'hdr':
                keep = row['name'].startswith(names)
            if keep:
                out.append(row)
        return out

    def furn_chips(self, surface):
        px, py, pw = cafe.PANEL_X, cafe.PANEL_Y, cafe.PANEL_W
        band = cafe.pygame.Rect(px + 4, py + 88, pw - 8, FURN_BAND)
        cafe.pygame.draw.rect(surface, (250, 232, 196), band)
        per = (len(FURN_SUBS) + 1) // 2
        bw = (band.w - 4) // per
        cur = getattr(self, 'furn_sub', FURN_SUBS[0][0])
        self._furn_hits = []
        for i, (sid, name, _) in enumerate(FURN_SUBS):
            rect = cafe.pygame.Rect(band.x + 2 + (i % per) * bw, band.y + 3 + (i // per) * 28, bw - 3, 24)
            active = sid == cur
            cafe.pygame.draw.rect(surface, (232, 150, 70) if active else (214, 184, 140), rect)
            cafe.pygame.draw.rect(surface, (54, 34, 24), rect, 2)
            size = 12
            while size > 8 and cafe.font(size, True).size(name)[0] > rect.w - 6:
                size -= 1
            cafe.text(surface, name, size, (255, 255, 255) if active else (84, 52, 34),
                      rect.centerx, rect.centery, True, 'mc')
            self._furn_hits.append((rect, sid))

    def draw(self, surface, mouse):
        if self.tab == DECOR_TAB:
            self.tab = FURN_TAB
        saved_off = cafe.LIST_OFF
        if self.tab == FURN_TAB:
            cafe.LIST_OFF = saved_off + FURN_BAND + 4
        try:
            original_draw(self, surface, mouse)
        finally:
            cafe.LIST_OFF = saved_off
        if self.tab == FURN_TAB:
            furn_chips(self, surface)
        px, py, pw = cafe.PANEL_X, cafe.PANEL_Y, cafe.PANEL_W
        if self.tab == FURN_TAB and not self.preview_items:
            g = self.g
            cafe.pygame.draw.rect(surface, (250, 232, 196), (px + 4, py + 52, pw - 8, 36))
            cafe.text(surface, f"판매대·가구 +{round((g.b_stand + g.b_furn) * 100)}%  ·  "
                      f"꾸미기 +{round(g.b_int * 100)}%", 12, (110, 76, 52), px + 12, py + 62, True)
        shown = [i for i in range(len(cafe.TABS)) if i != DECOR_TAB]
        bg = surface.get_at((px + 5, py + 28))
        surface.fill(bg, (px + 6, py + 8, pw - 12, 40))
        self.hit[:] = [h for h in self.hit if h[1] != 'tab']
        tw = (pw - 16) // len(shown)
        for slot, i in enumerate(shown):
            name = cafe.TABS[i]
            rect = cafe.pygame.Rect(px + 8 + slot * tw, py + 8, tw - 2, 40)
            active = i == self.tab
            cafe.pygame.draw.rect(surface, (232, 150, 70) if active else (214, 184, 140), rect)
            cafe.pygame.draw.rect(surface, (54, 34, 24), rect, 2)
            if rect.collidepoint(mouse) and not active:
                cafe.pygame.draw.rect(surface, (255, 255, 255), rect, 2)
            size = 15 if cafe.PORTRAIT else 12
            while size > 8 and cafe.font(size, True).size(name)[0] > rect.w - 6:
                size -= 1
            cafe.text(surface, name, size, (255, 255, 255) if active else (84, 52, 34),
                      rect.centerx, rect.centery, True, 'mc')
            self.hit.append((rect, 'tab', i))

    original_init = UI.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        # Furniture thumbnails render whole cafe shells (~1.4s); do it at startup,
        # not on the first click of the tab.
        saved = self.tab
        self.tab = FURN_TAB
        self._furn_all = True
        try:
            self.rows()
        except Exception:
            pass
        finally:
            self.tab = saved
            self._furn_all = False

    original_click = UI.click

    def click(self, pos, game, scene_clicks):
        if self.tab == FURN_TAB and not self.settings_open:
            for rect, sid in getattr(self, '_furn_hits', ()):
                if rect.collidepoint(pos):
                    self.furn_sub = sid
                    self.scroll[FURN_TAB] = 0
                    return
        return original_click(self, pos, game, scene_clicks)

    UI.__init__, UI.rows, UI.draw, UI.click = init, rows, draw, click


# --- smooth, faster mouse-wheel scrolling for every panel list ---
WHEEL_PX = 150          # per wheel notch (the stock list moved 50px, which made long lists a chore)
WHEEL_MIN_PX = 50       # smallest per-notch step, used for short lists
WHEEL_EASE = 16.0      # higher = snappier glide toward the target


def install_smooth_scroll(cafe):
    if getattr(cafe, '_smooth_scroll_installed', False):
        return
    cafe._smooth_scroll_installed = True
    pg, UI = cafe.pygame, cafe.UI
    wheel = {'y': 0, 't': 0.0}
    real_get = pg.event.get

    def get(*args, **kwargs):
        events = real_get(*args, **kwargs)
        for ev in events:
            if ev.type == pg.MOUSEWHEEL:
                wheel['y'] += ev.y
                wheel['t'] = time.perf_counter()
        return events

    pg.event.get = get
    original_draw = UI.draw

    def draw(self, surface, mouse):
        now = time.perf_counter()
        st = self.__dict__.setdefault('_smooth', {})
        ends = self.__dict__.setdefault('_smooth_ends', {})
        tab = self.tab
        cur, target, last, stamp = st.get(tab, (0.0, 0.0, 0, now))
        pos = self.scroll[tab]
        notch, wheel['y'] = wheel['y'], 0
        if notch and now - wheel['t'] < 0.5 and not self.settings_open and self.panel_rect().collidepoint(mouse):
            pos = last                               # undo the stock 50px step, glide instead
            limit = ends.get(tab)                    # short lists: smaller step so they don't whip past
            step = WHEEL_PX if limit is None else min(WHEEL_PX, max(WHEEL_MIN_PX, limit / 4))
            target = max(0.0, target - notch * step)
            if limit is not None:
                target = min(target, float(limit))
        elif pos != last:                            # list was reset or jumped by other code
            cur = target = float(pos)
        if abs(target - cur) < 1:
            cur = target
        else:
            cur += (target - cur) * (1 - math.exp(-WHEEL_EASE * min(now - stamp, 0.1)))
        self.scroll[tab] = int(round(cur))
        try:
            original_draw(self, surface, mouse)
        finally:
            shown = self.scroll[tab]
            if shown < int(round(cur)):              # clamped at the bottom of the list
                cur = target = float(shown)
                ends[tab] = shown                    # learned the list's real end
            elif shown > ends.get(tab, shown):
                ends.pop(tab)                        # list grew
            st[tab] = (cur, target, shown, now)

    UI.draw = draw
