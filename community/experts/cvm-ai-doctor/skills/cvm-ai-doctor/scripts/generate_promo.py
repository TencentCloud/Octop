import os

from PIL import Image

# 3:4 比例,设定目标尺寸为 1200x1600
target_width = 1200
target_height = 1600

# 创建画布
canvas = Image.new("RGB", (target_width, target_height), (255, 255, 255))

# 上半部分:AI 宣传图
top_img_path = "generated-images/A_modern__sleak_promotional_ba_2026-04-08T07-30-09.png"
if not os.path.exists(top_img_path):
    # 尝试另一张
    top_img_path = "generated-images/A_friendly_cartoon_style_docto_2026-04-08T07-34-43.png"

top_img = Image.open(top_img_path)
# 调整到画布宽度,保持比例,放到上半部分
top_aspect = top_img.width / top_img.height
new_top_height = int(target_width / top_aspect)
top_img_resized = top_img.resize((target_width, new_top_height), Image.Resampling.LANCZOS)

# 下半部分:LightClaw 截图
bottom_img_path = "docs/lightclaw-dashboard.png"
bottom_img = Image.open(bottom_img_path)
# 调整到画布宽度,保持比例
bottom_aspect = bottom_img.width / bottom_img.height
new_bottom_height = int(target_width / bottom_aspect)
bottom_img_resized = bottom_img.resize((target_width, new_bottom_height), Image.Resampling.LANCZOS)

# 计算位置:上图顶部对齐,下图底部对齐,中间留白或裁剪
available_height = target_height
if new_top_height + new_bottom_height <= target_height:
    # 两张图放得下,上下排列,中间留白
    canvas.paste(top_img_resized, (0, 0))
    canvas.paste(bottom_img_resized, (0, target_height - new_bottom_height))
else:
    # 放不下,按比例裁剪
    top_height_final = int(target_height * 0.5)  # 上半占 50%
    bottom_height_final = target_height - top_height_final

    top_img_final = top_img_resized.crop((0, 0, target_width, top_height_final))
    bottom_img_final = bottom_img_resized.crop((0, 0, target_width, bottom_height_final))

    canvas.paste(top_img_final, (0, 0))
    canvas.paste(bottom_img_final, (0, top_height_final))

# 保存
output_path = "generated-images/promo-3x4-composite.png"
canvas.save(output_path, "PNG", quality=95)
print(f"✅ 图片已生成: {output_path}")
print(f"尺寸: {canvas.width}x{canvas.height} (3:4)")
