#!/usr/bin/env python3
"""把 PSD 每一层拼成一张带序号的缩略图总览（认图层用）

画世界导出的 PSD 里图层名都是「图层N」、边界都是整张画布，只能看像素认。
本工具按 stride 隔行解码（行可以独立寻址，所以速度快），每层出：
    · 裁到内容框的缩略图 PNG（默认 1/4 大小）
    · 一张总览图，每格标了序号，方便主人指着说「几号是耳朵」

用法：
    python3 tools/psd-sheet.py <文件.psd> [--out 目录] [--stride 4]
"""
import importlib.util
import os
import struct
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("psd", os.path.join(HERE, "psd-layers.py"))
psd_lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(psd_lib)

SKIP_NAMES = {"背景"}


def layer_thumb(psd, layer, stride):
    """隔行解码一层 → 1/stride 缩略图（RGBA），返回 (图像, 内容框)"""
    W = psd["width"]
    H = psd["height"]
    bb = psd_lib.content_bbox(psd, layer, stride=stride)
    if bb is None:
        return None, None
    x0, y0, x1, y1 = bb
    chans, lens = layer["channels"], layer["_chan_lens"]
    pos = layer["_data_start"]
    rows = {}
    cols_needed = [c for c in (-1, 0, 1, 2) if c in chans]
    planes = {}
    for cid, ln in zip(chans, lens):
        start = pos
        pos += ln
        if cid not in cols_needed:
            continue
        buf = psd["buf"]
        comp = struct.unpack_from(">H", buf, start)[0]
        body = start + 2
        counts = None
        if comp == 1:
            counts = struct.unpack_from(">%dH" % H, buf, body)
            base = body + H * 2
        out = {}
        for y in range(y0, min(y1, H), stride):
            if comp == 0:
                row = buf[body + y * W: body + (y + 1) * W]
            else:
                off = base + sum(counts[:y])
                row = psd_lib.packbits_decode(buf[off:off + counts[y]], W)
            out[y] = row[x0:min(x1, W):stride]
        planes[cid] = out
    th = (len(range(y0, min(y1, H), stride)))
    tw = len(range(x0, min(x1, W), stride))
    img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    px = img.load()
    ys = sorted(planes.get(0, {}).keys())
    for row_i, y in enumerate(ys):
        r_row = planes.get(0, {}).get(y)
        g_row = planes.get(1, {}).get(y)
        b_row = planes.get(2, {}).get(y)
        a_row = planes.get(-1, {}).get(y)
        for x_i in range(min(tw, len(r_row) if r_row else 0)):
            r = r_row[x_i] if r_row else 0
            g = g_row[x_i] if g_row else 0
            b = b_row[x_i] if b_row else 0
            a = a_row[x_i] if a_row else 255
            px[x_i, row_i] = (r, g, b, a)
    return img, bb


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    out_dir = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else \
        os.path.expanduser("~/storage/downloads/fox-psd-layers")
    stride = int(sys.argv[sys.argv.index("--stride") + 1]) if "--stride" in sys.argv else 4
    os.makedirs(out_dir, exist_ok=True)
    psd = psd_lib.parse(path)
    print(f'画布 {psd["width"]}x{psd["height"]}，{len(psd["layers"])} 层，stride={stride}')

    thumbs = []
    for lay in psd["layers"]:
        if lay["name"] in SKIP_NAMES:
            print(f'  跳过 {lay["name"]}')
            continue
        img, bb = layer_thumb(psd, lay, stride)
        if img is None:
            print(f'  空层 {lay["index"]:>2} {lay["name"]}')
            continue
        img.save(os.path.join(out_dir, f'{lay["index"]:02d}-{lay["name"]}.png'))
        thumbs.append((lay["index"], lay["name"], img, bb, lay["visible"]))
        print(f'  {lay["index"]:>2} {lay["name"]:<8} 内容框 {bb}  缩略 {img.size}  可见={lay["visible"]}')

    # 总览：等大格子，每格把缩略图等比放进去，左上角标序号
    cell = 150
    cols = 6
    rows_n = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows_n * cell), (44, 44, 50))
    d = ImageDraw.Draw(sheet)
    for i, (idx, name, img, bb, visible) in enumerate(thumbs):
        cx, cy = (i % cols) * cell, (i // cols) * cell
        d.rectangle([cx, cy, cx + cell - 1, cy + cell - 1], outline=(90, 90, 100))
        # 格子底色：棋盘格，方便看透明区域
        for gy in range(0, cell, 10):
            for gx in range(0, cell, 10):
                if (gx // 10 + gy // 10) % 2 == 0:
                    d.rectangle([cx + gx, cy + gy, cx + gx + 9, cy + gy + 9], fill=(58, 58, 66))
        w, h = img.size
        k = min((cell - 24) / w, (cell - 24) / h)
        thumb = img.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
        px_ = (cell - thumb.width) // 2
        py_ = (cell - thumb.height) // 2 + 6
        sheet.paste(thumb, (cx + px_, cy + py_), thumb)
        d.text((cx + 4, cy + 3), f'{idx}', fill=(255, 220, 90))
        if not visible:
            d.text((cx + cell - 34, cy + 3), "HIDE", fill=(255, 120, 120))
    dst = os.path.join(out_dir, "_总览.png")
    sheet.save(dst)
    print("总览图:", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
