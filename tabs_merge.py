"""Merge the 꾸미기 (decor) tab into the 가구 tab.

Internal tab indexes stay untouched (the recovered code hardcodes them); tab 3 simply
is never shown or selectable, and its rows are appended to the furniture tab's list.
"""
DECOR_TAB = 3
FURN_TAB = 2


def install(cafe):
    if getattr(cafe, '_merged_tabs_installed', False):
        return
    cafe._merged_tabs_installed = True
    UI = cafe.UI
    original_rows, original_draw = UI.rows, UI.draw

    def rows(self):
        result = original_rows(self)
        if self.tab == FURN_TAB:
            result.append(dict(kind='hdr', name='꾸미기'))
            self.tab = DECOR_TAB
            try:
                result.extend(original_rows(self))
            finally:
                self.tab = FURN_TAB
        return result

    def draw(self, surface, mouse):
        if self.tab == DECOR_TAB:
            self.tab = FURN_TAB
        original_draw(self, surface, mouse)
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

    UI.rows, UI.draw = rows, draw
