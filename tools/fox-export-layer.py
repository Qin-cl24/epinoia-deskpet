#!/usr/bin/env python3
"""把 PSD 里某一层单独导成 PNG（可带参考层），方便主人在别的画布上补画

主人补画的流程：
    · 拿到 ahoge-fix-canvas.png（只有呆毛，透明底）→ 在画世界/其它画布里补
    · 或者拿 ahoge-fix-guide.png（呆毛 + 周围层 25% 透明参考 + 红色目标框）对着补
    · 补完存成同样尺寸的 PNG 交回来，我按固定偏移放回 PSD 坐标系

用法：
    python3 tools/fox-export-layer.py <文件.psd> --layer 13 --canvas 600,1120,940,1620 \\
        --out 目录 [--guide 12,7,6,14,11] [--rect 726,1348,882,1577]
"""
import importlib.util
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
for name in ("psd-layers", "fox-from-psd"):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    globals()[name.replace("-", "_")] = mod
pl, ffp = psd_layers, fox_from_psd


def arg(name, default=None):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


def layer_full(psd, idx, pad=2):
    lay = [l for l in psd["layers"] if l["index"] == idx][0]
    bb = pl.content_bbox(psd, lay, stride=2)
    img, realbb = ffp.layer_image(psd, lay, bb, pad=pad)
    return img, realbb


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    idx = int(arg("--layer"))
    cvs = tuple(int(v) for v in arg("--canvas").split(","))
    out_dir = os.path.expanduser(arg("--out", "~/storage/pictures/fox-ahoge"))
    guide_ids = [int(v) for v in arg("--guide", "").split(",") if v.strip()]
    rect = tuple(int(v) for v in arg("--rect").split(",")) if arg("--rect") else None
    os.makedirs(out_dir, exist_ok=True)

    psd = pl.parse(path)
    cw, ch = cvs[2] - cvs[0], cvs[3] - cvs[1]
    print(f"导出画布：PSD ({cvs[0]},{cvs[1]}) - ({cvs[2]},{cvs[3]})，{cw}x{ch}")

    def crop_into(img, bb, base=None):
        """把某层的图像按 PSD 坐标贴到画布尺寸的图上"""
        if base is None:
            base = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        base.alpha_composite(img, (bb[0] - cvs[0], bb[1] - cvs[1]))
        return base

    alone, bb = layer_full(psd, idx)
    canvas_alone = crop_into(alone, bb)

    name = "ahoge-fix"
    p1 = os.path.join(out_dir, f"{name}-canvas.png")
    canvas_alone.save(p1)
    print("① 只有这一层（透明底，拿去补画）:", p1, canvas_alone.size)

    if guide_ids:
        guide = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        for gid in guide_ids:
            gimg, gbb = layer_full(psd, gid)
            gimg.putalpha(gimg.split()[3].point(lambda v: v * 30 // 100))
            guide.alpha_composite(gimg, (gbb[0] - cvs[0], gbb[1] - cvs[1]))
        # 待补的层用正常不透明度叠在参考层上面
        guide.alpha_composite(canvas_alone)
        d = ImageDraw.Draw(guide)
        if rect:
            x0, y0, x1, y1 = rect
            d.rectangle([x0 - cvs[0], y0 - cvs[1], x1 - cvs[0], y1 - cvs[1]], outline=(255, 40, 40, 255), width=2)
        p2 = os.path.join(out_dir, f"{name}-guide.png")
        guide.save(p2)
        print("② 带参考层和红框（对着它补）:", p2)
        if rect:
            print(f"   红框 = PSD ({rect[0]},{rect[1]})-({rect[2]},{rect[3]})，"
                  f"在本图里的坐标 ({(rect[0]-cvs[0])},{(rect[1]-cvs[1])})-({(rect[2]-cvs[0])},{(rect[3]-cvs[1])})")

    print("\n补完交回来的要求：尺寸保持 "
          f"{cw}x{ch}，文件名随便，透明底 PNG。我会按 PSD 偏移 ({cvs[0]},{cvs[1]}) 放回去。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
