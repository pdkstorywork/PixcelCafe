"""Persistent data rules shared by progression, collection and theme catalogs.

Keep saved IDs permanent. Missing art must never renumber another item.
Schema 0 is the original unversioned JSON; schema 1 adds duplicate protection.
"""
import json
import os
from pathlib import Path
import random

SAVE_SCHEMA_VERSION = 1

# Tier occurrence and variant occurrence rates stay independent of duplicate
# protection: this only changes which eligible entry fills an existing roll.
LEGEND_P, RARE_P, FAMILY_P = 0.001, 0.05, 0.03
LEGEND_MULT, RARE_MULT, FAMILY_MULT = 3, 2, 4
LEGEND = ('hachiware', 'chiikawa', 'usagi')
STEPS = (1, 5, 15, 30)
FRIEND_BONUS, VARIANT_BONUS = 0.002, 0.0005
DROP_P = {'rare': 0.06, 'family': 0.04, 'legend': 0.25}
DROP_MULT = 2
VARIANTS = (
    ('rainbow', '무지개', 0.0015, 8.0), ('gold', '황금', 0.004, 3.0),
    ('choco', '초코', 0.012, 1.6), ('strawberry', '딸기', 0.03, 1.3),
)
MATE_RULES = {'normal': (0.001, 0, 50, 0), 'rare': (0.004, 4, 250, 0),
              'family': (0.010, 3, 350, 0), 'legend': (0.030, 1, 1200, 8)}
MATE_MAX_LV, MATE_LV_BONUS = 10, 0.1
ACH_SUB, ACH_CAT, ACH_ALL = (0.005, 20), (0.010, 60), (0.030, 200)

UNSEEN_WEIGHT = 4
DUPLICATE_LIMIT = 5
GUEST_POOLS = ('normal', 'rare', 'legend', 'family_name', 'family_look')
PITY_POOLS = (*GUEST_POOLS, *(f'variant:{v[0]}' for v in VARIANTS))

# IDs in the shipped complete 1.0.0 catalog. Append explicit IDs for new packs;
# never derive them from the number/order of available PNGs or base shop items.
_THEME_IDS = {
    'spring': ('wall6', 'floor6', 'sign5', 'light5', 'hair8', 'top8', 'top9', 'acc8', 'acc9'),
    'summer': ('wall7', 'floor7', 'sign6', 'light6', 'hair9', 'top10', 'top11', 'acc10', 'acc11'),
    'autumn': ('wall8', 'floor8', 'sign7', 'light7', 'hair10', 'top12', 'top13', 'acc12', 'acc13'),
    'winter': ('wall9', 'floor9', 'sign8', 'light8', 'hair11', 'top14', 'top15', 'acc14', 'acc15'),
    'golden': ('wall10', 'floor10', 'sign9', 'light9', 'hair12', 'top16', 'top17', 'acc16', 'acc17'),
}
_NUMBERED_PARTS = ('wall', 'floor', 'sign', 'light', 'hair', 'outfit_1',
                   'outfit_2', 'accessory_1', 'accessory_2')
THEME_ITEM_IDS = {theme: dict(zip(_NUMBERED_PARTS, ids)) for theme, ids in _THEME_IDS.items()}


def read_save(path):
    """Read legacy/current saves without changing them; never downgrade a future save."""
    try:
        with open(path, encoding='utf-8') as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    version = data.get('schema_version', 0)
    if isinstance(version, int) and version > SAVE_SCHEMA_VERSION:
        raise RuntimeError('이 저장 파일은 더 새로운 게임 버전에서 만들어졌습니다. 게임을 업데이트해 주세요.')
    return data


def write_save(path, data):
    """Serialize before touching disk, then atomically replace one save file."""
    payload = dict(data, schema_version=SAVE_SCHEMA_VERSION)
    content = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    try:
        with open(temporary, 'w', encoding='utf-8') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def normalize_pity(value):
    if not isinstance(value, dict):
        return {}
    return {key: min(DUPLICATE_LIMIT, max(0, number))
            for key, number in value.items()
            if key in PITY_POOLS and type(number) is int}


def choose_collectible(candidates, discovered, pity, pool, *, weights=None, rng=random):
    """Boost unseen entries; after five completed duplicates, prefer an unseen one.

    Discovery/counter updates happen on acquisition, not spawn. A guest who never
    pays therefore cannot consume discovery protection. No occurrence rates change.
    Optional base weights preserve the original distribution (e.g. animal species).
    """
    candidates = list(candidates)
    if not candidates:
        raise ValueError('An eligible collection pool must not be empty')
    weights = list(weights) if weights is not None else [1.0] * len(candidates)
    unseen = [i for i, key in enumerate(candidates) if key not in discovered]
    if unseen and pity.get(pool, 0) >= DUPLICATE_LIMIT:
        return rng.choices([candidates[i] for i in unseen],
                           weights=[weights[i] for i in unseen], k=1)[0]
    missing = set(unseen)
    return rng.choices(candidates, weights=[weight * (UNSEEN_WEIGHT if i in missing else 1)
                                          for i, weight in enumerate(weights)], k=1)[0]


def record_discovery(pity, pool, first):
    pity[pool] = 0 if first else min(DUPLICATE_LIMIT, pity.get(pool, 0) + 1)
