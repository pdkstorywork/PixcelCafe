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
import time

BAR_W, BAR_H = 260, 32
BUB_H = 42                      # transparent strip above the bar for the speech bubble
WIN_W, WIN_H = BAR_W, BAR_H + BUB_H
NOTE_SECONDS = 6.0
ALPHA_IDLE, ALPHA_HOVER = 150, 255   # bar opacity (0-255); fully opaque while hovered
NOTE_WORDS = ('도감', '손님', '등장', '우정', '변종', '선물', '업적')
# mini bar buttons (logical 320x228 coordinates): settings sits right of the gold amount,
# minimize takes the old settings slot.
MIN_RECT = (224, 210, 22, 16)
SPEED_W = (22, 24)              # x5 / x10 button widths in the mini window
SETTINGS_W = 24                 # settings button sits where x5 starts; x5/x10 shift right of it
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

    def enter(game):
        game._mini_pos_stash = game.mini_pos
        game.mini_pos = default_pos()          # the bar always sits on the taskbar
        game.bar = True
        game.mode_dirty = True

    def leave(game):
        game.mini_pos = mini_default_pos() or getattr(game, '_mini_pos_stash', None)
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
            return speed_fn(surface, game, mouse, x, y, mini)
        # mini layout: settings button first (next to the gold), then narrower x5/x10
        skin = palette(game)
        ref['settings_x'] = x
        x += SETTINGS_W + 4
        buttons = []
        for speed, width in ((5, SPEED_W[0]), (10, SPEED_W[1])):
            rect = pg.Rect(x, y, width, 16)
            active = game.guest_speed == speed
            pg.draw.rect(surface, cafe.ACCENT if active else skin['btn'], rect)
            pg.draw.rect(surface, cafe.INK, rect, 1)
            if rect.collidepoint(mouse):
                pg.draw.rect(surface, (255, 255, 255), rect, 1)
            cafe.text(surface, f'x{speed}', 10, (255, 255, 255) if active else cafe.BROWN_D,
                      rect.centerx, rect.centery, True, 'mc', aa=False)
            buttons.append((rect, speed))
            x = rect.right + 3
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

    def draw_mini(screen, game, scene, mouse):
        ref['game'] = game
        skin = palette(game)
        apply_skin(skin)
        if game.bar:
            off = pg.Rect(-100, -100, 1, 1)
            return [], off, [], off
        # the original tooltip/hover for the old settings slot must not fire on the minimize button
        hidden = (-1000, -1000) if pg.Rect(MIN_RECT).collidepoint(mouse) else mouse
        result = original_draw_mini(screen, game, scene, hidden)
        top, bottom = screen.get_height() - 20, screen.get_height() - 2
        pg.draw.line(screen, skin['light'], (6, top + 1), (screen.get_width() - 7, top + 1))   # bevel
        pg.draw.line(screen, skin['edge'], (4, bottom), (screen.get_width() - 5, bottom))
        pg.draw.rect(screen, skin['fill'], (MIN_RECT[0] - 1, MIN_RECT[1] - 1, MIN_RECT[2] + 2, MIN_RECT[3] + 2))
        settings = pg.Rect(ref.get('settings_x', 83), 210, SETTINGS_W, 16)
        rect = pg.Rect(MIN_RECT)
        for box, label in ((settings, '설정'), (rect, None)):
            pg.draw.rect(screen, cafe.ACCENT if box.collidepoint(mouse) else skin['btn'], box)
            pg.draw.rect(screen, cafe.INK, box, 1)
            if label:
                cafe.text(screen, label, 10, cafe.BROWN_D, box.centerx, box.centery, True, 'mc', False, False)
            else:
                pg.draw.line(screen, cafe.BROWN_D, (box.x + 6, box.bottom - 5), (box.right - 7, box.bottom - 5), 2)
        if rect.collidepoint(mouse):
            label = '미니바모드'
            width = cafe.font(10, True).size(label)[0] + 10
            tip = pg.Rect(0, rect.y - 20, width, 16)
            tip.right = min(rect.right, screen.get_width() - 2)
            pg.draw.rect(screen, (255, 250, 232), tip)
            pg.draw.rect(screen, cafe.INK, tip, 1)
            cafe.text(screen, label, 10, cafe.BROWN_D, tip.centerx, tip.centery, True, 'mc', False, False)
        result = result[:3] + (settings,)
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
            enter(game)
            return True
        return False

    # ---- notifications --------------------------------------------------------------
    original_toast = Game.toast
    original_paid = Game.customer_paid

    def customer_paid(self, customer, *args, **kwargs):
        ref['customer'] = customer      # lets toast() know who a dex/friendship toast is about
        try:
            return original_paid(self, customer, *args, **kwargs)
        finally:
            ref['customer'] = None

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

    def toast(self, msg):
        original_toast(self, msg)
        if self.bar and any(word in msg for word in NOTE_WORDS):
            who = ref.get('customer') or (self.customers[-1] if self.customers else None)
            notes.append([msg, time.time() + NOTE_SECONDS, face_of(who) if who else None])

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
        pg.draw.circle(win, skin['edge'], (16, bar.centery), 8)
        pg.draw.circle(win, cafe.GOLD, (16, bar.centery), 6)
        cafe.text(win, cafe.fmt(game.money), 14, skin['text'], 29, bar.centery, True, 'ml', False, True)
        btns = {}
        x = 108
        for speed, width in ((5, 36), (10, 42)):
            rect = pg.Rect(x, bar.y + 6, width, 20)
            btns[('speed', speed)] = rect
            button(win, rect, f'x{speed}', rect.collidepoint(mouse), game.guest_speed == speed, skin['btn'])
            x += width + 4
        rect = pg.Rect(BAR_W - 60, bar.y + 6, 22, 20)
        btns['quit'] = rect
        button(win, rect, 'X', rect.collidepoint(mouse), False, skin['btn'])
        rect = pg.Rect(BAR_W - 34, bar.y + 6, 26, 20)
        btns['restore'] = rect
        button(win, rect, '', rect.collidepoint(mouse), False, skin['btn'])
        inner = rect.inflate(-12, -10)
        pg.draw.rect(win, cafe.BROWN_D, inner, 2)
        ref['btns'] = btns
        tip = None
        if pg.mouse.get_focused():
            for key, rect in btns.items():
                if not rect.collidepoint(mouse):
                    continue
                if key == 'restore':
                    tip = ('미니모드로 돌아가기', rect.centerx)
                elif key == 'quit':
                    tip = ('종료', rect.centerx)
                else:
                    tip = (f'손님 도착 {key[1]}배', rect.centerx)
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
                    elif key == 'quit':
                        pg.event.post(pg.event.Event(pg.QUIT))   # same path as closing the window
                    else:
                        game.toggle_guest_speed(key[1])
                    return
            point = _Point()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            ref['drag'] = (point.x, point.y, *cafe.win_pos())
        elif event.type == pg.MOUSEMOTION and ref['drag']:
            point = _Point()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            sx, sy, wx, wy = ref['drag']
            cafe.win_move(wx + point.x - sx, wy + point.y - sy)
        elif event.type == pg.MOUSEBUTTONUP and event.button == 1 and ref['drag']:
            ref['drag'] = None
            game.mini_pos = cafe.win_pos()

    cafe._bar_api = type('MiniBar', (), dict(
        active=staticmethod(active), draw=staticmethod(draw), handle=staticmethod(handle),
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
    labels = {'항상 위: ': '미니모드 항상 위: ',
              '끄면 브라우저 등 다른 창 뒤로 가려집니다': '끄면 미니모드가 다른 창 뒤로 가려집니다'}
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

