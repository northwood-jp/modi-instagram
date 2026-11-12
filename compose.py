"""MoDi Instagram：下書きを読み取って、誌面風の画像を作る"""
import io, json, os, re, datetime
from collections import deque
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

GAS_URL = os.environ.get('GAS_URL', '')
GAS_TOKEN = os.environ.get('GAS_TOKEN', '')
W, H = 1080, 1350
FONT_DIR = '/usr/share/fonts/opentype/noto/'
SANS_R = FONT_DIR + 'NotoSansCJK-Regular.ttc'
SANS_B = FONT_DIR + 'NotoSansCJK-Bold.ttc'
SERIF_B = FONT_DIR + 'NotoSerifCJK-Bold.ttc'
CREAM, INK, GRAY, OLIVE = (241, 236, 224), (30, 30, 25), (80, 80, 70), (62, 66, 44)


def font(path, size):
    return ImageFont.truetype(path, size, index=0)


def wrap_ja(text, n):
    """日本語をおよそn文字ずつで折り返す（句読点が行頭に来ないようにする）"""
    lines, cur = [], ''
    for ch in str(text):
        cur += ch
        if len(cur) >= n:
            lines.append(cur)
            cur = ''
    if cur:
        lines.append(cur)
    for i in range(1, len(lines)):
        while lines[i] and lines[i][0] in '、。」）・ー':
            lines[i - 1] += lines[i][0]
            lines[i] = lines[i][1:]
    return [l for l in lines if l]


def fetch(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content)).convert('RGB')
    im.thumbnail((900, 900))
    return im


def cutout(im, thr=232):
    """写真のまわりの白い背景を切り抜く（ふちから続く白い部分だけを消す）"""
    a = np.asarray(im).astype(int)
    white = a.min(axis=2) > thr
    h, w = white.shape
    bg = np.zeros_like(white)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if white[y, x] and not bg[y, x]:
                bg[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if white[y, x] and not bg[y, x]:
                bg[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and white[ny, nx] and not bg[ny, nx]:
                bg[ny, nx] = True; q.append((ny, nx))
    alpha = Image.fromarray(((~bg) * 255).astype('uint8'))
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1))
    rgba = im.convert('RGBA')
    rgba.putalpha(alpha)
    box = alpha.getbbox()
    return rgba.crop(box) if box else rgba


def place(canvas, img, box, rot=0):
    x0, y0, x1, y1 = box
    s = min((x1 - x0) / img.width, (y1 - y0) / img.height)
    i = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
    i = i.rotate(rot, expand=True, resample=Image.BICUBIC)
    a = i.split()[3].point(lambda v: int(v * 0.25))
    shadow = Image.merge('RGBA', (Image.new('L', i.size, 40),) * 3 + (a,)).filter(ImageFilter.GaussianBlur(8))
    x = x0 + ((x1 - x0) - i.width) // 2
    y = y0 + ((y1 - y0) - i.height) // 2
    canvas.paste(shadow, (x + 6, y + 10), shadow)
    canvas.paste(i, (x, y), i)


def short(name):
    """表示用に、説明語を除いて短くする"""
    return re.sub(r'\s+', ' ', re.sub(r'(デッドストック|レプリカ|放出|未使用)', '', str(name))).strip()[:16]


def caption(d, x, y, p, align='l'):
    anchor = 'la' if align == 'l' else 'ra'
    name = short(p['name'])
    d.text((x, y), name, font=font(SANS_B, 22), fill=INK, anchor=anchor)
    d.text((x, y + 32), p.get('sub', ''), font=font(SANS_R, 18), fill=GRAY, anchor=anchor)
    d.text((x, y + 58), '¥{:,}'.format(int(p.get('price') or 0)), font=font(SANS_B, 20), fill=INK, anchor=anchor)


def cover(draft, no):
    im = Image.new('RGB', (W, H), CREAM)
    d = ImageDraw.Draw(im)
    d.text((60, 55), 'MoDi', font=font(SANS_B, 40), fill=INK)
    d.text((190, 72), 'COORDINATE ARCHIVE  No.{:02d}'.format(no), font=font(SANS_R, 20), fill=GRAY)
    d.line([60, 120, 1020, 120], fill=INK, width=2)
    d.text((1020, 150), draft.get('headline1', ''), font=font(SERIF_B, 52), fill=INK, anchor='ra')
    d.text((1020, 215), draft.get('headline2', ''), font=font(SERIF_B, 52), fill=INK, anchor='ra')
    d.text((1020, 290), draft.get('sub', ''), font=font(SANS_R, 20), fill=GRAY, anchor='ra')
    roles = {p['role']: p for p in draft['products']}
    has_bag = '小物' in roles
    layout = {
        '主役': ((50, 150, 560, 760), 3, (70, 770, 'l')),
        'ボトムス': ((600, 340, 1020, 1080), -4, (1020, 1090, 'r')),
        '小物': ((60, 880, 420, 1150), -6, (70, 1160, 'l')),
        'シューズ': (((440, 990, 760, 1180), 8, (470, 1195, 'l')) if has_bag
                  else ((90, 900, 520, 1160), 8, (110, 1180, 'l'))),
    }
    for role, (box, rot, (cx, cy, al)) in layout.items():
        p = roles.get(role)
        if not p:
            continue
        try:
            place(im, cutout(fetch(p['img'])), box, rot)
        except Exception as e:
            print('写真の取得に失敗:', p.get('img'), e)
        caption(d, cx, cy, p, al)
    d.line([60, 1295, 1020, 1295], fill=INK, width=1)
    d.text((60, 1305), 'MILITARY ARCHIVE CURATION STORE', font=font(SANS_R, 16), fill=GRAY)
    d.text((1020, 1305), 'modi.northwood-jp.com', font=font(SANS_R, 16), fill=GRAY, anchor='ra')
    return im


def page(draft, pg, idx, total, no):
    im = Image.new('RGB', (W, H), OLIVE)
    d = ImageDraw.Draw(im)
    rng = np.random.default_rng(idx)
    noise = rng.normal(0, 6, (H, W, 1))
    im = Image.fromarray(np.clip(np.asarray(im).astype(float) + noise, 0, 255).astype('uint8'))
    d = ImageDraw.Draw(im)
    tx, ty, tw, th = 80, 90, 920, 1170
    d.rectangle([tx + 10, ty + 10, tx + tw + 10, ty + th + 10], fill=(40, 42, 28))
    d.rectangle([tx, ty, tx + tw, ty + th], fill=(236, 230, 214))
    d.rectangle([tx + 16, ty + 16, tx + tw - 16, ty + th - 16], outline=(60, 60, 50), width=2)
    hero = short(draft['products'][0]['name'])
    d.text((tx + 50, ty + 50), 'MoDi 名作図鑑｜' + hero, font=font(SANS_R, 28), fill=(60, 60, 50))
    d.text((tx + tw - 50, ty + 50), '{}/{}'.format(idx, total), font=font(SANS_R, 28), fill=(60, 60, 50), anchor='ra')
    d.line([tx + 50, ty + 100, tx + tw - 50, ty + 100], fill=(60, 60, 50), width=2)
    y = ty + 160
    for ln in wrap_ja(pg.get('title', ''), 14):
        d.text((tx + 60, y), ln, font=font(SERIF_B, 56), fill=(25, 25, 20)); y += 76
    y += 50
    for ln in wrap_ja(pg.get('body', ''), 19):
        d.text((tx + 60, y), ln, font=font(SANS_R, 40), fill=(40, 40, 32)); y += 66
    d.line([tx + 50, ty + th - 110, tx + tw - 50, ty + th - 110], fill=(60, 60, 50), width=2)
    d.text((W // 2, ty + th - 85), 'MILITARY ARCHIVE CURATION STORE  ―  memento mori & carpe diem.',
           font=font(SANS_R, 22), fill=(60, 60, 50), anchor='ma')
    return im


def main():
    r = requests.get(GAS_URL, params={'mode': 'igdrafts', 'token': GAS_TOKEN}, timeout=60)
    drafts = r.json().get('drafts', [])
    print('画像待ちの下書き：', len(drafts), '件')
    manifest = []
    for dft in drafts:
        stamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
        folder = 'images/r{}_{}'.format(dft['row'], stamp)
        os.makedirs(folder, exist_ok=True)
        files = []
        total = 1 + len(dft.get('pages', []))
        img = cover(dft, dft['row'] - 1)
        path = folder + '/1.jpg'; img.save(path, 'JPEG', quality=92); files.append(path)
        for i, pg in enumerate(dft.get('pages', []), start=2):
            img = page(dft, pg, i, total, dft['row'] - 1)
            path = folder + '/{}.jpg'.format(i); img.save(path, 'JPEG', quality=92); files.append(path)
        manifest.append({'row': dft['row'], 'files': files})
        print('作成：', folder)
    with open('manifest.json', 'w') as f:
        json.dump(manifest, f, ensure_ascii=False)


if __name__ == '__main__':
    main()
