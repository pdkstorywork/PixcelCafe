# Python 3.13 launcher for code recovered from PixelCafe.exe.
# The original editable source was deleted; PixelCafe.pyc contains compiled code.
if __name__ == '__main__':
    from game_updater import check_for_updates
    check_for_updates()

from pathlib import Path as _Path
import importlib.util as _importlib_util
import marshal as _marshal

_payload = _Path(__file__).with_suffix(".pyc").read_bytes()
if _payload[:4] != _importlib_util.MAGIC_NUMBER:
    raise RuntimeError("This recovered game requires Python 3.13.")
_code = _marshal.loads(_payload[16:])
# Install editable growth rules before starting the recovered game's main loop.
_NO_BUY_PREFIX = ('해금 ', '채용 ', '승급 ')


def _patch_consts(code, top=False):
    # Rows whose label already starts with an action word skip the "구매 " prefix; add 영입 to that list.
    consts = []
    for value in code.co_consts:
        if value == _NO_BUY_PREFIX:
            value = _NO_BUY_PREFIX + ('영입 ',)
        elif top and isinstance(value, str) and value == '__main__':
            value = '__recovered_entry_disabled__'
        elif hasattr(value, 'co_consts'):
            value = _patch_consts(value)
        consts.append(value)
    return code.replace(co_consts=tuple(consts))


_code = _patch_consts(_code, top=True)
exec(_code, globals())
import progression as _progression
_progression.install(sys.modules[__name__])
import small
import mini
small.install_window_art(sys.modules[__name__])
small.install_recipe_book(sys.modules[__name__])
small.install_ui_performance(sys.modules[__name__])
small.install_staff_art(sys.modules[__name__])
import collection as _collection
_collection.install(sys.modules[__name__])
small.install_rare_dialog(sys.modules[__name__])
small.install_customer_facing(sys.modules[__name__])
small.install_customer_eating(sys.modules[__name__])
import themes as _themes
_themes.install(sys.modules[__name__])
mini.install_mini_bar(sys.modules[__name__])
mini.install_mini_view(sys.modules[__name__])
mini.install_mini_window(sys.modules[__name__])
mini.install_monitor2(sys.modules[__name__])
mini.install_merged_tabs(sys.modules[__name__])
mini.install_smooth_scroll(sys.modules[__name__])
try:
    # pygame's default window icon (yellow creature with a gamepad) otherwise shows in the taskbar.
    _icon_base = getattr(sys, '_MEIPASS', None) or str(_Path(__file__).resolve().parent)
    import io as _io
    _ico = (_Path(_icon_base) / 'assets' / 'PixelCafe.ico').read_bytes()
    _size, _offset = int.from_bytes(_ico[14:18], 'little'), int.from_bytes(_ico[18:22], 'little')
    pygame.display.set_icon(pygame.image.load(_io.BytesIO(_ico[_offset:_offset + _size]), 'icon.png'))
except Exception:
    pass
if __name__ == '__main__':
    main()
