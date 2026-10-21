"""Headless balance regressions; --simulate runs a 300-day economy forecast.

The forecast uses real plans, payments, collection rolls and shop methods, but
skips walking and seating. The default 100 arrivals/hour matches a measured
late-game live loop (101/hour). Pass an arrival rate to explore other traffic.
This is a forecast, not a promise about each player's completion date.
Never reads or writes player saves.
"""
import datetime
import copy
import ctypes
import os
import random
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import PixelCafe as cafe
import collection
import game_data
import progression
import themes
import mini


def fresh_game():
    with patch.object(cafe.Game, 'load'), patch.object(cafe.Game, 'save'):
        game = cafe.Game()
    game.toast = lambda *args: None
    return game


def enclosed(function, name, visited=None):
    """Find recovered/installed rules without duplicating their implementations."""
    visited = set() if visited is None else visited
    if id(function) in visited:
        return None
    visited.add(id(function))
    if getattr(function, '__name__', '') == name:
        return function
    for cell in getattr(function, '__closure__', ()) or ():
        found = enclosed(cell.cell_contents, name, visited)
        if found is not None:
            return found
    return None


class BalanceTests(unittest.TestCase):
    def test_mini_to_toolbar_preserves_current_window_position(self):
        game = fresh_game()
        game.mini = True
        game.mini_pos = (20, 30)
        api = cafe._bar_api
        ref = dict(zip(api.handle.__code__.co_freevars,
                       (cell.cell_contents for cell in api.handle.__closure__)))['ref']
        with patch.dict(ref, game=game, drag=None, btns={}):
            with patch.object(cafe, 'win_pos', return_value=(-800, 350)):
                self.assertTrue(api.mini_click((mini.MIN_RECT[0] * 2 + 2, mini.MIN_RECT[1] * 2 + 2)))
            self.assertTrue(game.bar)
            self.assertEqual(game.mini_pos, (-800, 350 + int(mini.LOGICAL[1] * mini.VIEW) - mini.WIN_H))
            self.assertEqual(game._mini_pos_stash, (-800, 350))
            leave = enclosed(api.handle, 'leave')
            leave(game)
            self.assertEqual(game.mini_pos, (-800, 350))
            self.assertFalse(game.bar)

    def test_toolbar_drag_anchors_click_and_captures_mouse(self):
        game = fresh_game()
        api = cafe._bar_api
        ref = dict(zip(api.handle.__code__.co_freevars,
                       (cell.cell_contents for cell in api.handle.__closure__)))['ref']
        cursor = (950, 700)

        def cursor_position(pointer):
            point = ctypes.cast(pointer, ctypes.POINTER(mini._Point)).contents
            point.x, point.y = cursor
            return 1

        with patch.dict(ref, game=game, drag=None, btns={}):
            with patch.object(cafe, 'win_pos', return_value=(400, 300)), \
                    patch.object(cafe, 'win_move') as move, \
                    patch.object(cafe.pygame.display, 'get_wm_info', return_value={'window': 123}), \
                    patch.object(ctypes.windll.user32, 'SetCapture') as capture, \
                    patch.object(ctypes.windll.user32, 'ReleaseCapture') as release, \
                    patch.object(ctypes.windll.user32, 'GetCursorPos', side_effect=cursor_position):
                api.handle(cafe.pygame.event.Event(cafe.pygame.MOUSEBUTTONDOWN,
                                                 button=1, pos=(15, 52)))
                capture.assert_called_once()
                api.handle(cafe.pygame.event.Event(cafe.pygame.MOUSEMOTION, pos=(550, 400)))
                move.assert_called_once_with(935, 648)
                self.assertEqual(game.mini_pos, (935, 648))
                api.handle(cafe.pygame.event.Event(cafe.pygame.MOUSEBUTTONUP,
                                                 button=1, pos=(15, 52)))
                release.assert_called_once()
                self.assertIsNone(ref['drag'])

    def test_companion_preview_draws_without_changing_saved_crew(self):
        game = fresh_game()
        game.col['mates'] = ['n_cat_0']
        game.col['rep'] = 'n_cat_0'
        game.sync_staff()
        original_staff = game.staff[:]
        original_collection = copy.deepcopy(game.col)
        money = game.money
        ui = cafe.UI(game)
        ui.tab = 4
        ui.preview = ('mate', 'n_dog_0')
        view = ui.preview_game()
        self.assertIsNot(view, game)
        self.assertEqual([mate.mate_key for mate in view.staff], ['n_dog_0'])
        self.assertIs(ui.preview_game().staff[0], view.staff[0])
        cafe.pygame.display.set_mode((cafe.SW, cafe.SH))
        sprite = cafe.pygame.Surface((cafe.SW, cafe.SH), cafe.pygame.SRCALPHA)
        view.staff[0].draw(sprite)
        self.assertGreater(sprite.get_bounding_rect().width, 0)
        self.assertEqual(game.staff, original_staff)
        self.assertEqual(game.col, original_collection)
        self.assertEqual(game.money, money)
        ui.preview = ('mate', 'n_cat_0')
        self.assertEqual(ui.preview_game().staff[0].mate_key, 'n_cat_0')
        ui.tab = 0
        self.assertIs(ui.preview_game(), game)
        self.assertIsNone(ui._mate_preview)

    def test_companion_preview_leaves_empty_cafe_unchanged(self):
        game = fresh_game()
        ui = cafe.UI(game)
        ui.tab = 4
        ui.preview = ('mate', 'n_cat_0')
        self.assertEqual(len(ui.preview_game().staff), 1)
        self.assertEqual(game.staff, [])
        self.assertEqual(game.col['mates'], [])
        self.assertIsNone(game.col['rep'])
        ui.preview = None
        self.assertIs(ui.preview_game(), game)

    def test_active_hours_pace_collection(self):
        hours = [progression.unlock_hours(i) for i in range(50)]
        self.assertEqual(hours[:2], [0, 0])
        self.assertEqual(hours[-1], 2000)
        self.assertEqual(hours, sorted(hours))
        self.assertGreaterEqual(hours[-1] / 10, 200)
        self.assertLessEqual(hours[-1] / 8, 250)

    def test_elapsed_calendar_cannot_skip_work(self):
        game = fresh_game()
        game.start_time -= 400 * 86400
        game.total = 1_000_000
        game.rlv[cafe.RECIPES[1]['id']] = 1
        index = 2
        self.assertFalse(game.cond_met(index))
        game.play_time = cafe.RECIPES[index]['cond']['hours'] * 3600
        self.assertTrue(game.cond_met(index))
        self.assertIn('영업', game.cond_now(index))

    def test_first_discovery_and_owned_progress_survive(self):
        game = fresh_game()
        game.sold = 8
        game.unlock_due()
        self.assertEqual(game.rlv[cafe.RECIPES[1]['id']], 1)
        last = cafe.RECIPES[-1]['id']
        game.rlv[last] = 7
        game.unlock_due()
        self.assertEqual(game.rlv[last], 7)

    def test_work_ignores_long_stalls(self):
        game = fresh_game()
        before = game.play_time
        game.update(60)
        self.assertEqual(game.play_time, before)
        game.update(.1)
        self.assertAlmostEqual(game.play_time, before + .1)
        self.assertEqual(sum(progression.staff_target(lv) for lv in range(1, 10)), 360 * 3600)

    def test_shop_keeps_early_purchases_and_readable_bonuses(self):
        paid_furniture = sorted(i['cost'] for i in cafe.FURN if i['cost'])
        self.assertEqual(paid_furniture[:2], [250, 500])
        items = [*cafe.FURN, *cafe.STAFF, *cafe.STANDS,
                 *(i for group in cafe.INTERIOR.values() for i in group),
                 *(i for group in cafe.HERO.values() for i in group)]
        self.assertTrue(all(0 <= i['cost'] <= progression.COST_CAP for i in items))
        self.assertTrue(all(i['bonus'] >= .01 for i in items if i['bonus']))

    def test_collection_rates_and_real_calendar_are_preserved(self):
        self.assertEqual(game_data.LEGEND_P, .001)
        self.assertEqual(game_data.RARE_P, .05)
        self.assertEqual(game_data.FAMILY_P, .03)
        self.assertEqual(collection.occasion(datetime.date(2026, 12, 25)), 'christmas')
        self.assertEqual(collection.occasion(datetime.date(2026, 2, 10)), 'valentine')

    def test_seasonal_duplicates_prefer_missing_family(self):
        game = fresh_game()
        names = cafe.specials.FAMILY_NAMES
        keys = [f'fam_spring:{name}' for name in names]
        game.col['guests'] = {key: {'v': 1, 'lv': 0, 'gift': 0} for key in keys[:-1]}
        # All base family identities may already be known from a previous season.
        game.col['guests'].update({'famn_' + name: {'v': 1} for name in names})
        game.col['pity']['family:spring'] = game_data.DUPLICATE_LIMIT
        with patch.object(collection, 'occasion', return_value='spring'), patch.object(random, 'random', return_value=.01):
            game.spawn_customer([('pay',)])
        customer = game.customers[-1]
        self.assertEqual(customer.name, names[-1])
        self.assertEqual(game.col['pity']['family:spring'], game_data.DUPLICATE_LIMIT)
        customer.cart = ['bread']
        enclosed(cafe.Game.customer_paid, 'paid')(game, customer)
        self.assertEqual(game.col['pity']['family:spring'], 0)
        self.assertEqual(game.col['guests'][keys[-1]]['v'], 1)
        self.assertIn('family:spring', game_data.normalize_pity(game.col['pity']))


class StandPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cafe.pygame.init()
        cafe.pygame.display.set_mode((1, 1))
        cafe.build_sprites()
        cafe.GLOW = cafe.make_glow()

    def test_food_fits_shelves_for_every_stand_and_skin(self):
        for theme in (None, *themes.THEMES):
            for st in cafe.STANDS:
                with self.subTest(theme=theme, stand=st['id']):
                    layout = themes.stand_food_layout(st, theme)
                    self.assertEqual(len(layout), st['slots'])
                    rects = [cafe.pygame.Rect(x - w // 2, y - h, w, h)
                             for x, y, w, h in layout]
                    for i, rect in enumerate(rects):
                        self.assertTrue(cafe.stand_rect(st).contains(rect))
                        self.assertFalse(any(rect.colliderect(other) for other in rects[i + 1:]))
                        if theme:
                            self.assertGreaterEqual(rect.top, st['y'] + (13 if theme == 'autumn' else 9))
                            self.assertLessEqual(rect.bottom, st['y'] + 25)

    def test_empty_slots_stay_empty_and_food_is_between_stand_layers(self):
        st = cafe.STANDS[0]
        calls = []

        class Surface:
            def blit(self, food, position):
                calls.append(('food', position))

        with patch.object(cafe, '_stand_base', side_effect=lambda *a: calls.append('base')), \
                patch.object(cafe, '_stand_cover', side_effect=lambda *a: calls.append('cover')):
            cafe.draw_stand(Surface(), st, 0, [None, 'bread', None, 'bread'])
            self.assertEqual(calls[0], 'base')
            self.assertEqual(calls[-1], 'cover')
            self.assertEqual(len(calls), 4)
            food = cafe.art.placed_food(cafe.RECIPE['bread']['spr'], 12, 8)
            for actual, slot in zip(calls[1:-1], (1, 3)):
                x, y, _, _ = themes.stand_food_layout(st)[slot]
                self.assertEqual(actual[1], (x - food.get_width() // 2, y - food.get_height()))
            calls.clear()
            cafe.draw_stand(Surface(), st, 0, [])
            self.assertEqual(calls, ['base', 'cover'])

    def test_catalog_stands_keep_their_art_after_skin_purchase_and_preview(self):
        game = fresh_game()
        ui = cafe.UI(game)
        ui.tab = mini.FURN_TAB
        pixels = lambda image: cafe.pygame.image.tobytes(image, 'RGBA')
        cafe.icon_cache.clear()
        original = {st['id']: pixels(cafe.icon_for('stand', st['id'])) for st in cafe.STANDS}
        self.assertEqual(len(set(original.values())), len(cafe.STANDS))
        game.money = 10 ** 9
        game.buy_furn('spring_stand')
        ui.preview_items = {('furn', 'stand_skin'): 'winter_stand'}
        ui.preview_game()
        cafe.icon_cache.clear()
        for key, expected in original.items():
            self.assertEqual(pixels(cafe.icon_for('stand', key)), expected)

    def test_scene_uses_its_own_skin_without_leaking_preview(self):
        game = fresh_game()
        game.money = 10 ** 9
        game.buy_furn('spring_stand')
        game.buy_furn('winter_stand')
        ui = cafe.UI(game)
        ui.tab = mini.FURN_TAB
        ui.preview_items = {('furn', 'stand_skin'): 'spring_stand'}
        view = ui.preview_game()
        self.assertEqual(view.owned_furn('stand_skin')['id'], 'spring_stand')
        self.assertEqual(game.owned_furn('stand_skin')['id'], 'winter_stand')
        layers = cafe.art.stand_layers
        for scene_game, theme in ((view, 'spring'), (game, 'winter'), (view, 'spring')):
            seen = []

            def capture(key):
                result = layers(key)
                seen.append(result[0])
                return result

            with patch.object(cafe.art, 'stand_layers', side_effect=capture):
                cafe.render_scene(scene_game, cafe.art.dr.DetailSurface((cafe.SW, cafe.SH)))
            self.assertTrue(seen)
            path = Path(themes.__file__).parent / 'assets' / 'themes' / theme / 'native' / 'stand.png'
            expected = cafe.pygame.image.load(str(path)).convert_alpha()
            pixels = lambda image: cafe.pygame.image.tobytes(image, 'RGBA')
            for image in seen:
                self.assertEqual(pixels(image), pixels(expected))
            # Outside a scene, the glass and cake cases must retain distinct art.
            self.assertNotEqual(pixels(layers('stand4')[0]), pixels(layers('stand6')[0]))


class DoormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cafe.pygame.init()
        cafe.pygame.display.set_mode((1, 1))
        cafe.build_sprites()
        cafe.GLOW = cafe.make_glow()

    def test_assets_and_shop_preview_do_not_change_owned_mat(self):
        game = fresh_game()
        ui = cafe.UI(game)
        ui.tab = 3
        mats = [r for r in ui.rows() if r.get('id', '').endswith('_doormat')]
        self.assertEqual(len(mats), 8)
        prices = [cafe.FURN_BY_ID[row['id']]['cost'] for row in mats]
        self.assertEqual(prices, sorted(prices))
        before = set(game.furn)
        assets = [(f'{theme}_doormat', theme, 'doormat') for theme in themes.THEMES]
        assets += [(f'{key}_doormat', 'classic', key) for key, *_ in themes.EXTRA_DOORMATS]
        for ident, folder, filename in assets:
            image = cafe.pygame.image.load(str(Path(themes.__file__).parent /
                                           'assets' / 'themes' / folder / 'native' / f'{filename}.png'))
            self.assertEqual(image.get_size(), themes.DOORMAT_SIZE)
            self.assertEqual(image.get_at((0, 0)).a, 0)
            self.assertFalse(cafe.furn_rect(cafe.FURN_BY_ID[ident]))
            ui.preview_items = {('furn', 'doormat'): ident}
            view = ui.preview_game()
            self.assertEqual(view.owned_furn('doormat')['id'], ident)
            cafe.render_scene(view, cafe.art.dr.DetailSurface((cafe.SW, cafe.SH)))
            self.assertEqual(game.furn, before)
            self.assertFalse(game.theme_eq)

    def test_purchase_reapply_and_free_default(self):
        game = fresh_game()
        game.money = 0
        self.assertFalse(game.buy_furn('spring_doormat'))
        game.money = 10 ** 9
        keys = [f'{theme}_doormat' for theme in themes.THEMES]
        keys += [f'{key}_doormat' for key, *_ in themes.EXTRA_DOORMATS]
        for key in keys:
            money = game.money
            self.assertTrue(game.buy_furn(key))
            self.assertEqual(game.money, money - cafe.FURN_BY_ID[key]['cost'])
            self.assertEqual(game.owned_furn('doormat')['id'], key)
        money = game.money
        self.assertTrue(game.buy_furn('spring_doormat'))
        self.assertEqual(game.money, money)
        self.assertFalse(game.buy_furn('spring_doormat'))
        self.assertTrue(game.buy_furn(themes.DEFAULT_DOORMAT))
        self.assertIsNone(game.owned_furn('doormat'))
        self.assertEqual(game.money, money)
        self.assertNotIn(themes.DEFAULT_DOORMAT, game.furn)
        ui = cafe.UI(game)
        ui.tab = 3
        default = next(r for r in ui.rows() if r.get('id') == themes.DEFAULT_DOORMAT)
        self.assertEqual(default['state'], 'equipped')
        ui.preview_items = {('furn', 'doormat'): themes.DEFAULT_DOORMAT}
        self.assertIsNone(ui.preview_game().owned_furn('doormat'))

    def test_render_replaces_mat_and_scopes_shell_cache(self):
        game = fresh_game()
        game.money = 10 ** 9
        base_cache, base_image = cafe._shell_cache, cafe.art.image
        scenes = []
        # Fix time-dependent light effects so pixel comparisons isolate the mat.
        with patch.object(cafe, 'darkness', return_value=0):
            for key in (None, 'spring_doormat', 'cat_doormat', themes.DEFAULT_DOORMAT):
                if key:
                    game.buy_furn(key)
                scene = cafe.art.dr.DetailSurface((cafe.SW, cafe.SH))
                cafe.render_scene(game, scene)
                scenes.append(scene)
                self.assertIs(cafe._shell_cache, base_cache)
                self.assertIs(cafe.art.image, base_image)
                for scale in (2, 3):
                    self.assertEqual(cafe.art.dr.detail(scene, scale).get_size(),
                                     (cafe.SW * scale, cafe.SH * scale))
        pixels = lambda s: cafe.pygame.image.tobytes(s, 'RGBA')
        self.assertNotEqual(pixels(scenes[0]), pixels(scenes[1]))
        self.assertNotEqual(pixels(scenes[1]), pixels(scenes[2]))
        self.assertEqual(pixels(scenes[0]), pixels(scenes[3]))

    def test_save_load_choice_and_legacy_default_without_player_saves(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parent / 'build') as folder, ExitStack() as stack:
            stack.enter_context(patch.object(cafe, 'SAVE_DIR', folder))
            stack.enter_context(patch.object(cafe, 'SAVE_PATH', str(Path(folder) / 'save.json')))
            # Sidecar paths were captured at installation: redirect both to the
            # test directory. Never touch the real one-time mini-window marker.
            stack.enter_context(patch('mini.os.path.exists', return_value=True))
            for module in (themes, collection):
                stack.enter_context(patch.object(module, 'write_save', side_effect=lambda p, d:
                    game_data.write_save(Path(folder) / Path(p).name, d)))
                stack.enter_context(patch.object(module, 'read_save', side_effect=lambda p:
                    game_data.read_save(Path(folder) / Path(p).name)))
            game = fresh_game()
            game.money = 10 ** 9
            game.buy_furn('spring_doormat')
            game.buy_furn('golden_doormat')
            game.buy_furn('cat_doormat')
            game.save()
            restored = cafe.Game()
            restored.load()
            self.assertEqual(restored.owned_furn('doormat')['id'], 'cat_doormat')
            self.assertIn('golden_doormat', restored.furn)
            restored.buy_furn(themes.DEFAULT_DOORMAT)
            restored.save()
            default = cafe.Game()
            default.load()
            self.assertIsNone(default.owned_furn('doormat'))
            Path(folder, 'themes.json').unlink()
            legacy = cafe.Game()
            legacy.load()
            self.assertFalse(legacy.theme_eq)
            self.assertIn('golden_doormat', legacy.furn)


def simulate(hours_per_day, arrivals_per_hour=100, days=300, seed=1729):
    random.seed(seed)
    game = fresh_game()
    paid = enclosed(cafe.Game.customer_paid, 'paid')
    invite = enclosed(cafe.UI.click, 'invite')
    check = enclosed(cafe.Game.update, 'check')
    shop = []
    for group, method, owned in ((cafe.FURN, game.buy_furn, game.furn),
                                (cafe.STANDS, game.buy_stand, game.stands),
                                (cafe.STAFF, game.hire, game.staff_n)):
        shop.extend((i['cost'], i['id'], method, owned) for i in group if i['cost'])
    for groups, method, owned in ((cafe.INTERIOR, game.buy_int, game.int_own),
                                  (cafe.HERO, game.buy_hero, game.hero_own)):
        shop.extend((i['cost'], i['id'], method, owned) for group in groups.values() for i in group if i['cost'])
    shop.sort(key=lambda row: (row[0], row[1]))
    milestones = {}
    first_date = datetime.date(2026, 3, 1)
    for day in range(1, days + 1):
        with patch.object(collection, 'occasion', return_value=collection.occasion(first_date + datetime.timedelta(days=day - 1))):
            before = game.total
            for hour in range(hours_per_day):
                game.unlock_due()
                game.run_auto_display()
                for _ in range(arrivals_per_hour):
                    plan = game.make_plan()
                    if not plan:
                        continue
                    game.spawn_customer(plan)
                    customer = game.customers.pop()
                    customer.cart = [task[3] for task in plan if task[0] == 'pick']
                    paid(game, customer)
                    game.popups.clear()
                game.play_time += 3600
                for item in cafe.STAFF:
                    key = item['id']
                    level = game.staff_n[key]
                    if level:
                        game.staff_work[key] += 3600
                        while level < item['max'] and game.staff_work[key] >= progression.staff_target(level):
                            game.staff_work[key] -= progression.staff_target(level)
                            level += 1
                        game.staff_n[key] = level
                for key in list(game.col['guests']):
                    if not key.startswith('fama_') and key not in game.col['mates']:
                        invite(game, key)
                for key in game.col['mates']:
                    level = game.col['mate_lv'][key]
                    work = game.col['mate_work'].get(key, 0) + 3600
                    while level < game_data.MATE_MAX_LV and work >= progression.staff_target(level):
                        work -= progression.staff_target(level)
                        level += 1
                    game.col['mate_lv'][key], game.col['mate_work'][key] = level, work
                for cost, key, buy, owned in shop:
                    if not (owned.get(key, 0) if isinstance(owned, dict) else key in owned) and game.money >= cost:
                        buy(key)
                game.recalc()
                check(game)
                game.money = min(game.money, progression.GOLD_CAP)
            opened = sum(lv > 0 for lv in game.rlv.values())
            variants = sum(len(found) for found in game.col['variants'].values())
            if opened == 50:
                milestones.setdefault('recipes', day)
            if variants == 200:
                milestones.setdefault('variants', day)
            if all(owned.get(key, 0) if isinstance(owned, dict) else key in owned for _, key, _, owned in shop):
                milestones.setdefault('shop', day)
            if day in (1, 30, 100, 200, 250, 300):
                print(dict(hours=hours_per_day, day=day, recipes=opened, variants=variants,
                           shop_owned=sum(bool(owned.get(key, 0) if isinstance(owned, dict) else key in owned) for _, key, _, owned in shop),
                           shop_total=len(shop), gold=round(game.money), income=round(game.total - before)), flush=True)
    print('milestones', hours_per_day, milestones, flush=True)


class EatingAnimationTests(unittest.TestCase):
    def customer(self, game, furniture, index=0, kind='normal', name=None):
        customer = cafe.Customer(game, [], kind, name)
        seat = furniture['seats'][index]
        customer.x, customer.y = seat[:2]
        customer.seat = ((furniture['id'], index), seat)
        customer.route, customer.cur, customer.cart = [], ('sit',), ['bread']
        customer._arrive(game)
        return customer

    def test_four_cycles_use_simulation_time_and_release_the_seat(self):
        import small
        game = fresh_game()
        furniture = next(f for f in cafe.FURN if f['id'] == 'tableL1')
        customer = self.customer(game, furniture)
        game.customers = [customer]
        duration = customer.timer
        self.assertTrue(cafe.EAT_TIME[0] <= duration <= cafe.EAT_TIME[1])
        for cycle in range(4):
            customer.timer = duration - (cycle + .4) * small.MEAL_CYCLE
            self.assertEqual(small._meal_motion(customer)[2:], (True, True))
        customer.timer = duration - 4 * small.MEAL_CYCLE
        self.assertFalse(small._meal_motion(customer)[-1])
        before = (customer.x, customer.y, customer.facing, customer.timer)
        surface = cafe.pygame.Surface((cafe.SW, cafe.SH), cafe.pygame.SRCALPHA)
        customer.draw(surface, 10)
        customer.draw_meal(surface)
        self.assertEqual(before, (customer.x, customer.y, customer.facing, customer.timer))
        customer.timer = .01
        customer.update(.02, game)
        self.assertIsNone(customer.seat)
        self.assertEqual(customer.state, 'walk')

    def test_arm_lengths_and_rabbit_angle_are_fixed_in_both_directions(self):
        import math
        import small
        for facing in (-1, 1):
            for compact in (False, True):
                for frame in range(101):
                    shoulder, elbow, wrist = small._meal_arm(50, 30, facing, frame / 100, frame % 2, compact)
                    self.assertAlmostEqual(math.dist(shoulder, elbow), 3)
                    self.assertAlmostEqual(math.dist(elbow, wrist), 2.5)
            start = small._meal_arm(50, 30, facing, 0)
            end = small._meal_arm(50, 30, facing, 1)
            for index in (0, 1):
                def angle(pose):
                    a, b = pose[index:index + 2]
                    return math.atan2(b[1] - a[1], facing * (b[0] - a[0]))
                self.assertAlmostEqual(abs(math.degrees(angle(end) - angle(start))), 15)

    def test_all_guest_appearances_on_every_seat_and_render_density(self):
        import small
        import detail_render as dr
        game = fresh_game()
        cafe.pygame.display.set_mode((1, 1))
        furniture = next(f for f in cafe.FURN if f['id'] == 'tableL1')
        guests = []
        for species, variants in cafe.SPECIES.items():
            for variant in range(len(variants)):
                customer = self.customer(game, furniture)
                customer.species, customer.var = species, variant
                guests.append(customer)
        guests.extend(self.customer(game, furniture, kind='rare', name=name)
                      for name in cafe.specials.SPECIAL)
        for appearance in range(1, 12):
            customer = self.customer(game, furniture, kind='family', name='test')
            customer.appearance = appearance
            guests.append(customer)
        surface = dr.DetailSurface((cafe.SW, cafe.SH))
        for customer in guests:
            for table in (f for f in cafe.FURN if f.get('seats')):
                for index, seat in enumerate(table['seats']):
                    customer.seat = ((table['id'], index), seat)
                    customer.x, customer.y, customer.facing = seat[:3]
                    for elapsed in (0, .7, 7.7):
                        customer.timer = customer._meal_duration - elapsed
                        with self.subTest(kind=customer.kind, guest=customer.name or customer.species,
                                          table=table['id'], seat=index, elapsed=elapsed):
                            surface.fill((0, 0, 0, 0))
                            customer.draw(surface, elapsed)
                            customer.draw_meal(surface)
                            bounds = surface.get_bounding_rect()
                            self.assertTrue(bounds)
                            self.assertLessEqual(bounds.width, 48)
                            self.assertLessEqual(bounds.height, 48)
                            self.assertLess(abs(bounds.centerx - customer.sx), 20)
            # Verify registered native detail rather than just enlarging 1x pixels.
            customer.seat = ((furniture['id'], 0), furniture['seats'][0])
            customer.x, customer.y, customer.facing = furniture['seats'][0][:3]
            customer.timer = customer._meal_duration - .7
            surface.fill((0, 0, 0, 0))
            customer.draw(surface, 0)
            customer.draw_meal(surface)
            for density in (1, 2, 3):
                image = dr.scaled(surface, (cafe.SW * density, cafe.SH * density))
                self.assertEqual(image.get_size(), (cafe.SW * density, cafe.SH * density))

    def test_seated_sprite_preserves_sources_and_anchors_the_hips(self):
        import small
        import detail_render as dr
        cafe.pygame.display.set_mode((1, 1))
        sources = [cafe.specials.family_surf(appearance, 0, facing)
                   for appearance in range(1, 12) for facing in (-1, 1)]
        for source in sources:
            before = cafe.pygame.image.tobytes(source, 'RGBA')
            for bob in (0, 1):
                image, hip = small._seated_guest(source, 19, 7, 1, bob)
                self.assertEqual(hip, 26)
                for density in (1, 2, 3):
                    self.assertEqual(dr.detail(image, density).get_size(),
                                     (image.get_width() * density, image.get_height() * density))
            self.assertEqual(before, cafe.pygame.image.tobytes(source, 'RGBA'))


if __name__ == '__main__':
    if '--simulate' in sys.argv:
        simulate(int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 100)
    else:
        unittest.main()
