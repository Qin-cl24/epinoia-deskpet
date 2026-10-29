#!/usr/bin/env python3
"""把 PSD 每层解成 PNG（只在内容框范围内解码，快），并输出认层用的指标

画世界导出的 PSD：图层名都是「图层N」、边界都是整张画布，所以这里自己算内容框，
只解内容框那几行的通道数据（RLE 的行可以独立寻址）。

用法：
    python3 tools/fox-from-psd.py <文件.psd> --out 目录 [--stride 4]
"""
import importlib.util
import os
import struct
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("psd", os.path.join(HERE, "psd-layers.py"))
pl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pl)


def channel_rows(psd, layer, want=(-1, 0, 1, 2), y_from=0, y_to=None):
    """解出指定通道的行（只解码 y_from..y_to），返回 {通道: {y: bytes}}"""
    W, H = psd["width"], psd["height"]
    y_to = H if y_to is None else min(y_to, H)
    buf = psd["buf"]
    chans, lens = layer["channels"], layer["_chan_lens"]
    out = {}
    pos = layer["_data_start"]
    for cid, ln in zip(chans, lens):
        start = pos
        pos += ln
        if cid not in want:
            continue
        comp = struct.unpack_from(">H", buf, start)[0]
        body = start + 2
        rows = {}
        if comp == 0:
            for y in range(y_from, y_to):
                rows[y] = buf[body + y * W: body + (y + 1) * W]
        elif comp == 1:
            counts = struct.unpack_from(">%dH" % H, buf, body)
            pre = [0] * (H + 1)          # 前缀和，避免每行都 sum(counts[:y])
            for i, c in enumerate(counts):
                pre[i + 1] = pre[i] + c
            base = body + H * 2
            for y in range(y_from, y_to):
                off = base + pre[y]
                rows[y] = pl.packbits_decode(buf[off:off + counts[y]], W)
        else:
            raise SystemExit(f"不支持的压缩方式 {comp}")
        out[cid] = rows
    return out


def layer_image(psd, layer, bb, pad=0):
    x0, y0, x1, y1 = bb
    W = psd["width"]
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(W, x1 + pad); y1 = min(psd["height"], y1 + pad)
    rows = channel_rows(psd, layer, y_from=y0, y_to=y1)
    img = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    px = img.load()
    for y in range(y0, y1):
        r_row = rows.get(0, {}).get(y)
        g_row = rows.get(1, {}).get(y)
        b_row = rows.get(2, {}).get(y)
        a_row = rows.get(-1, {}).get(y)
        for x in range(x0, x1):
            px[x - x0, y - y0] = (
                r_row[x] if r_row else 0,
                g_row[x] if g_row else 0,
                b_row[x] if b_row else 0,
                a_row[x] if a_row else 255,
            )
    return img, (x0, y0, x1, y1)


def metrics(img):
    """面积、填充率、平均色、最厚处（用逐层腐蚀估厚度，判断是「块」还是「细笔画」）"""
    a = img.split()[3]
    W, H = img.size
    px = a.load()
    src = img.load()
    area = 0
    sumc = [0, 0, 0]
    for y in range(H):
        for x in range(W):
            if px[x, y] > 140:
                area += 1
                r, g, b, _ = src[x, y]
                sumc[0] += r; sumc[1] += g; sumc[2] += b
    mean = tuple(c // max(area, 1) for c in sumc)
    # 厚度：腐蚀 N 次直到没有像素，N*2 大约是最大笔画宽度
    thick = 0
    cur = a.point(lambda v: 255 if v > 140 else 0)
    for i in range(1, 60):
        cur = cur.filter(__import__("PIL.ImageFilter", fromlist=["ImageFilter"]).MinFilter(3))
        if cur.getbbox() is None:
            break
        thick = i * 2
    return {"area": area, "fill": round(area / max(1, W * H), 3), "mean": mean, "thick": thick}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    out_dir = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else \
        os.path.expanduser("~/storage/downloads/fox-psd-full")
    stride = int(sys.argv[sys.argv.index("--stride") + 1]) if "--stride" in sys.argv else 4
    os.makedirs(out_dir, exist_ok=True)
    psd = pl.parse(path)
    print(f'画布 {psd["width"]}x{psd["height"]}，{len(psd["layers"])} 层')
    print(f'{"序号":>4} {"名":<7} {"内容框":<26} {"尺寸":>11} {"面积":>7} {"填充":>5} {"最厚":>4} 均色')
    total = 0
    for lay in psd["layers"]:
        if lay["name"] == "背景" or not lay["visible"]:
            continue
        bb = pl.content_bbox(psd, lay, stride=stride)
        if bb is None:
            continue
        img, realbb = layer_image(psd, lay, bb, pad=2)
        m = metrics(img)
        total += m["area"]
        fn = os.path.join(out_dir, f'{lay["index"]:02d}-{lay["name"]}.png')
        img.save(fn)
        print(f'{lay["index"]:>4} {lay["name"]:<7} {str(realbb):<26} '
              f'{img.size[0]:>5}x{img.size[1]:<5} {m["area"]:>7} {m["fill"]:>5} {m["thick"]:>4} {m["mean"]}')
    print(f"（所有层面积合计 {total}，输出目录 {out_dir}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
