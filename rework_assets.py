"""Normalize generated outfit masters and compare them with actual game sprites.

ImageGen creates the artwork. This script only crops, sizes, limits the palette,
and checks/exports the production PNGs; it does not draw replacement artwork.
"""
from pathlib import Path
import os
import argparse
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
GENERATED = Path(r'C:\Users\user\.codex\generated_images\01a15cdf-795a-7b00-985c-e189349ad3ca')
JOBS = [
    ('summer', 'outfit_1', ROOT / 'summer-outfit-preview.png'),
    ('summer', 'outfit_2', GENERATED / 'exec-84abd9e4-f76a-45bf-9d30-4168f895b1b0.png'),
    ('autumn', 'outfit_1', GENERATED / 'exec-bde5a144-ca07-4dd6-9daf-e3972f25b1c2.png'),
    ('autumn', 'outfit_2', GENERATED / 'exec-55037352-c945-4b53-a3f3-1de814d745d8.png'),
    ('winter', 'outfit_1', GENERATED / 'exec-1f617daa-7259-4edc-80fa-2ada9f23bdbe.png'),
    ('winter', 'outfit_2', GENERATED / 'exec-774917da-5fb3-49b9-b9fa-17e2e412c195.png'),
    ('golden', 'outfit_1', GENERATED / 'exec-ee94c5a5-5c34-49f0-808a-1b55598f7457.png'),
    ('golden', 'outfit_2', GENERATED / 'exec-ff964823-e159-4df7-838c-851dd5a8c6cc.png'),
]
HAIR_JOBS = [
    ('summer', GENERATED / 'exec-9f1ea447-75f7-461d-9fd2-5cf64b630ed4.png', (3, 0, 66, 57)),
    ('autumn', GENERATED / 'exec-5b9bb0d8-e67b-4265-b7a5-714720e6e894.png', (3, 0, 66, 78)),
    ('winter', GENERATED / 'exec-5714ee1b-232e-4ac7-be4d-5c2167bd8b69.png', (3, 0, 66, 60)),
    ('golden', GENERATED / 'exec-83b5fac1-0f01-4adb-b0bc-7a72f97c4947.png', (3, 0, 66, 74)),
]


def limited(image):
    image = image.convert('RGBA')
    alpha = image.getchannel('A').point(lambda a: 255 if a >= 128 else 0)
    # Transparent RGB must not use up the sprite's limited opaque palette.
    rgb = image.convert('RGB')
    colors = Image.new('RGB', (max(1, sum(a > 0 for a in alpha.getdata())), 1))
    colors.putdata([p for p, a in zip(rgb.getdata(), alpha.getdata()) if a])
    palette = colors.quantize(colors=19, method=Image.Quantize.MEDIANCUT)
    out = rgb.quantize(palette=palette, dither=Image.Dither.NONE).convert('RGBA')
    out.putalpha(alpha)
    out.paste((0, 0, 0, 0), mask=alpha.point(lambda a: 255-a))
    return out


def outfit(source, theme, part):
    image = Image.open(source).convert('RGBA')
    mask = image.getchannel('A').point(lambda a: 255 if a >= 128 else 0)
    box = mask.getbbox()
    if box is None:
        raise ValueError(f'Empty generation: {source}')
    # Fixed game coordinates, not source-image canvas proportions. The accepted
    # spring asset starts its neck at y52 and ends its shoes at y99.
    left, top, width, height = (12, 53, 48, 43)
    if (theme, part) == ('autumn', 'outfit_2'):
        left, width = 9, 54
    cut = image.crop(box).resize((width, height), Image.Resampling.BOX)
    out = Image.new('RGBA', (72, 102))
    out.paste(cut, (left, top))
    return limited(out)


def placed(source, box, canvas=(72, 102)):
    image = Image.open(source).convert('RGBA')
    bounds = image.getchannel('A').point(lambda a: 255 if a >= 128 else 0).getbbox()
    x, y, w, h = box
    out = Image.new('RGBA', canvas)
    out.paste(image.crop(bounds).resize((w, h), Image.Resampling.BOX), (x, y))
    return limited(out)


def variants(master):
    return {s: limited(master.resize((24*s, 34*s), Image.Resampling.BOX))
            for s in (1, 2, 3)}


def pillow(surface):
    import pygame
    return Image.frombytes('RGBA', surface.get_size(), pygame.image.tobytes(surface, 'RGBA'))


def compose(cafe, layer, scale):
    # Match themes.hero.compose order: body cleared, neck bridge, outfit,
    # then original head. Face/hair are never generated again.
    base = pillow(cafe.art.image('player/base/short') if scale == 1
                  else cafe.art.native_image('player/base/short', scale))
    head = base.copy()
    d = ImageDraw.Draw(base)
    d.rectangle((5*scale, 19*scale, 19*scale-1, 33*scale-1), fill=(0, 0, 0, 0))
    skin = head.getpixel((10*scale, 16*scale))
    d.rectangle((10*scale, 18*scale, 14*scale-1, 23*scale-1), fill=skin)
    base.alpha_composite(layer)
    base.alpha_composite(head.crop((0, 0, 24*scale, 19*scale)), (0, 0))
    return base


def validate(images, label):
    for s, im in images.items():
        assert im.size == (24*s, 34*s), (label, s, im.size)
        assert set(im.getchannel('A').getdata()) <= {0, 255}, (label, 'alpha')
        colors = {p[:3] for p in im.getdata() if p[3]}
        assert len(colors) <= 19, (label, len(colors))
    print(label, '3x bbox', images[3].getbbox(), 'colors', len({p for p in images[3].getdata() if p[3]}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import pygame
    pygame.init()
    pygame.display.set_mode((1, 1))
    import PixelCafe as cafe
    rows = []
    hair = cafe.HERO['hair'][0]['v']
    for key in ('top1', 'top2', 'top4', 'top7', 'top8', 'top9'):
        top = cafe.HERO_BY_ID[key][1]['v']
        base = cafe.hero_surf(hair, top, 'none', 0, 1)
        rows.append((key+' existing '+top[0],
                     {s: pillow(base if s == 1 else cafe.art.dr.detail(base, s)) for s in (1, 2, 3)}, None))
    for theme, part, source in JOBS:
        images = variants(outfit(source, theme, part))
        validate(images, theme+'/'+part)
        composed = {s: compose(cafe, image, s) for s, image in images.items()}
        rows.append((theme+'/'+part+' candidate', composed, images[3]))
        if args.apply:
            folder = ROOT / 'assets' / 'themes' / theme / 'native'
            for s, image in images.items():
                image.save(folder / (part + ('' if s == 1 else f'@{s}x') + '.png'))
    for theme, source, box in HAIR_JOBS:
        images = variants(placed(source, box))
        validate(images, theme+'/hair')
        if args.apply:
            folder = ROOT / 'assets' / 'themes' / theme / 'native'
            for s, image in images.items():
                image.save(folder / ('hair' + ('' if s == 1 else f'@{s}x') + '.png'))
    sheet = Image.new('RGB', (1050, 65+len(rows)*160), '#e4ddcd')
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 10), 'Actual game size check | all zooms use nearest-neighbour', fill='#422c20')
    draw.text((280, 35), '1x actual', fill='#422c20')
    draw.text((350, 35), '2x actual', fill='#422c20')
    draw.text((440, 35), '3x actual', fill='#422c20')
    draw.text((570, 35), 'Same character at 4x logical zoom', fill='#422c20')
    draw.text((840, 35), 'Outfit at 2x zoom of 3x PNG', fill='#422c20')
    for i, (label, images, layer) in enumerate(rows):
        y = 65+i*160
        draw.line((0, y, 1050, y), fill='#b9ac98')
        draw.text((12, y+62), label, fill='#422c20')
        for s, x in ((1, 280), (2, 350), (3, 440)):
            im = images[s]
            sheet.paste(im, (x, y+142-im.height), im)
        zoom = images[3].resize((96, 136), Image.Resampling.NEAREST)
        sheet.paste(zoom, (620, y+6), zoom)
        if layer:
            zoom = layer.crop((0, 49, 72, 102)).resize((144, 106), Image.Resampling.NEAREST)
            sheet.paste(zoom, (850, y+35), zoom)
    sheet.save(ROOT / 'outfit-size-check.png')
    print('Saved outfit-size-check.png; apply:', args.apply)


if __name__ == '__main__':
    main()
