#!/usr/bin/env python3
"""读 PSD 图层清单（纯 Python，不依赖 psd-tools / numpy）

画世界（ArtPlanet）导出的 PSD 直接能读：图层名、位置、尺寸、通道、透明度。
本工具默认只**列清单**（不解码像素，很快）；加 --extract 才把某几层解成 PNG。

用法：
    python3 tools/psd-layers.py <文件.psd>                       # 列所有图层
    python3 tools/psd-layers.py <文件.psd> --json                # 同上，JSON 输出
    python3 tools/psd-layers.py <文件.psd> --extract 名字或序号 --out 目录
"""
import json
import os
import struct
import sys


class Reader:
    def __init__(self, buf, pos=0):
        self.b = buf
        self.p = pos

    def u8(self):
        v = self.b[self.p]
        self.p += 1
        return v

    def u16(self):
        v = struct.unpack_from(">H", self.b, self.p)[0]
        self.p += 2
        return v

    def i16(self):
        v = struct.unpack_from(">h", self.b, self.p)[0]
        self.p += 2
        return v

    def u32(self):
        v = struct.unpack_from(">I", self.b, self.p)[0]
        self.p += 4
        return v

    def i32(self):
        v = struct.unpack_from(">i", self.b, self.p)[0]
        self.p += 4
        return v

    def take(self, n):
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def pascal_name(self):
        n = self.u8()
        raw = self.take(n)
        total = 1 + n
        pad = (4 - total % 4) % 4
        self.take(pad)
        return raw


def parse(path):
    with open(path, "rb") as f:
        buf = f.read()
    r = Reader(buf)
    sig = r.take(4)
    if sig != b"8BPS":
        raise SystemExit(f"不是 PSD：{sig!r}")
    version = r.u16()
    r.take(6)
    channels = r.u16()
    height = r.u32()
    width = r.u32()
    depth = r.u16()
    color_mode = r.u16()

    r.take(r.u32())                     # 颜色模式数据
    r.take(r.u32())                     # 图像资源

    layer_mask_len = r.u32()
    lm_end = r.p + layer_mask_len
    layer_info_len = r.u32()
    li_end = r.p + layer_info_len
    n_layers = r.i16()
    if n_layers < 0:
        n_layers = -n_layers

    layers = []
    for i in range(n_layers):
        top, left, bottom, right = r.i32(), r.i32(), r.i32(), r.i32()
        nch = r.u16()
        chans = [(r.i16(), r.u32()) for _ in range(nch)]
        r.take(4)                        # '8BIM'
        blend = r.take(4).decode("latin-1")
        opacity = r.u8()
        clipping = r.u8()
        flags = r.u8()
        r.u8()
        extra_len = r.u32()
        extra_end = r.p + extra_len
        # 图层蒙版
        mask_len = r.u32()
        r.take(mask_len)
        # 混合范围
        br_len = r.u32()
        r.take(br_len)
        name = r.pascal_name().decode("latin-1", "replace")
        unicode_name = None
        while r.p + 12 <= extra_end:
            k1 = r.take(4)
            if k1 not in (b"8BIM", b"8B64"):
                break
            key = r.take(4).decode("latin-1")
            ln = r.u32()
            data = r.take(ln)
            if key == "luni":
                cnt = struct.unpack_from(">I", data, 0)[0]
                unicode_name = data[4:4 + cnt * 2].decode("utf-16-be", "replace")
            if ln % 2:
                r.take(1)
        r.p = extra_end
        visible = not (flags & 2)
        layers.append({
            "index": i,
            "name": unicode_name or name,
            "bounds": [left, top, right, bottom],
            "w": right - left,
            "h": bottom - top,
            "channels": [c[0] for c in chans],
            "opacity": round(opacity / 255, 3),
            "visible": visible,
            "blend": blend,
            "_chan_lens": [c[1] for c in chans],
        })
    # 通道数据起点：每层按顺序
    data_pos = r.p
    for lay in layers:
        lay["_data_start"] = data_pos
        data_pos += sum(lay["_chan_lens"])
    return {
        "version": version, "width": width, "height": height, "depth": depth,
        "color_mode": color_mode, "channels": channels, "layers": layers,
        "buf": buf,
    }


def packbits_decode(data, expected):
    out = bytearray()
    i = 0
    n = len(data)
    while i < n and len(out) < expected:
        h = data[i]
        i += 1
        if h < 128:
            out += data[i:i + h + 1]
            i += h + 1
        elif h > 128:
            out += bytes([data[i]]) * (257 - h)
            i += 1
        # h == 128: 无操作
    if len(out) < expected:
        out += bytes(expected - len(out))
    return bytes(out[:expected])


def decode_channel(psd, start, length, rows, cols, depth):
    """解一个通道 → 每行一个 bytes（灰度/RLE 都可）"""
    buf = psd["buf"]
    comp = struct.unpack_from(">H", buf, start)[0]
    pos = start + 2
    if comp == 0:                                    # 原始
        if depth == 8:
            out = buf[pos:pos + rows * cols]
        else:
            out = buf[pos:pos + rows * cols * depth // 8][::depth // 8]
        return [out[y * cols:(y + 1) * cols] for y in range(rows)]
    if comp == 1:                                    # RLE
        if psd["version"] == 1:
            counts = struct.unpack_from(">%dH" % rows, buf, pos)
            pos += rows * 2
        else:
            counts = struct.unpack_from(">%dI" % rows, buf, pos)
            pos += rows * 4
        lines = []
        for c in counts:
            lines.append(packbits_decode(buf[pos:pos + c], cols))
            pos += c
        return lines
    raise SystemExit(f"不支持的压缩方式 {comp}")


def extract(psd, layer, out_path):
    """把一个图层解成 PNG（RGBA）"""
    from PIL import Image
    w, h = layer["w"], layer["h"]
    if w <= 0 or h <= 0:
        raise SystemExit("空图层")
    chans = layer["channels"]
    lens = layer["_chan_lens"]
    pos = layer["_data_start"]
    planes = {}
    for cid, ln in zip(chans, lens):
        planes[cid] = decode_channel(psd, pos, ln, h, w, psd["depth"])
        pos += ln
    img = Image.new("RGBA", (w, h))
    px = img.load()
    ids = [c for c in (-1, 0, 1, 2) if c in planes]   # -1=alpha, 0..2=RGB
    has_alpha = -1 in planes
    for y in range(h):
        row = {}
        for cid in ids:
            row[cid] = planes[cid][y]
        for x in range(w):
            r = row[0][x] if 0 in row else 0
            g = row[1][x] if 1 in row else 0
            b = row[2][x] if 2 in row else 0
            a = row[-1][x] if has_alpha else 255
            px[x, y] = (r, g, b, a)
    img.save(out_path)
    return img


def content_bbox(psd, layer, stride=8, alpha_thr=20):
    """只看 alpha 通道、隔行采样，快速算出这层实际内容框（画布坐标）"""
    W, H = psd["width"], psd["height"]
    chans = layer["channels"]
    lens = layer["_chan_lens"]
    if -1 not in chans:
        return None
    pos = layer["_data_start"] + sum(ln for cid, ln in zip(chans, lens) if cid != -1)
    ln = lens[chans.index(-1)]
    buf = psd["buf"]
    comp = struct.unpack_from(">H", buf, pos)[0]
    body = pos + 2
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    for y in range(0, H, stride):
        if comp == 0:
            row = buf[body + y * W: body + (y + 1) * W]
        else:
            counts = struct.unpack_from(">%dH" % H, buf, body)
            off = body + H * 2 + sum(counts[:y])
            row = packbits_decode(buf[off:off + counts[y]], W)
        idx = [i for i, v in enumerate(row) if v > alpha_thr]
        if idx:
            x0 = min(x0, idx[0]); x1 = max(x1, idx[-1])
            y0 = min(y0, y); y1 = max(y1, y)
    if x1 < 0:
        return None
    return (x0, y0, x1 + 1, y1 + stride)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    psd = parse(path)
    print(f'画布 {psd["width"]}x{psd["height"]}  {psd["depth"]}bit  通道 {psd["channels"]}  '
          f'图层 {len(psd["layers"])} 层')

    if "--bbox" in sys.argv:
        print(f'{"序号":>4}  内容框(left,top,right,bottom)        尺寸')
        for lay in psd["layers"]:
            bb = content_bbox(psd, lay)
            if bb is None:
                print(f'{lay["index"]:>4}  （空图层）')
                continue
            print(f'{lay["index"]:>4}  {bb[0]:>5},{bb[1]:>5},{bb[2]:>5},{bb[3]:>5}   '
                  f'{bb[2]-bb[0]:>5}x{bb[3]-bb[1]:<5}  {lay["name"]}')
        return 0

    if "--json" in sys.argv:
        print(json.dumps([{k: v for k, v in l.items() if not k.startswith("_")}
                          for l in psd["layers"]], ensure_ascii=False, indent=1))
        return 0

    if "--extract" in sys.argv:
        want = sys.argv[sys.argv.index("--extract") + 1]
        out_dir = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "."
        os.makedirs(out_dir, exist_ok=True)
        hit = [l for l in psd["layers"] if l["name"] == want or str(l["index"]) == want]
        if not hit:
            print("没找到图层", want)
            return 1
        for lay in hit:
            safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in lay["name"])
            dst = os.path.join(out_dir, f'{lay["index"]:02d}-{safe}.png')
            extract(psd, lay, dst)
            print("写出", dst, f'({lay["w"]}x{lay["h"]} @ {lay["bounds"][0]},{lay["bounds"][1]})')
        return 0

    print(f'{"序号":>4}  {"图层名":<24} {"位置(left,top)":>16} {"尺寸":>11}  不透明度  可见')
    for lay in psd["layers"]:
        b = lay["bounds"]
        nm = lay["name"][:24]
        pad = "　" * (24 - len(nm))          # 中文按两格宽对齐
        print(f'{lay["index"]:>4}  {nm}{pad} {b[0]:>7},{b[1]:<7} {lay["w"]:>5}x{lay["h"]:<5} '
              f'{lay["opacity"]:>8}  {"✓" if lay["visible"] else "✗"}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
