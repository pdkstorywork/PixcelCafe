"""Run with Python 3.13: python -m unittest test_game_data -v.

Real game integration uses dummy SDL and isolated saves; player saves are untouched.
"""
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import game_data as data


def load_game(name):
    module = types.ModuleType(name)
    module.__file__ = str(Path(__file__).with_name('PixelCafe.py'))
    sys.modules[name] = module
    exec(compile(Path(module.__file__).read_text(encoding='utf-8'), module.__file__, 'exec'),
         module.__dict__)
    return module


class CollectionRulesTests(unittest.TestCase):
    def test_missing_entries_get_four_times_base_weight(self):
        rng = random.Random(42)
        results = [data.choose_collectible(['owned', 'missing'], {'owned'}, {}, 'rare', rng=rng)
                   for _ in range(10000)]
        rate = results.count('missing') / len(results)
        self.assertGreater(rate, .78)
        self.assertLess(rate, .82)

    def test_duplicate_limit_and_reset_only_on_acquisition(self):
        pity = {}
        for _ in range(data.DUPLICATE_LIMIT):
            data.record_discovery(pity, 'rare', False)
        self.assertEqual(data.choose_collectible(['old', 'new'], {'old'}, pity, 'rare'), 'new')
        self.assertEqual(pity['rare'], data.DUPLICATE_LIMIT)
        data.record_discovery(pity, 'rare', True)
        self.assertEqual(pity['rare'], 0)

    def test_completed_and_single_entry_pools_still_work(self):
        for discovered in (set(), {'only'}):
            self.assertEqual(data.choose_collectible(['only'], discovered,
                             {'rare': data.DUPLICATE_LIMIT}, 'rare'), 'only')

    def test_pool_counters_do_not_leak_between_tiers_and_variants(self):
        self.assertEqual(data.normalize_pity({'rare': 999, 'legend': -1, 'normal': True,
                         'variant:gold': 2, 'variant:missing': 3, 'other': 4}),
                         {'rare': data.DUPLICATE_LIMIT, 'legend': 0, 'variant:gold': 2})

    def test_base_weights_are_preserved_without_missing_entries(self):
        rng = random.Random(123)
        results = [data.choose_collectible(['a', 'b'], {'a', 'b'}, {'normal': 5},
                                          'normal', weights=[1, 3], rng=rng)
                   for _ in range(10000)]
        self.assertAlmostEqual(results.count('b') / len(results), .75, delta=.02)


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='data-test-', dir=Path(__file__).parent)
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'save.json'

    def test_legacy_save_reads_without_rewrite(self):
        self.path.write_text('{"money": 321}', encoding='utf-8')
        before = self.path.read_bytes()
        self.assertEqual(data.read_save(self.path), {'money': 321})
        self.assertEqual(self.path.read_bytes(), before)

    def test_current_schema_round_trip_and_invalid_write_keeps_save(self):
        data.write_save(self.path, {'money': 321, 'pity': {'rare': 3}})
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            data.write_save(self.path, {'money': float('nan')})
        self.assertEqual(self.path.read_bytes(), before)
        loaded = data.read_save(self.path)
        self.assertEqual(loaded['schema_version'], data.SAVE_SCHEMA_VERSION)
        self.assertEqual(loaded['pity'], {'rare': 3})
        self.assertFalse(self.path.with_name('save.json.tmp').exists())

    def test_failed_replace_preserves_previous_file(self):
        data.write_save(self.path, {'money': 321})
        before = self.path.read_bytes()
        with patch.object(data.os, 'replace', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                data.write_save(self.path, {'money': 999})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.path.with_name('save.json.tmp').exists())

    def test_future_schema_is_not_loaded_as_a_new_game(self):
        self.path.write_text('{"schema_version": 999, "money": 321}', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            data.read_save(self.path)


class GameIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix='game-data-test-', dir=Path(__file__).parent)
        cls.addClassCleanup(cls.folder.cleanup)
        cls.environment = patch.dict(os.environ, APPDATA=cls.folder.name,
                                     SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
        cls.environment.start()
        cls.addClassCleanup(cls.environment.stop)
        cls.game = load_game('game_data_test_runtime')
        cls.game.pygame.init()
        cls.addClassCleanup(cls.game.pygame.quit)
        cls.game.pygame.display.set_mode((1280, 860))
        cls.game.build_sprites()

    def setUp(self):
        self.g = self.game.Game()

    def test_all_shipped_catalog_counts_and_ids_are_preserved(self):
        self.assertEqual(len(self.game.RECIPES), 50)
        self.assertEqual(len(self.game.FURN_BY_ID), 42)
        self.assertEqual(len(self.game.INT_BY_ID), 48)
        self.assertEqual(len(self.game.HERO_BY_ID), 46)
        for theme, mapping in data.THEME_ITEM_IDS.items():
            for part, ident in mapping.items():
                if part in ('wall', 'floor', 'sign', 'light'):
                    item = self.game.INT_BY_ID[ident][1]
                    self.assertTrue(item['themed'])
                else:
                    value = self.game.HERO_BY_ID[ident][1]['v']
                    tag = value if isinstance(value, str) else value[0]
                    self.assertEqual(tag, f'T:{theme}:{part}')

    def test_missing_assets_and_reordered_themes_do_not_renumber_items(self):
        import themes
        original = Path.is_file
        def exists(path):
            return False if path.as_posix().endswith('/spring/native/outfit_1.png') else original(path)
        with patch.object(themes, 'THEMES', tuple(reversed(themes.THEMES))), patch.object(Path, 'is_file', exists):
            other = load_game('game_data_test_missing_asset')
        self.assertNotIn('top8', other.HERO_BY_ID)
        self.assertEqual(other.HERO_BY_ID['top9'][1]['v'][0], 'T:spring:outfit_2')
        self.assertEqual(other.HERO_BY_ID['top10'][1]['v'][0], 'T:summer:outfit_1')
        self.assertEqual(other.HERO_BY_ID['top17'][1]['v'][0], 'T:golden:outfit_2')

    def test_existing_ownership_and_collection_survive_legacy_load(self):
        self.g.money = 1234
        self.g.rlv['garlic'] = 2
        self.g.hero_own.add('top17')
        self.g.hero_eq['top'] = 'top17'
        self.g.col['guests']['kitty'] = dict(v=8, lv=3, gift=2)
        self.g.col['variants']['bread'] = {'gold': 2}
        self.g.save()
        for name in ('save.json', 'collection.json', 'themes.json'):
            path = Path(self.game.SAVE_DIR) / name
            payload = json.loads(path.read_text(encoding='utf-8'))
            payload.pop('schema_version', None)
            payload.pop('pity', None)
            path.write_text(json.dumps(payload), encoding='utf-8')
        other = self.game.Game()
        other.load()
        self.assertEqual(other.money, 1234)
        self.assertEqual(other.rlv['garlic'], 2)
        self.assertIn('top17', other.hero_own)
        self.assertEqual(other.hero_eq['top'], 'top17')
        self.assertEqual(other.col['guests']['kitty'], dict(v=8, lv=3, gift=2))
        self.assertEqual(other.col['variants']['bread'], {'gold': 2})
        self.assertEqual(other.col['pity'], {})

    def test_rare_spawn_uses_protection_but_only_payment_registers_discovery(self):
        import collection
        rare = [k for k in self.game.specials.SPECIAL if k not in data.LEGEND]
        missing = rare[-1]
        self.g.col['guests'] = {k: dict(v=1, lv=1, gift=0) for k in rare[:-1]}
        self.g.col['pity']['rare'] = data.DUPLICATE_LIMIT
        with patch.object(collection.random, 'random', return_value=.05):
            self.g.spawn_customer([('pay',)])
        customer = self.g.customers[-1]
        self.assertEqual(customer.name, missing)
        self.assertNotIn(missing, self.g.col['guests'])
        self.assertEqual(self.g.col['pity']['rare'], data.DUPLICATE_LIMIT)
        customer.cart = ['bread']
        self.g.customer_paid(customer)
        self.assertEqual(self.g.col['guests'][missing]['v'], 1)
        self.assertEqual(self.g.col['pity']['rare'], 0)
        self.g.customer_paid(customer)
        self.assertEqual(self.g.col['guests'][missing]['v'], 1)

    def test_tier_roll_boundaries_are_unchanged_even_with_protection(self):
        import collection
        for roll, tier in ((.001, 'legend'), (.003, 'family'), (.045, 'rare'), (.2, 'normal')):
            with self.subTest(tier=tier):
                self.g.col['pity'] = {key: data.DUPLICATE_LIMIT for key in data.PITY_POOLS}
                with patch.object(collection.random, 'random', return_value=roll):
                    self.g.spawn_customer([('pay',)])
                customer = self.g.customers[-1]
                self.assertEqual(getattr(customer, 'tier', 'normal'), tier)
                if tier == 'legend':
                    self.assertIn(customer.name, data.LEGEND)
                if tier == 'family':
                    self.assertEqual(customer.occ, collection.occasion())

    def test_variant_occurrence_boundaries_are_unchanged(self):
        import collection
        for roll, variant in ((.0005, 'rainbow'), (.002, 'gold'), (.01, 'choco'),
                              (.03, 'strawberry'), (.1, None)):
            with self.subTest(variant=variant):
                game = self.game.Game()
                game.col['pity'] = {key: data.DUPLICATE_LIMIT for key in data.PITY_POOLS}
                customer = self.game.Customer(game, [('pay',)])
                customer.cart = ['bread']
                with patch.object(collection.random, 'random', return_value=roll):
                    game.customer_paid(customer)
                self.assertEqual(set(game.col['variants'].get('bread', {})),
                                 {variant} if variant else set())

    def test_normal_guest_protection_uses_valid_species_and_appearance(self):
        import collection
        keys = [f'n_{sp}_{v}' for sp, looks in self.game.SPECIES.items() for v in range(len(looks))]
        missing = keys[0]
        self.g.col['guests'] = {key: dict(v=1, lv=0, gift=0) for key in keys[1:]}
        self.g.col['pity']['normal'] = data.DUPLICATE_LIMIT
        with patch.object(collection.random, 'random', return_value=.9):
            self.g.spawn_customer([('pay',)])
        customer = self.g.customers[-1]
        self.assertEqual(f'n_{customer.species}_{customer.var}', missing)
        customer.cart = ['bread']
        self.g.customer_paid(customer)
        self.assertEqual(self.g.col['pity']['normal'], 0)
        self.assertEqual(self.g.col['guests'][missing]['v'], 1)

    def test_variant_protection_only_uses_unlocked_breads_and_persists(self):
        import collection
        self.g.rlv['garlic'] = 1
        self.g.col['variants']['bread'] = {'rainbow': 2}
        self.g.col['pity']['variant:rainbow'] = data.DUPLICATE_LIMIT
        customer = self.game.Customer(self.g, [('pay',)])
        customer.cart = ['bread']
        with patch.object(collection.random, 'random', return_value=0.0):
            self.g.customer_paid(customer)
        self.assertEqual(self.g.col['variants']['garlic']['rainbow'], 1)
        self.assertEqual(self.g.col['pity']['variant:rainbow'], 0)
        self.g.col['pity']['rare'] = 4
        self.g.save()
        other = self.game.Game()
        other.load()
        self.assertEqual(other.col['pity']['rare'], 4)
        self.assertEqual(other.col['variants']['garlic']['rainbow'], 1)


if __name__ == '__main__':
    unittest.main()
