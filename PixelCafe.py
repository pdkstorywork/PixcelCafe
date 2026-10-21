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
_code = _code.replace(co_consts=tuple(
    '__recovered_entry_disabled__' if isinstance(value, str) and value == '__main__' else value
    for value in _code.co_consts))
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
import themes as _themes
_themes.install(sys.modules[__name__])
mini.install_mini_bar(sys.modules[__name__])
mini.install_mini_view(sys.modules[__name__])
mini.install_mini_window(sys.modules[__name__])
mini.install_monitor2(sys.modules[__name__])
import tabs_merge as _tabs_merge
_tabs_merge.install(sys.modules[__name__])
if __name__ == '__main__':
    main()
