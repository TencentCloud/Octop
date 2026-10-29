# 第三方许可证 / Third-party licenses

本插件（`simple-theme` / 简单主题）自身代码随 Octop 仓库以 MIT 授权发布；随包分发的
第三方资源如下，原样保留上游许可全文，未修改任何许可文本。

## 1. Inter 字体 — SIL Open Font License 1.1

| 项目 | 值 |
|------|-----|
| 文件 | `../ui/fonts/InterVariable.woff2` |
| 上游 | https://github.com/rsms/inter ，release `v4.0`，包内路径 `web/InterVariable.woff2` |
| 校验 | `sha256 = 8af7bd5b545567adffb3dfceb5bedb353a522d7bf1b3a2b8af7b6064156babc0`（与上游发布包字节一致） |
| 许可 | SIL Open Font License 1.1，见 [`Inter-OFL-1.1.txt`](./Inter-OFL-1.1.txt)（取自同一 release 包内 `LICENSE.txt`，`sha256 = 262481e844521b326f5ecd053e59b98c8b2da78c8ee1bdbb6e8174305e54935a`） |
| 版权 | Copyright (c) 2016 The Inter Project Authors |

字体文件保持上游原始字节，未做子集化或改名，因此不需要额外保留 Reserved Font Name 变更说明。

## 2. 模型品牌图标 — MIT

| 项目 | 值 |
|------|-----|
| 文件 | `../ui/model-icons.js` |
| 上游 | npm [`@lobehub/icons-static-svg@1.98.0`](https://www.npmjs.com/package/@lobehub/icons-static-svg) / https://github.com/lobehub/lobe-icons |
| 生成 | `../tools/gen_model_icons.py`（CDN 固定到 `@1.98.0`，取 `icons/<slug>.svg`） |
| 许可 | MIT，见 [`LobeHub-icons-MIT.txt`](./LobeHub-icons-MIT.txt)（上游仓库 `LICENSE`，`sha256 = add9d7531d1b21646317a8958e38fc727506fa39d24bdecb44154d943c82753a`） |
| 版权 | Copyright (c) 2023 LobeHub |

派生说明：`model-icons.js` 是上游 SVG 的派生作品——几何路径保持原样，仅做两处机械变换：
① 把上游单色图标的 `fill="currentColor"` 替换为品牌近似色（见脚本 `BRAND_COLORS`），
避免 CSS data URI 里的 `currentColor` 变黑；② 压缩标签间空白并编码为 `data:image/svg+xml` URI。
上游许可为 MIT，允许修改与再分发；各品牌标识本身仍属其权利人商标，此处仅作模型归属展示。

## 3. 其他

`../ui/theme.css`、`../ui/index.template.js`、`../ui/index.js`、`../main.py`、`../build.py`、
`../icon.svg` 为本插件原创代码/资源，随 Octop 仓库 MIT 授权。
