"""Headless balance regressions; --simulate runs a 300-day economy forecast.

The forecast uses real plans, payments, collection rolls and shop methods, but
skips walking and seating. The default 100 arrivals/hour matches a measured
late-game live loop (101/hour). Pass an arrival rate to explore other traffic.
This is a forecast, not a promise about each player's completion date.
Never reads or writes player saves.
"""
import datetime
import os
import random
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import PixelCafe as cafe
import collection
import game_data
import progression


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


if __name__ == '__main__':
    if '--simulate' in sys.argv:
        simulate(int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 100)
    else:
        unittest.main()
