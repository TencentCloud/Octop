# 数据源参考手册

按分类整理的热榜/热点内容数据源完整目录。
每个条目标注了可用的获取通道（60s API / DailyHotApi / browser_use）及优先级。

> DailyHotApi 的调用方式、参数详解和返回格式见 `dailyhot-api.md`。
> 本文件中 DailyHotApi 只标注 source 名（如 `hupu`），实际调用命令为 `node <skill目录>/scripts/fetch_dailyhot.mjs <source> [参数]`。

## 获取通道说明

| 通道 | 基础 URL | 特点 |
|------|----------|------|
| **60s API** | `https://60s.viki.moe/v2` | 公共免费，速度最快，无需认证，覆盖 50+ 端点（含金融/天气/影视等） |
| **DailyHotApi** | `node <skill目录>/scripts/fetch_dailyhot.mjs <source>` | 覆盖 56 个源，统一 JSON 响应，补充 60s API 未覆盖的源。详见 `dailyhot-api.md` |
| **browser_use** | 各站点 URL | 浏览器直接访问，速度最慢但覆盖面最广 |

**优先级：60s API > DailyHotApi > browser_use**

## 目录
1. [社交媒体与热搜](#社交媒体与热搜)
2. [新闻门户](#新闻门户)
3. [科技与开发者](#科技与开发者)
4. [财经与商业](#财经与商业)
5. [金融工具与数据](#金融工具与数据)
6. [视频与内容](#视频与内容)
7. [影视与音乐](#影视与音乐)
8. [社区与论坛](#社区与论坛)
9. [游戏](#游戏)
10. [科普与数码](#科普与数码)
11. [国际](#国际)
12. [应急与天气](#应急与天气)
13. [实用工具](#实用工具)
14. [数据源选择指南](#数据源选择指南)

---

## 社交媒体与热搜

### 1. 微博热搜
- **60s API：** `GET /v2/weibo`
- **DailyHotApi：** `weibo`
- **browser_use：** `https://weibo.com/hot/search`
- **可靠性：** 高
- **提取内容：** 带编号的热搜词列表，含排名、关键词、热度数值、趋势标签（新/热/沸/爆）

### 2. 知乎热榜
- **60s API：** `GET /v2/zhihu`
- **DailyHotApi：** `zhihu`
- **browser_use：** `https://www.zhihu.com/hot`
- **可靠性：** 高
- **提取内容：** 前 50 个热门问题，含标题、摘要、热度（xx万热度）

### 3. 知乎日报
- **DailyHotApi：** `zhihu-daily`
- **browser_use：** `https://daily.zhihu.com`
- **可靠性：** 中
- **提取内容：** 编辑精选的每日文章，含标题和描述

### 4. 百度热搜
- **60s API：** `GET /v2/baidu/hot`
- **DailyHotApi：** `baidu`
- **browser_use：** `https://top.baidu.com/board`
- **可靠性：** 高
- **提取内容：** 排名搜索词，含搜索指数和简要描述

### 5. 抖音热点
- **60s API：** `GET /v2/douyin`
- **DailyHotApi：** `douyin`
- **browser_use：** `https://www.douyin.com/hot`
- **可靠性：** 中（浏览器可能弹登录/下载提示，API 更稳定）
- **提取内容：** 热门话题，含标题、描述、热度数值

### 6. 快手热榜
- **DailyHotApi：** `kuaishou`
- **browser_use：** `https://www.kuaishou.com`
- **可靠性：** 低（浏览器重 JS 渲染，建议用 API）
- **提取内容：** 热门视频/话题

### 7. 百度贴吧热议
- **60s API：** `GET /v2/baidu/tieba`
- **DailyHotApi：** `tieba`
- **browser_use：** `https://tieba.baidu.com/hottopic/browse/topicList`
- **可靠性：** 高
- **提取内容：** 讨论话题，含回复数和讨论热度

### 8. 小红书热点
- **60s API：** `GET /v2/rednote`
- **browser_use：** `https://www.xiaohongshu.com`
- **可靠性：** 中
- **提取内容：** 小红书热门内容

### 9. 夸克热点
- **60s API：** `GET /v2/quark`
- **browser_use：** `https://www.quark.cn`
- **可靠性：** 中
- **提取内容：** 夸克浏览器热点榜单

### 10. 懂车帝热搜
- **60s API：** `GET /v2/dongchedi`
- **browser_use：** `https://www.dongchedi.com`
- **可靠性：** 中
- **提取内容：** 汽车领域热搜榜单

---

## 新闻门户

### 11. 每日60秒新闻
- **60s API：** `GET /v2/60s`（支持 `date` 和 `encoding` 参数）
- **可靠性：** 高
- **提取内容：** 每日 15 条精选新闻 + 每日一言。每 30 分钟更新

### 12. AI 资讯快报
- **60s API：** `GET /v2/ai-news`
- **可靠性：** 高
- **提取内容：** AI 领域最新资讯（日更）

### 13. 今日头条
- **60s API：** `GET /v2/toutiao`
- **DailyHotApi：** `toutiao`
- **browser_use：** `https://www.toutiao.com/trending/`
- **可靠性：** 高
- **提取内容：** 按热度排名的热门文章，含标题、热度值、来源

### 14. 腾讯新闻
- **DailyHotApi：** `qq-news`
- **browser_use：** `https://news.qq.com`
- **可靠性：** 高
- **提取内容：** 首页头条新闻，含标题和分类标签

### 15. 澎湃新闻
- **DailyHotApi：** `thepaper`
- **browser_use：** `https://www.thepaper.cn`
- **可靠性：** 高
- **提取内容：** 焦点新闻和"热榜"，含浏览量

### 16. 新浪新闻
- **DailyHotApi：** `sina-news`
- **browser_use：** `https://news.sina.com.cn`
- **可靠性：** 高
- **提取内容：** 按分类（要闻/国际/社会/财经）组织的头条新闻

### 17. 新浪热搜
- **DailyHotApi：** `sina`
- **browser_use：** `https://sinanews.sina.cn/news/hotnews`
- **可靠性：** 中
- **提取内容：** 热点新闻排行，含热度值

### 18. 网易新闻
- **DailyHotApi：** `netease-news`
- **browser_use：** `https://news.163.com`
- **可靠性：** 高
- **提取内容：** 主要头条和热门板块

### 19. 纽约时报中文
- **DailyHotApi：** `nytimes`
- **browser_use：** `https://cn.nytimes.com`
- **可靠性：** 中（可能有付费墙）
- **提取内容：** 国际新闻标题

### 20. 历史上的今天
- **60s API：** `GET /v2/today-in-history`
- **DailyHotApi：** `history`
- **browser_use：** `https://baike.baidu.com/calendar`
- **可靠性：** 高
- **提取内容：** 今天日期对应的历史事件

---

## 科技与开发者

### 21. 稀土掘金
- **DailyHotApi：** `juejin`
- **browser_use：** `https://juejin.cn/hot/articles`
- **可靠性：** 高
- **提取内容：** 按热度排名的技术文章，含标题、作者、浏览量、分类标签

### 22. CSDN
- **DailyHotApi：** `csdn`
- **browser_use：** `https://blog.csdn.net/rank/list`
- **可靠性：** 高
- **提取内容：** 按浏览量排名的博客文章

### 23. 51CTO
- **DailyHotApi：** `51cto`
- **browser_use：** `https://www.51cto.com`
- **可靠性：** 中
- **提取内容：** 技术新闻和教程排行

### 24. 少数派
- **DailyHotApi：** `sspai`
- **browser_use：** `https://sspai.com`
- **可靠性：** 高
- **提取内容：** 数码工具、效率和 Apple 生态的精选文章

### 25. IT之家
- **DailyHotApi：** `ithome`
- **browser_use：** `https://www.ithome.com`
- **可靠性：** 高
- **提取内容：** 科技新闻标题和热榜

### 26. IT之家喜加一
- **DailyHotApi：** `ithome-xijiayi`
- **browser_use：** `https://www.ithome.com/zt/xijiayi`
- **可靠性：** 高
- **提取内容：** 免费游戏赠品和优惠

### 27. GitHub Trending
- **DailyHotApi：** `github`
- **browser_use：** `https://github.com/trending`
- **可靠性：** 高
- **提取内容：** 热门仓库，含所有者/仓库名、描述、star 数、今日新增

### 28. HelloGitHub
- **DailyHotApi：** `hellogithub`
- **browser_use：** `https://hellogithub.com`
- **可靠性：** 高
- **提取内容：** 每月精选开源项目

### 29. NodeSeek
- **DailyHotApi：** `nodeseek`
- **browser_use：** `https://www.nodeseek.com`
- **可靠性：** 高
- **提取内容：** VPS/主机社区讨论

### 30. 简书
- **DailyHotApi：** `jianshu`
- **browser_use：** `https://www.jianshu.com`
- **可靠性：** 中
- **提取内容：** 热门文章和精选内容

---

## 财经与商业

### 31. 36氪
- **DailyHotApi：** `36kr`
- **browser_use：** `https://www.36kr.com/hot-list/catalog`
- **可靠性：** 高
- **提取内容：** 热门文章，侧重创业、VC 融资、行业分析

### 32. 爱范儿
- **DailyHotApi：** `ifanr`
- **browser_use：** `https://www.ifanr.com`
- **可靠性：** 高
- **提取内容：** 科技产品新闻、评测、行业分析

### 33. 什么值得买
- **DailyHotApi：** `smzdm`
- **browser_use：** `https://post.smzdm.com/fenlei/zhinan/`
- **可靠性：** 高
- **提取内容：** 消费品推荐和优惠

### 34. 虎嗅
- **DailyHotApi：** `huxiu`
- **browser_use：** `https://www.huxiu.com`
- **可靠性：** 高
- **提取内容：** 商业分析和行业洞察

### 35. 新浪财经
- **DailyHotApi：** `sina`
- **browser_use：** `https://finance.sina.com.cn`
- **可靠性：** 高
- **提取内容：** 股市头条、大盘指数（上证/深证/创业板）、财经新闻

### 36. 雪球
- **browser_use：** `https://xueqiu.com/today`（无 API 覆盖）
- **可靠性：** 中（可能需要登录）
- **提取内容：** 投资讨论、个股分析、市场点评

---

## 金融工具与数据

### 37. 黄金价格
- **60s API：** `GET /v2/gold-price`（支持 `encoding` 参数：json/text/markdown）
- **可靠性：** 高
- **提取内容：** 实时贵金属行情（黄金/白银/铂金/钯金），含国际金价、各大金店金价、银行金条价格、黄金回收价格

### 38. 货币汇率
- **60s API：** `GET /v2/exchange-rate`（参数：`currency=CNY` 指定基准货币）
- **可靠性：** 高
- **提取内容：** 当日全球货币汇率，默认 CNY 基准，含更新时间和下次更新时间

### 39. 汽油价格
- **60s API：** `GET /v2/fuel-price`
- **可靠性：** 高
- **提取内容：** 国内各地油价查询

---

## 视频与内容

### 40. 哔哩哔哩排行
- **60s API：** `GET /v2/bili`
- **DailyHotApi：** `bilibili`
- **browser_use：** `https://www.bilibili.com/v/popular/rank/all`
- **可靠性：** 高
- **提取内容：** 热门视频排行，含标题、UP主、播放量

### 41. AcFun
- **DailyHotApi：** `acfun`
- **browser_use：** `https://www.acfun.cn/rank/list`
- **可靠性：** 高
- **提取内容：** 视频和文章排行

### 42. 微信读书
- **DailyHotApi：** `weread`
- **browser_use：** `https://weread.qq.com`
- **可靠性：** 中
- **提取内容：** 热门书籍和阅读榜单

### 43. 游研社
- **DailyHotApi：** `yystv`
- **browser_use：** `https://www.yystv.cn`
- **可靠性：** 高
- **提取内容：** 游戏行业新闻、评测、分析

---

## 影视与音乐

### 44. 猫眼全球票房
- **60s API：** `GET /v2/maoyan/all/movie`
- **可靠性：** 高
- **提取内容：** 全球电影票房总榜

### 45. 猫眼实时电影票房
- **60s API：** `GET /v2/maoyan/realtime/movie`
- **可靠性：** 高
- **提取内容：** 电影实时票房数据

### 46. 猫眼电视收视排行
- **60s API：** `GET /v2/maoyan/realtime/tv`
- **可靠性：** 高
- **提取内容：** 电视剧收视率排行

### 47. 猫眼网剧热度
- **60s API：** `GET /v2/maoyan/realtime/web`
- **可靠性：** 高
- **提取内容：** 网剧实时热度排行

### 48. 豆瓣全球口碑电影榜
- **60s API：** `GET /v2/douban/weekly/movie`
- **DailyHotApi：** `douban-movie`
- **browser_use：** `https://movie.douban.com/chart`
- **可靠性：** 高
- **提取内容：** 豆瓣全球口碑电影（周更）

### 49. 豆瓣华语口碑剧集榜
- **60s API：** `GET /v2/douban/weekly/tv_chinese`
- **可靠性：** 高
- **提取内容：** 华语口碑剧集（周更）

### 50. 豆瓣全球口碑剧集榜
- **60s API：** `GET /v2/douban/weekly/tv_global`
- **可靠性：** 高
- **提取内容：** 全球口碑剧集（周更）

### 51. 豆瓣华语口碑综艺榜
- **60s API：** `GET /v2/douban/weekly/show_chinese`
- **可靠性：** 高
- **提取内容：** 华语口碑综艺（周更）

### 52. 豆瓣全球口碑综艺榜
- **60s API：** `GET /v2/douban/weekly/show_global`
- **可靠性：** 高
- **提取内容：** 全球口碑综艺（周更）

### 53. 百度电视剧榜
- **60s API：** `GET /v2/baidu/teleplay`
- **可靠性：** 高
- **提取内容：** 百度电视剧热度排行

### 54. 网易云音乐排行榜
- **60s API：** `GET /v2/ncm-rank/list`（榜单列表）、`GET /v2/ncm-rank/:id`（榜单详情）
- **可靠性：** 高
- **提取内容：** 各类音乐排行榜及歌曲详情

---

## 社区与论坛

### 55. V2EX
- **DailyHotApi：** `v2ex`
- **browser_use：** `https://www.v2ex.com/?tab=hot`
- **可靠性：** 高
- **提取内容：** 热门讨论话题，科技/开发者社区

### 56. 豆瓣讨论
- **DailyHotApi：** `douban-group`
- **browser_use：** `https://www.douban.com/group/explore`
- **可靠性：** 中
- **提取内容：** 生活、文化、娱乐的热门小组讨论

### 57. 豆瓣电影
- **DailyHotApi：** `douban-movie`
- **browser_use：** `https://movie.douban.com/chart`
- **可靠性：** 高
- **提取内容：** 票房排行、新片、评分
- **备注：** 口碑榜单优先用 60s API（见“影视与音乐”分类 #48）

### 58. 虎扑
- **DailyHotApi：** `hupu`
- **browser_use：** `https://bbs.hupu.com/all-gambia`
- **可靠性：** 高
- **提取内容：** 体育热门讨论和社区话题

### 59. NGA
- **DailyHotApi：** `ngabbs`
- **browser_use：** `https://ngabbs.com`
- **可靠性：** 高
- **提取内容：** 游戏社区热门讨论

### 60. 水木社区
- **DailyHotApi：** `newsmth`
- **browser_use：** `https://www.newsmth.net`
- **可靠性：** 中
- **提取内容：** 学术和科技社区热门话题

### 61. 全球主机交流 (Hostloc)
- **DailyHotApi：** `hostloc`
- **browser_use：** `https://hostloc.com/forum.php`
- **可靠性：** 中
- **提取内容：** VPS/主机优惠和技术讨论

### 62. 吾爱破解
- **DailyHotApi：** `52pojie`
- **browser_use：** `https://www.52pojie.cn`
- **可靠性：** 中
- **提取内容：** 软件和逆向工程社区讨论

### 63. Linux.do
- **DailyHotApi：** `linuxdo`
- **browser_use：** `https://linux.do`
- **可靠性：** 高
- **提取内容：** Linux/开源社区讨论

### 64. 酷安
- **DailyHotApi：** `coolapk`
- **browser_use：** `https://www.coolapk.com`
- **可靠性：** 中
- **提取内容：** Android 社区讨论、应用评测、数码产品新闻

---

## 游戏

### 65. 英雄联盟
- **DailyHotApi：** `lol`
- **browser_use：** `https://lol.qq.com/news/`
- **可靠性：** 高
- **提取内容：** 英雄联盟新闻、版本更新、电竞赛事

### 66. 原神（米游社）
- **DailyHotApi：** `genshin`
- **browser_use：** `https://www.miyoushe.com/ys`
- **可靠性：** 高
- **提取内容：** 原神社区新闻、公告、玩家创作

### 67. 崩坏3（米游社）
- **DailyHotApi：** `honkai`
- **browser_use：** `https://www.miyoushe.com/bh3`
- **可靠性：** 高
- **提取内容：** 崩坏3 社区新闻和版本更新

### 68. 崩坏：星穹铁道（米游社）
- **DailyHotApi：** `starrail`
- **browser_use：** `https://www.miyoushe.com/sr`
- **可靠性：** 高
- **提取内容：** 星穹铁道社区新闻和版本更新

### 69. GameRes 游资网
- **DailyHotApi：** `gameres`
- **browser_use：** `https://www.gameres.com`
- **可靠性：** 中
- **提取内容：** 游戏行业新闻、开发资源、分析

---

## 科普与数码

### 70. 果壳
- **DailyHotApi：** `guokr`
- **browser_use：** `https://www.guokr.com`
- **可靠性：** 高
- **提取内容：** 生物、物理、健康、科技的科普文章

### 71. 极客公园
- **DailyHotApi：** `geekpark`
- **browser_use：** `https://www.geekpark.net`
- **可靠性：** 高
- **提取内容：** 科技行业深度报道、创始人访谈、产品分析

### 72. 数字尾巴
- **DailyHotApi：** `dgtle`
- **browser_use：** `https://www.dgtle.com`
- **可靠性：** 高
- **提取内容：** 数字生活、数码评测、摄影

---

## 国际

### 73. Hacker News
- **60s API：** `GET /v2/hacker-news/top`（另有 `/v2/hacker-news/new` 和 `/v2/hacker-news/best`）
- **DailyHotApi：** `hackernews`
- **browser_use：** `https://news.ycombinator.com`
- **可靠性：** 高
- **提取内容：** 按分数排名的头条，含标题、链接、分数、评论数

### 74. Product Hunt
- **DailyHotApi：** `producthunt`
- **browser_use：** `https://www.producthunt.com`
- **可靠性：** 高
- **提取内容：** 今日热门产品发布，含产品名、一句话介绍、投票数

### 75. 纽约时报
- **browser_use：** `https://www.nytimes.com`（无 API 覆盖）
- **可靠性：** 中（部分文章有付费墙）
- **提取内容：** 首页国际新闻标题

---

## 应急与天气

### 76. 中央气象台（天气预警）
- **DailyHotApi：** `weatheralarm`
- **browser_use：** `http://www.nmc.cn`
- **可靠性：** 高
- **提取内容：** 当前天气预警和警报

### 77. 中国地震台
- **DailyHotApi：** `earthquake`
- **browser_use：** `https://news.ceic.ac.cn`
- **可靠性：** 高
- **提取内容：** 最新地震报告，含震级、位置、时间

### 78. 实时天气
- **60s API：** `GET /v2/weather/realtime`（参数：`query=城市名`，默认北京）
- **可靠性：** 高
- **提取内容：** 当前天气、温度、湿度、风力、空气质量（AQI/PM2.5）、生活指数、天气预警

### 79. 天气预报
- **60s API：** `GET /v2/weather/forecast`（参数：`query=城市名&days=7`）
- **可靠性：** 高
- **提取内容：** 逐小时和逐日天气预报，含最高/最低温度、天气状况

---

## 实用工具

### 80. 摸鱼日报
- **60s API：** `GET /v2/moyu`
- **可靠性：** 高
- **提取内容：** 摸鱼日历

### 81. Epic 免费游戏
- **60s API：** `GET /v2/epic`
- **可靠性：** 高
- **提取内容：** Epic Games 当前免费游戏（周更）

### 82. 百度百科
- **60s API：** `GET /v2/baike`（参数：`query=关键词`）
- **可靠性：** 高
- **提取内容：** 百科词条查询

### 83. 翻译
- **60s API：** `ALL /v2/fanyi`（参数：`query=文本&from=auto&to=zh`）
- **可靠性：** 高
- **提取内容：** 109 种语言互译

### 84. 歌词搜索
- **60s API：** `ALL /v2/lyric`（参数：`query=歌名或歌词`）
- **可靠性：** 高
- **提取内容：** 歌曲歌词

### 85. 必应壁纸
- **60s API：** `GET /v2/bing`
- **可靠性：** 高
- **提取内容：** 必应每日壁纸

---

## 数据源选择指南

当用户的请求对应某个分类时，使用以下预设方案。优先使用 60s API。

### 每日早报（综合）
`60s /v2/60s` → `60s /v2/weibo` → `60s /v2/zhihu` → `60s /v2/toutiao` → `fetch_dailyhot.mjs 36kr`

### 科技/开发者
`60s /v2/hacker-news/top` → `fetch_dailyhot.mjs github` → `fetch_dailyhot.mjs juejin` → `fetch_dailyhot.mjs v2ex` → `fetch_dailyhot.mjs ithome`

### 财经/投资
`60s /v2/gold-price` → `60s /v2/exchange-rate` → `fetch_dailyhot.mjs 36kr` → `fetch_dailyhot.mjs sina` → `60s /v2/weibo`（过滤财经）→ `browser_use 雪球`

### 娱乐/社交
`60s /v2/weibo` → `60s /v2/douyin` → `60s /v2/rednote` → `60s /v2/bili` → `fetch_dailyhot.mjs kuaishou`

### 影视/综艺
`60s /v2/maoyan/realtime/movie` → `60s /v2/douban/weekly/movie` → `60s /v2/douban/weekly/tv_chinese` → `60s /v2/baidu/teleplay` → `60s /v2/maoyan/realtime/web`

### 开发者/开源
`60s /v2/hacker-news/top` → `fetch_dailyhot.mjs github` → `fetch_dailyhot.mjs v2ex` → `fetch_dailyhot.mjs juejin` → `fetch_dailyhot.mjs nodeseek` → `fetch_dailyhot.mjs linuxdo`

### 国际新闻
`60s /v2/hacker-news/top` → `fetch_dailyhot.mjs producthunt` → `fetch_dailyhot.mjs nytimes` → `browser_use 纽约时报`

### AI/人工智能
`60s /v2/ai-news` → `60s /v2/hacker-news/top` → `fetch_dailyhot.mjs 36kr`（过滤AI）→ `fetch_dailyhot.mjs juejin`（过滤AI）

### 汽车
`60s /v2/dongchedi` → `60s /v2/fuel-price` → `60s /v2/weibo`（过滤汽车）

### 游戏
`60s /v2/epic` → `fetch_dailyhot.mjs ngabbs` → `fetch_dailyhot.mjs genshin` → `fetch_dailyhot.mjs yystv` → `fetch_dailyhot.mjs gameres`

### 体育
`fetch_dailyhot.mjs hupu` → `60s /v2/weibo`（过滤体育）

### 生活/消费
`fetch_dailyhot.mjs smzdm` → `60s /v2/rednote` → `fetch_dailyhot.mjs coolapk`

### 天气/应急
`60s /v2/weather/realtime` → `60s /v2/weather/forecast` → `fetch_dailyhot.mjs earthquake` → `fetch_dailyhot.mjs weatheralarm`

### 金融数据（快速查询）
`60s /v2/gold-price` → `60s /v2/exchange-rate` → `60s /v2/fuel-price`（按需选取）

---

## 通道覆盖统计

| 通道 | 覆盖源数 | 说明 |
|------|----------|------|
| 60s API | 50+ 个 | 热榜（微博/知乎/百度/抖音/头条/B站/小红书/夸克/懂车帝/HN）+ 影视（猫眼/豆瓣/百度电视剧）+ 金融（金价/汇率/油价）+ 天气 + 音乐 + AI资讯 等 |
| DailyHotApi | 56 个 | 补充 60s API 未覆盖的源（36氪/虎嗅/新浪财经/GitHub/掘金等） |
| browser_use | 85 个 | 所有源都可浏览器访问（兜底） |
| 仅 browser_use | 1 个 | 雪球（无 API 覆盖） |
