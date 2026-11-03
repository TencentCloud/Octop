# -*- coding: utf-8 -*-
"""生成 bazi-fortune 技能图标 _icon.png（太极 + 中式棕金配色）。"""
import os
from PIL import Image, ImageDraw

S = 512
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_icon.png")


def main():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 圆角底
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=S // 5, fill=(250, 247, 242, 255))
    d.rounded_rectangle([10, 10, S - 11, S - 11], radius=S // 5 - 6,
                        outline=(139, 94, 60, 255), width=6)

    cx = cy = S // 2
    r = int(S * 0.30)
    bbox = [cx - r, cy - r, cx + r, cy + r]
    # 太极
    d.ellipse(bbox, fill=(255, 255, 255, 255), outline=(139, 94, 60, 255), width=5)
    d.pieslice(bbox, start=90, end=270, fill=(44, 42, 40, 255))
    hr = r // 2
    d.ellipse([cx - hr, cy - r, cx + hr, cy], fill=(44, 42, 40, 255))
    d.ellipse([cx - hr, cy, cx + hr, cy + r], fill=(255, 255, 255, 255))
    er = max(3, r // 7)
    d.ellipse([cx - er, cy - hr - er, cx + er, cy - hr + er], fill=(255, 255, 255, 255))
    d.ellipse([cx - er, cy + hr - er, cx + er, cy + hr + er], fill=(44, 42, 40, 255))

    # 四柱刻度：外圈四点
    for i in range(4):
        a = -90 + i * 90
        import math
        rad = math.radians(a)
        px = cx + int((r + S * 0.075) * math.cos(rad))
        py = cy + int((r + S * 0.075) * math.sin(rad))
        rr = max(5, int(S * 0.022))
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=(185, 138, 90, 255))

    out = os.path.normpath(OUT)
    img.save(out)
    print("已生成", out)


if __name__ == "__main__":
    main()
