"""Automatic cafe growth: recipe sales and active staff work replace paid upgrades.

The recovered runtime supplies drawing and movement. All new progression rules,
save fields, shop rows and compact tooltips are editable here.
"""
import math
from game_data import read_save, write_save

import time

SALES_PER_LEVEL = 12         # Lv1->2 needs this much sales credit
LEVEL_EXP = 3.0              # target = SALES_PER_LEVEL * level ** LEVEL_EXP
SHARE_CREDIT = 0.12          # every other unlocked bread learns a bit from each sale
LEVEL_PRICE = 0.12           # collection stays valuable without compounding sale prices
LEVEL_CURVE = 0.5            # square-root growth keeps long-running cafes on a small gold scale
# ---- Sale time: now and then a crowd (3~5 guests) rushes in together ----
SALE_CHECK_SEC = 60          # every minute the cafe rolls for a sale time
SALE_CHANCE = 0.15           # 15% per roll -> about once every 6~7 minutes
SALE_GUESTS = (3, 5)         # guests that rush in, inclusive range
SALE_GUEST_GAP = 1.0         # seconds between the rushing guests

STAFF_WORK_STEP = 8 * 3600   # Lv.10 takes 360 active hours (36~45 days at 8~10h/day)

# ---- Spread collection over 200~250 days at 8~10 active hours per day. ----
LAST_UNLOCK_HOURS = 2000
UNLOCK_CURVE = 1.6           # faster early discoveries, then regular long-term goals
UNLOCK_KINDS = ('furn', 'sold', 'earn', 'guest')   # rotation by recipe index; index 1 (first bread) asks for 8 sales


def _span(minutes):
    return f"{minutes}분" if minutes < 120 else f"{minutes / 60:.0f}시간"


def _unlock_task(index):
    """One unlock condition per recipe (RECIPES[index]); the kind rotates so each bread asks for something different."""
    kind = UNLOCK_KINDS[index % len(UNLOCK_KINDS)]
    if kind == 'earn':
        need = int(nice_number(200 * index ** 2))
        return dict(kind='earn', need=need, text=f"누적 수익 {need:,}G")
    if kind == 'furn':
        need = 1 + index // 6
        return dict(kind='furn', need=need, text=f"가구 {need}개 구매")
    if kind == 'guest':
        need = 3 + round(index * 0.6)       # pool is ~72 kinds; rares/legends are slow, so cap at ~30
        return dict(kind='guest', need=need, text=f"손님 {need}종 도감 수집")
    need = int(nice_number(8 * index ** 1.4))
    return dict(kind='sold', need=need, text=f"빵 {need}개 판매")


def unlock_hours(index, last_index=49):
    """Active hours required; the first discovery still needs only eight sales."""
    if index <= 1:
        return 0
    frac = ((index - 1) / max(1, last_index - 1)) ** UNLOCK_CURVE
    return int(round(LAST_UNLOCK_HOURS * frac))


def unlock_condition(index, last_index=49):
    cond = _unlock_task(index)
    cond['hours'] = unlock_hours(index, last_index)
    if cond['hours']:
        cond['text'] += f" · 영업 {cond['hours']:,}시간"
    return cond


# ---- Economy: first decorations within an hour; full shop is a long-term goal ----
MAX_GOLD = 10000      # top of the old recipe-price curve (used only as a position scale)
COST_SCALE = 10.0       # first employee 500G; final employee 9,500G
COST_CAP = 3000000
COST_UNIT = 0.1        # whole shop is priced at 1/10 of the old gold scale
FURN_COST_MULT = 990.0
SHOP_COST_MULT = 495.0  # staff, stands, interior, hero outfits
BUY_FIRST = 30        # position scale start
SELL_FIRST = 5        # starter bread price at Lv.1
SELL_GROWTH = 1.01      # later recipes remain worthwhile beside leveled starter breads
BONUS_SCALE = 0.04    # owned pieces stack; keep their income secondary to collecting them


EARLY_FURN_COST = (250.0, 500.0)   # the two cheapest base furniture pieces stay quick to buy


def nice_number(value):
    """Round to a clean figure: 5 steps for 2 digits, then 50 / 500 / 5,000 ... (2,500 / 3,000 / 35,000)."""
    value = float(value)
    if value < 10:
        return float(max(1, round(value)))
    step = 5 * 10 ** (len(str(int(value))) - 2)
    return float(round(value / step) * step)


def shop_price(value):
    """Shop prices in clean steps: 50G below 1,000G, 100G below 10,000G, then 500G (min 50G)."""
    step = 50 if value < 1000 else 100 if value < 10000 else 500
    return float(max(50, round(value / step) * step))


def _nice(value):
    return min(float(COST_CAP), shop_price(value))


def shrink_bonuses(cafe):
    """Scale every purchasable income bonus, in whole percents (never below +1%)."""
    groups = [cafe.STAFF, cafe.STANDS, cafe.FURN, *cafe.INTERIOR.values(), *cafe.HERO.values()]
    for group in groups:
        for item in group:
            if item.get('bonus'):
                item['bonus'] = max(0.01, round(item['bonus'] * BONUS_SCALE, 2))


def rebalance(cafe):
    """Rewrite every price in the recovered data tables, in place.

    Recipes follow a geometric curve BUY_FIRST..MAX_GOLD. Every other purchase
    (staff, stands, furniture, interior, hero outfits) keeps its old relative
    position in the progression: its old cost is located between two recipe
    unlock costs and mapped to the same point on the new curve.
    """
    recipes = cafe.RECIPES
    last = len(recipes) - 1
    old_buy = [r['buy'] for r in recipes]

    def curve(pos):
        return BUY_FIRST * (MAX_GOLD / BUY_FIRST) ** ((pos - 1) / (last - 1))

    def remap(cost, mult=SHOP_COST_MULT):
        if not cost or cost <= 0:
            return cost
        pos = 1.0
        if cost < old_buy[1]:
            pos = max(0.0, cost / old_buy[1])
        else:
            for i in range(1, last):
                if cost <= old_buy[i + 1]:
                    lo, hi = math.log(old_buy[i]), math.log(old_buy[i + 1])
                    pos = i + (math.log(cost) - lo) / (hi - lo)
                    break
            else:
                pos = float(last)
        return _nice(curve(pos) * COST_SCALE * mult * COST_UNIT)

    for i, recipe in enumerate(recipes):
        recipe['cond'] = unlock_condition(i, last) if i else None
        recipe['buy'] = 0
        sell = SELL_FIRST * SELL_GROWTH ** i
        recipe['sell'] = max(1, round(sell))    # whole gold only
        recipe['inc'] = sell / cafe.SELL_K
        recipe['upg'] = 0
    for staff in cafe.STAFF:
        staff['cost'] = remap(staff['cost'])
    for stand in cafe.STANDS:
        stand['cost'] = remap(stand['cost'])
    for item in cafe.FURN:
        item['cost'] = remap(item['cost'], FURN_COST_MULT)
        if item['id'] == 'tableL1':
            item['desc'] = '2석'
    for group in cafe.INTERIOR.values():
        for item in group:
            item['cost'] = remap(item['cost'])
    for group in cafe.HERO.values():
        for item in group:
            item['cost'] = remap(item['cost'])
    paid = sorted((item for item in cafe.FURN if item['cost'] > 0), key=lambda item: item['cost'])
    for item, cost in zip(paid, EARLY_FURN_COST):
        item['cost'] = cost
    shrink_bonuses(cafe)
    for key, cost in list(cafe.LEGACY_STANDS.items()):
        cafe.LEGACY_STANDS[key] = remap(cost)


def recipe_target(level):
    return max(1, int(SALES_PER_LEVEL * max(1, level) ** LEVEL_EXP))


def staff_target(level):
    return STAFF_WORK_STEP * max(1, level)


def _hours(seconds):
    return f"{seconds / 3600:.1f}시간" if seconds >= 3600 else f"{int(seconds // 60)}분"


def _nonnegative(value):
    try:
        number = float(value)
        return max(0.0, number) if math.isfinite(number) else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


GOLD_CAP = 9999999           # money and totals stop at 999만 9,999G


def gold(value):
    """Short gold text, e.g. 1,730G / 1.05만G / 7.4만G / 52.3만G / 999.9만G (cap 999만 9,999G, never 억).

    From 1만 up the figure is shown in 만 with at most 2 decimals below 10만 (so 500G steps stay exact)
    and 1 decimal from 10만; extra digits are cut, never rounded up.
    """
    n = min(GOLD_CAP, int(round(value)))
    sign, n = ('-', -n) if n < 0 else ('', n)
    if n < 10000:
        return f'{sign}{n:,}G'
    if n < 100000:
        text = f'{n // 100 / 100:.2f}'.rstrip('0').rstrip('.')
    else:
        text = f'{n // 1000 / 10:.1f}'.rstrip('0').rstrip('.')
    return f'{sign}{text}만G'


def install(cafe):
    if getattr(cafe, '_automatic_growth_installed', False):
        return
    cafe._automatic_growth_installed = True
    rebalance(cafe)
    cafe.fmt = gold
    Game, UI = cafe.Game, cafe.UI
    original_init = Game.__init__
    original_paid = Game.customer_paid
    original_hire = Game.hire
    original_update = Game.update
    original_load = Game.load
    original_rows = UI.rows
    original_draw = UI.draw
    original_btn = UI.btn
    original_tip = Game.tip

    def tip(self, *args, **kwargs):
        before, total = self.money, self.total
        original_tip(self, *args, **kwargs)
        # the original floors a tip at 1G, which is huge at the small gold scale: recompute it and
        # round up or down at random so tips stay whole gold without inflating income
        amt = self.inc / self.guest_speed * cafe.SPAWN_GAP * cafe.TIP_RATE
        whole = int(amt) + (cafe.random.random() < amt - int(amt))
        self.money, self.total = before + whole, total + whole

    def init(self):
        original_init(self)
        self.recipe_sales = {rid: 0 for rid in cafe.RECIPE}
        self.staff_work = {sid: 0.0 for sid in cafe.STAFF_BY_ID}
        self.auto_display_on = True
        self._auto_sig = None
        self.start_time = cafe.time.time()
        self._unlock_check = 0.0
        self.play_time = 0.0
        self.sold = 0

    def cond_value(self, kind):
        if kind == 'day':
            return self.day()
        if kind == 'earn':
            return int(self.total)
        if kind == 'furn':       # bought pieces only; the free starter furniture doesn't count
            return sum(1 for fid in self.furn if cafe.FURN_BY_ID.get(fid, {}).get('cost', 0) > 0)
        if kind == 'guest':
            return sum(1 for e in getattr(self, 'col', {}).get('guests', {}).values() if e.get('v', 0) > 0)
        return self.sold

    def cond_met(self, index):
        if index > 0 and self.rlv[cafe.RECIPES[index - 1]['id']] <= 0:
            return False         # unlock in order
        cond = cafe.RECIPES[index]['cond']
        return (self.cond_value(cond['kind']) >= cond['need']
                and self.play_time >= cond['hours'] * 3600)

    def cond_now(self, index):
        kind = cafe.RECIPES[index]['cond']['kind']
        unit = dict(day='일차', earn='G', furn='개', guest='종', sold='개')[kind]
        text = f"현재 {self.cond_value(kind):,}{unit}"
        if cafe.RECIPES[index]['cond']['hours']:
            text += f" · 영업 {self.play_time / 3600:,.1f}시간"
        return text

    def cond_progress(self, index):
        """Condition text with the player's current figure, e.g. '누적 수익 800G (현재 120G)'."""
        return f"{cafe.RECIPES[index]['cond']['text']} ({self.cond_now(index)})"

    def price(self, recipe):
        level = max(1, self.rlv[recipe['id']])
        return recipe['sell'] * (1 + LEVEL_PRICE * (level - 1) ** LEVEL_CURVE) * self.mult

    def day(self):
        return max(1, int((cafe.time.time() - self.start_time) // 86400) + 1)

    def buy_recipe(self, rid):
        # Recipes unlock by themselves on their cafe day; they can't be bought.
        self.toast(f"{cafe.RECIPE[rid]['name']}: 해금 조건 · {cafe.RECIPE[rid]['cond']['text']}")
        return False

    def unlock_due(self):
        today, opened = self.day(), []
        for index, recipe in enumerate(cafe.RECIPES):
            rid = recipe['id']
            if self.rlv[rid] <= 0 and cond_met(self, index):
                self.rlv[rid] = 1
                self.recipe_sales[rid] = 0.0
                self.auto_place(rid)
                opened.append(recipe['name'])
        if opened:
            self.toast(f"{today}일차 · 새 레시피 해금: {', '.join(opened[:2])}" +
                       (f" 외 {len(opened) - 2}종" if len(opened) > 2 else '') + '!')
            self.recalc()

    def hire(self, sid):
        # Employees are hired once. Further levels come only from active work.
        if self.staff_n[sid] > 0:
            return False
        return original_hire(self, sid)

    def paid(self, customer):
        if customer.paid:
            return
        # This sale is paid at its original price; growth affects later sales.
        original_paid(self, customer)
        changed = False
        for rid in customer.cart:
            if self.rlv.get(rid, 0) <= 0:
                continue
            self.sold += 1
            for other in self.recipe_sales:
                if self.rlv[other] > 0:
                    self.recipe_sales[other] += 1.0 if other == rid else SHARE_CREDIT
            for other in self.recipe_sales:
                before = self.rlv[other]
                if before <= 0:
                    continue
                while self.recipe_sales[other] >= recipe_target(self.rlv[other]):
                    self.recipe_sales[other] -= recipe_target(self.rlv[other])
                    self.rlv[other] += 1
                if self.rlv[other] != before:
                    changed = True
                    if other == rid:
                        self.toast(f"{cafe.RECIPE[rid]['name']} 판매 Lv.{self.rlv[rid]}!")
        if changed:
            self.recalc()

    def auto_signature(self):
        breads = sorted((r['id'] for r in cafe.RECIPES if self.rlv[r['id']] > 0),
                        key=lambda rid: self.price(cafe.RECIPE[rid]), reverse=True)
        return (tuple(breads), tuple((sid, len(self.disp[sid])) for sid in self.stands_sorted()))

    def auto_display(self):
        """The shop button now toggles auto-display instead of arranging once."""
        self.auto_display_on = not self.auto_display_on
        if self.auto_display_on:
            self._auto_sig = None
            self.toast('자동진열 ON · 비싼 빵부터 자동으로 진열해요')
        else:
            self.toast('자동진열 OFF · 직접 진열할 수 있어요')

    def run_auto_display(self):
        signature = self.auto_signature()
        if signature == self._auto_sig:
            return
        self._auto_sig = signature
        breads = signature[0]
        slots = [(sid, k) for sid in self.stands_sorted() for k in range(len(self.disp[sid]))]
        for i, (sid, k) in enumerate(slots):
            self.disp[sid][k] = breads[i] if i < len(breads) else None
        self.recalc()

    def sale_time(self, dt):
        if not 0 < dt <= 1.0:
            return
        left = getattr(self, 'sale_left', 0)
        if left > 0:
            self.sale_gap = getattr(self, 'sale_gap', 0.0) - dt
            if self.sale_gap <= 0:
                self.sale_gap = SALE_GUEST_GAP
                plan = self.make_plan()
                if plan:
                    self.spawn_customer(plan)
                self.sale_left = left - 1
            return
        self.sale_roll = getattr(self, 'sale_roll', 0.0) + dt
        if self.sale_roll >= SALE_CHECK_SEC:
            self.sale_roll = 0.0
            if cafe.random.random() < SALE_CHANCE:
                self.sale_left = cafe.random.randint(*SALE_GUESTS)
                self.sale_gap = 0.0
                self.toast(f"세일타임! 손님 {self.sale_left}명이 우르르 몰려와요!")

    def update(self, dt):
        original_update(self, dt)
        sale_time(self, dt)
        self.money = min(self.money, GOLD_CAP)
        self._unlock_check += dt
        if self._unlock_check >= 1.0:
            self._unlock_check = 0.0
            self.unlock_due()
        if self.auto_display_on:
            self.run_auto_display()
        # Match the live loop: no offline credit and no growth during long stalls.
        work = dt if 0 < dt <= 1.0 else 0.0
        self.play_time += work
        changed = False
        for sd in cafe.STAFF:
            sid = sd['id']
            level = self.staff_n[sid]
            if level <= 0 or level >= sd['max']:
                continue
            self.staff_work[sid] += work
            before = level
            while level < sd['max'] and self.staff_work[sid] >= staff_target(level):
                self.staff_work[sid] -= staff_target(level)
                level += 1
            if level == sd['max']:
                self.staff_work[sid] = 0.0
            if level != before:
                self.staff_n[sid] = level
                changed = True
                self.toast(f"{sd['name']} 근무 성장 Lv.{level}!")
        if changed:
            self.recalc()

    def save(self):
        data = dict(money=self.money, total=self.total, rlv=self.rlv,
                    furn=sorted(self.furn), int_own=sorted(self.int_own), equip=self.equip,
                    staff=self.staff_n, guest_speed=self.guest_speed, topmost=self.topmost,
                    display_settings_version=1, window_resolution=self.window_resolution,
                    fullscreen=self.fullscreen, start_time=self.start_time, hero_own=sorted(self.hero_own), hero_eq=self.hero_eq,
                    stands=sorted(self.stands), disp=self.disp, mini_scale=self.mini_scale,
                    mini=self.mini, portrait=self.portrait, mini_pos=self.mini_pos,
                    time=cafe.time.time(), growth_version=1,
                    recipe_sales=self.recipe_sales, staff_work=self.staff_work,
                    auto_display_on=self.auto_display_on,
                    play_time=self.play_time, sold=self.sold)
        try:
            write_save(cafe.SAVE_PATH, data)
        except (OSError, TypeError, ValueError):
            pass

    def load(self):
        data = read_save(cafe.SAVE_PATH)
        if not data:
            return  # missing/corrupt/non-object save: start fresh instead of crashing
        original_load(self)
        # The recovered loader accepts arbitrarily large recipe levels. Bound
        # persisted values before recipe_target raises them to a fractional power.
        for rid, level in self.rlv.items():
            self.rlv[rid] = min(2 ** 31 - 1, int(_nonnegative(level)))
        # A hand-edited or damaged save must never leave NaN/negative money:
        # save() refuses NaN, so progress would silently stop being written.
        self.money = round(_nonnegative(self.money))     # older saves may hold fractions
        self.total = round(_nonnegative(self.total))
        # Old saves already provide the paid recipe/staff levels. Keep them.
        start = _nonnegative(data.get('start_time', 0))
        now = cafe.time.time()
        self.start_time = start if 0 < start <= now else now
        self.auto_display_on = data.get('auto_display_on', True) is True
        self.play_time = _nonnegative(data.get('play_time', 0))
        self.sold = int(_nonnegative(data.get('sold', 0)))
        self._auto_sig = None
        sales = data.get('recipe_sales', {})
        work = data.get('staff_work', {})
        if not isinstance(sales, dict):
            sales = {}
        if not isinstance(work, dict):
            work = {}
        for rid in self.recipe_sales:
            self.recipe_sales[rid] = (min(_nonnegative(sales.get(rid, 0)),
                                          recipe_target(self.rlv[rid]) - .001)
                                      if self.rlv[rid] > 0 else 0)
        for sid in self.staff_work:
            level = self.staff_n[sid]
            # Keep earned seconds when growth targets change; update() grants all earned levels.
            self.staff_work[sid] = (_nonnegative(work.get(sid, 0))
                                   if 0 < level < cafe.STAFF_BY_ID[sid]['max'] else 0.0)

    def rows(self):
        g = self.g
        if self.tab == 1:
            result, next_shown, hidden_shown = [], False, False
            for index, recipe in enumerate(cafe.RECIPES):
                rid, level = recipe['id'], g.rlv[recipe['id']]
                if level > 0:
                    result.append(dict(kind='recipe', id=rid,
                        name=recipe['name'],
                        sub=f"판매가 {cafe.fmt(g.price(recipe))}",
                        price=f"Lv.{level} {int(g.recipe_sales[rid])}/{recipe_target(level)}",
                        ok=False, state='owned', icon=cafe.icon_for('recipe', rid)))
                elif not next_shown:
                    next_shown = True
                    result.append(dict(kind='recipe', id=rid, name=recipe['name'],
                        sub=recipe['cond']['text'],
                        sub2=g.cond_now(index),
                        price='',
                        ok=False, state='locked', icon=cafe.icon_for('recipe', rid)))
                elif not hidden_shown:
                    hidden_shown = True
                    result.append(dict(kind='none', id=rid, name='???',
                        sub='???', price='', ok=False,
                        state='hidden', icon=cafe.icon_for('recipe', rid, 'hidden')))
            return result
        if self.tab == 4:
            result = []
            for sd in cafe.STAFF:
                sid, level = sd['id'], g.staff_n[sd['id']]
                if level == 0:
                    price, state = '영입 ' + cafe.fmt(cafe.staff_cost(sd, 0)), 'buy'
                    name = sd['name']
                    sub = sd['desc']
                else:
                    name = f"{sd['name']}  Lv.{level}/{sd['max']}"
                    sub = f"수익 +{int(sd['bonus'] * level * 100)}%"
                    if level >= sd['max']:
                        price, state = '최대 성장', 'max'
                    else:
                        price = f"근무 {_hours(g.staff_work[sid])}/{_hours(staff_target(level))}"
                        state = 'owned'
                result.append(dict(kind='staff', id=sid, name=name, sub=sub, price=price,
                    ok=level == 0 and g.money >= cafe.staff_cost(sd, 0), state=state,
                    icon=cafe.icon_for('staff', sid)))
            return result
        return original_rows(self)

    def btn(self, surface, label, rect, action, mouse, active):
        if isinstance(action, tuple) and action[0] == 'mode':
            return
        if action == 'auto_display':
            on = self.g.auto_display_on
            label, active = f"자동진열 {'ON' if on else 'OFF'}", on
        return original_btn(self, surface, label, rect, action, mouse, active)

    def draw(self, surface, mouse):
        self.g.inc *= 60
        try:
            original_draw(self, surface, mouse)
        finally:
            self.g.inc /= 60

    Game.__init__ = init
    Game.tip = tip
    Game.buy_recipe = buy_recipe
    Game.day = day
    Game.cond_value = cond_value
    Game.cond_now = cond_now
    Game.cond_met = cond_met
    Game.cond_progress = cond_progress
    Game.price = price
    Game.unlock_due = unlock_due
    Game.plan_upgrade = lambda self, recipe: (0, 0.0, False)
    Game.hire = hire
    Game.auto_signature = auto_signature
    Game.auto_display = auto_display
    Game.run_auto_display = run_auto_display
    Game.customer_paid = paid
    Game.update = update
    Game.save = save
    Game.load = load
    # 1x mini mode shrinks the art and breaks the pixels; only the 2x detail render is crisp.
    Game.mini_scale = property(lambda self: 2, lambda self, value: None)
    UI.rows = rows
    UI.btn = btn
    UI.draw = draw

    # Income per second is a fraction early on (0.17G/s), so it is shown per minute in whole gold.
    code = original_draw.__code__
    original_draw.__code__ = code.replace(co_consts=tuple(
        ' / 분' if value == ' / 초' else value for value in code.co_consts))

    short = {'세로 모드로 열기': '세로모드',
             '가로 모드로 열기 (화면 중앙)': '가로모드',
             '게임 닫기 (진행 상황 자동 저장)': '종료', '설정 열기': '설정', '/초': '/분'}
    code = cafe.UI.draw_row.__code__            # price buttons said "<n> 코인"; the unit is now the G in fmt
    cafe.UI.draw_row.__code__ = code.replace(co_consts=tuple(
        '' if value == ' 코인' else value for value in code.co_consts))
    code = cafe.draw_mini.__code__
    cafe.draw_mini.__code__ = code.replace(co_consts=tuple(
        short.get(value, value) if isinstance(value, str) else value
        for value in code.co_consts))
    mini_draw = cafe.draw_mini

    def draw_mini(screen, game, *args, **kwargs):
        game.inc *= 60
        try:
            return mini_draw(screen, game, *args, **kwargs)
        finally:
            game.inc /= 60
    cafe.draw_mini = draw_mini
    cafe.guest_speed_help = lambda speed: f'손님{speed}배'
    # fixed guest rate: no x5/x10 buttons. SPAWN_GAP 120s -> 24s equals the old 5x speed
    # (about 2.5 guests per minute), and only one guest is in the cafe at a time.
    cafe.SPAWN_GAP = 24.0
    cafe.MAX_CUST = 1
    cafe.Game.toggle_guest_speed = lambda self, speed: None
    _load = cafe.Game.load

    def load(self, *args, **kw):
        result = _load(self, *args, **kw)
        self.guest_speed = 1
        return result
    cafe.Game.load = load
