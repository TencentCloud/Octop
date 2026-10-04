# 截图比较入口

`dashboard/scripts/compare-workbuddy-screenshots.mjs` 比较相同像素尺寸的无损 RGBA PNG。任一通道差值超过 10 的像素计为变化，变化比例按未遮罩像素计算，超过 1% 返回非零退出码。它是静态像素比较基础，不能替代实际页面自动化、2 CSS px 几何检查或人工叠图。

从 `dashboard/` 执行：

```sh
node --test scripts/compare-workbuddy-screenshots.test.mjs
node scripts/compare-workbuddy-screenshots.mjs reference.png actual.png masks.json
```

可省略遮罩文件；提供时必须是数组，每个矩形包含整数 `x/y/width/height` 和非空 `reason`。越界、缺少理由或遮住整张截图均报错。遮罩只用于真实动态区域；品牌与能力差异须单独登记和人工核对，不能通过大面积遮罩宣称一比一还原。

```json
[{"x":100,"y":80,"width":40,"height":20,"reason":"固定位置的动态时间"}]
```

原版基准和 Octop 回归基准分别保存，记录版本、页面/状态、视口、像素比、浏览器版本、语言、服务器时区、主题、字体和测试数据。输入尺寸不一致会报错，不缩放基准。

当前内置浏览器返回的展示截图为 JPEG，已按实际格式保存在 `evidence/*.jpg`，只能作为展示检查证据。尚未取得 5.5.6 原版实际运行的无损基准，因此没有执行或通过 1% 原版差异验收。工具自身 3 项测试覆盖遮罩计数、尺寸拒绝及无效遮罩，并不表示业务页面截图回归通过。
