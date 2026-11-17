"""MoDi Instagram：下書きを読み取って、誌面風の画像を作る（表紙＋1点ずつのアーカイブカード）"""
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
CREAM, INK, GRAY, OLIVE = (244, 240, 230), (25, 25, 22), (80, 80, 70), (62, 66, 44)
TAN = (214, 204, 178)
NUM = '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf'
if not os.path.exists(NUM):
    NUM = SANS_B


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
    im.thumbnail((1400, 1400))
    return im



def wrap_px(d, text, f, maxw):
    """横幅（ピクセル）で折り返す。句読点が行頭に来ないようにする"""
    lines, cur = [], ''
    for ch in str(text):
        if d.textlength(cur + ch, font=f) > maxw and cur and ch not in '、。」）・ー':
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def edge_color(im):
    """写真の縁の色（台紙の色に使う）"""
    a = np.asarray(im.convert('RGB')).astype(int)
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return tuple(int(x) for x in np.median(edge, axis=0))


def fit(im, w, h):
    r = min(w / im.width, h / im.height)
    return im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)


def fill(im, w, h):
    r = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, max(0, (im.height - h) // 3)
    return im.crop((x, y, x + w, y + h))


def cover(draft, no):
    """表紙：主役の写真を全面に敷いて、キャッチコピーを大きく"""
    p0 = draft['products'][0]
    try:
        im = fill(fetch(p0['img']), W, H)
    except Exception as e:
        print('写真の取得に失敗:', e)
        im = Image.new('RGB', (W, H), OLIVE)
    g = np.linspace(0.15, 0.7, H)[:, None, None]
    im = Image.fromarray((np.asarray(im).astype(float) * (1 - g)).clip(0, 255).astype('uint8'))
    d = ImageDraw.Draw(im)
    d.text((60, 55), 'MoDi', font=font(SANS_B, 40), fill='white')
    d.text((1020, 70), 'ARCHIVE FILE  No.{:02d}'.format(no), font=font(SANS_R, 22), fill='white', anchor='ra')
    f = font(SANS_B, 92)
    y = 720
    for t in (draft.get('headline1', ''), draft.get('headline2', '')):
        if not t:
            continue
        d.text((W // 2 + 3, y + 3), t, font=f, fill=(0, 0, 0), anchor='ma')
        d.text((W // 2, y), t, font=f, fill='white', anchor='ma')
        y += 122
    chip = p0.get('theme', 'PICK UP')
    cf = font(SANS_B, 32)
    cw = d.textlength(chip, font=cf) + 60
    d.rectangle([W // 2 - cw / 2, y + 20, W // 2 + cw / 2, y + 80], fill=OLIVE)
    d.text((W // 2, y + 50), chip, font=cf, fill=CREAM, anchor='mm')
    d.text((W // 2, y + 118), draft.get('sub', ''), font=font(SANS_R, 30), fill='white', anchor='ma')
    d.text((W // 2, H - 60), 'MILITARY ARCHIVE CURATION STORE', font=font(SANS_R, 18), fill=(220, 220, 210), anchor='ma')
    return im


def item(p, idx, total):
    """2枚目以降：1点ずつのアーカイブカード"""
    im = Image.new('RGB', (W, H), CREAM)
    d = ImageDraw.Draw(im)
    d.text((60, 50), 'MoDi ARCHIVE FILE', font=font(SANS_B, 24), fill=OLIVE)
    d.text((1020, 50), '{}　{}/{}'.format(p.get('theme', ''), idx, total), font=font(SANS_R, 24), fill=(110, 110, 95), anchor='ra')
    d.line([60, 92, 1020, 92], fill=OLIVE, width=2)
    bx0, by0, bx1, by1 = 60, 120, 1020, 860
    try:
        photo = fetch(p['img'])
        d.rectangle([bx0, by0, bx1, by1], fill=edge_color(photo))
        ph = fit(photo, bx1 - bx0 - 120, by1 - by0 - 80)
        im.paste(ph, (bx0 + (bx1 - bx0 - ph.width) // 2, by0 + (by1 - by0 - ph.height) // 2))
    except Exception as e:
        print('写真の取得に失敗:', p.get('img'), e)
        d.rectangle([bx0, by0, bx1, by1], fill=(232, 226, 210))
    d = ImageDraw.Draw(im)
    for (x, y, sx, sy) in [(bx0, by0, 1, 1), (bx1, by0, -1, 1), (bx0, by1, 1, -1), (bx1, by1, -1, -1)]:
        d.line([x + sx * 14, y + sy * 14, x + sx * 64, y + sy * 14], fill=OLIVE, width=4)
        d.line([x + sx * 14, y + sy * 14, x + sx * 14, y + sy * 64], fill=OLIVE, width=4)
    tx, ty = 60, 810
    d.rectangle([tx, ty, tx + 250, ty + 96], fill=OLIVE)
    d.ellipse([tx + 18, ty + 36, tx + 42, ty + 60], fill=CREAM)
    d.text((tx + 60, ty + 12), 'ITEM', font=font(SANS_B, 20), fill=TAN)
    d.text((tx + 60, ty + 30), 'No.{:02d}'.format(idx - 1), font=font(NUM, 54), fill=CREAM)
    y = 935
    nf = font(SERIF_B, 46)
    for ln in wrap_px(d, p.get('name', ''), nf, 960)[:2]:
        d.text((60, y), ln, font=nf, fill=INK)
        y += 62
    y += 12
    df = font(SANS_R, 26)
    for ln in wrap_px(d, p.get('desc', ''), df, 960)[:4]:
        d.text((60, y), ln, font=df, fill=(60, 60, 50))
        y += 44
    d.line([60, H - 120, 1020, H - 120], fill=OLIVE, width=2)
    cols = [('COUNTRY', p.get('country', '')), ('TYPE', p.get('kind', '')), ('PRICE', '¥{:,}'.format(int(p.get('price') or 0)))]
    for i, (k, v) in enumerate(cols):
        x = 60 + i * 330
        d.text((x, H - 102), k, font=font(SANS_B, 18), fill=(130, 125, 105))
        d.text((x, H - 76), v, font=font(SANS_B, 30), fill=INK)
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
        prods = dft.get('products', [])
        total = 1 + len(prods)
        img = cover(dft, dft['row'] - 1)
        path = folder + '/1.jpg'; img.save(path, 'JPEG', quality=92); files.append(path)
        for i, p in enumerate(prods, start=2):
            img = item(p, i, total)
            path = folder + '/{}.jpg'.format(i); img.save(path, 'JPEG', quality=92); files.append(path)
        manifest.append({'row': dft['row'], 'files': files})
        print('作成：', folder)
    with open('manifest.json', 'w') as f:
        json.dump(manifest, f, ensure_ascii=False)


if __name__ == '__main__':
    main()
