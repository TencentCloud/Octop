# DailyHotApi 接口文档

npm 包 `dailyhot-api`，共 56 个路由模块。本文档是参数查阅手册，数据源的分类导航和场景选择见 `sources.md`。

## 安装

**每次会话首次调用 DailyHotApi 前，必须先确保已安装：**

```bash
npm list dailyhot-api 2>/dev/null || npm install dailyhot-api
```

确认安装成功后再执行脚本。禁止跳过安装直接回退 browser_use。

## 调用方式

**必须通过 `fetch_dailyhot.mjs` 脚本调用，禁止自己写代码或拼 HTTP 请求。**

**调用格式：**
```bash
node <skill目录>/scripts/fetch_dailyhot.mjs <source> [key=value ...]
```

**调用示例：**
```bash
# 虎扑步行街 — 主干道
node <skill目录>/scripts/fetch_dailyhot.mjs hupu

# 虎扑 — 恋爱区
node <skill目录>/scripts/fetch_dailyhot.mjs hupu type=6

# 百度热搜
node <skill目录>/scripts/fetch_dailyhot.mjs baidu type=realtime

# GitHub Trending 周榜
node <skill目录>/scripts/fetch_dailyhot.mjs github type=weekly

# 微博（无参数）
node <skill目录>/scripts/fetch_dailyhot.mjs weibo
```

其中 `<skill目录>` 是 SKILL.md 所在目录，脚本位于其 `scripts/` 子目录下。

**返回类型 RouterData：**
```json
{
  "name": "hupu",
  "title": "虎扑",
  "type": "步行街热帖",
  "total": 10,
  "updateTime": "2025-03-13T14:00:00.000Z",
  "fromCache": false,
  "data": [
    {
      "id": "12345",
      "title": "帖子标题",
      "desc": "描述（可选）",
      "hot": 1234,
      "timestamp": 1710000000,
      "url": "https://...",
      "mobileUrl": "https://..."
    }
  ]
}
```

## 全部路由模块

### 新闻资讯

| source | 名称 | 参数 |
|--------|------|------|
| `toutiao` | 今日头条 · 热榜 | 无 |
| `qq-news` | 腾讯新闻 · 热点榜 | 无 |
| `netease-news` | 网易新闻 · 热点榜 | 无 |
| `thepaper` | 澎湃新闻 · 热榜 | 无 |
| `sina-news` | 新浪新闻 · 总排行 | `type`: 1=总排行, 2=视频, 3=图片, 4=国内, 5=国际, 6=社会, 7=体育, 8=财经, 9=娱乐, 10=科技, 11=军事 |
| `sina` | 新浪网 · 热榜 | `type`: all=热榜, hotcmnt=热议, minivideo=视频, ent=娱乐, ai=AI, auto=汽车, mother=育儿, fashion=时尚, travel=旅游, esg=ESG |
| `nytimes` | 纽约时报 · 中文网 | `area`: china=中文网, global=全球版 |

### 社交媒体

| source | 名称 | 参数 |
|--------|------|------|
| `weibo` | 微博 · 热搜榜 | 无 |
| `zhihu` | 知乎 · 热榜 | 无 |
| `zhihu-daily` | 知乎日报 · 推荐榜 | 无 |
| `douyin` | 抖音 · 热榜 | 无 |
| `kuaishou` | 快手 · 热榜 | 无 |
| `tieba` | 百度贴吧 · 热议榜 | 无 |
| `douban-group` | 豆瓣讨论 · 讨论精选 | 无 |

### 搜索引擎

| source | 名称 | 参数 |
|--------|------|------|
| `baidu` | 百度 · 热搜 | `type`: realtime=热搜, novel=小说, movie=电影, teleplay=电视剧, car=汽车, game=游戏 |

### 视频平台

| source | 名称 | 参数 |
|--------|------|------|
| `bilibili` | 哔哩哔哩 · 热榜 | `type`: 0=全站, 1=动画, 3=音乐, 4=游戏, 5=娱乐, 188=科技, 119=鬼畜, 129=舞蹈, 155=时尚, 160=生活, 168=国创, 181=影视 |
| `acfun` | AcFun · 排行榜 | `type`: -1=综合, 155=番剧, 1=动画, 60=娱乐, 201=生活, 58=音乐, 123=舞蹈, 59=游戏, 70=科技, 68=影视, 69=体育, 125=鱼塘; `range`: DAY=今日, THREE_DAYS=三日, WEEK=本周 |

### 影视娱乐

| source | 名称 | 参数 |
|--------|------|------|
| `douban-movie` | 豆瓣电影 · 新片榜 | 无 |
| `weread` | 微信读书 · 飙升榜 | `type`: rising=飙升榜, hot_search=热搜榜, newbook=新书榜, general_novel_rising=小说榜, all=总榜 |

### 科技商业

| source | 名称 | 参数 |
|--------|------|------|
| `36kr` | 36氪 · 人气榜 | `type`: hot=人气榜, video=视频榜, comment=热议榜, collect=收藏榜 |
| `huxiu` | 虎嗅 · 24小时 | 无 |
| `ifanr` | 爱范儿 · 快讯 | 无 |
| `geekpark` | 极客公园 · 热门文章 | 无 |
| `smzdm` | 什么值得买 · 热门 | `type`: 1=今日热门, 7=周热门, 30=月热门 |

### 开发者

| source | 名称 | 参数 |
|--------|------|------|
| `github` | GitHub Trending | `type`: daily=日榜, weekly=周榜, monthly=月榜 |
| `hellogithub` | HelloGitHub · 热门仓库 | `sort`: featured=精选, all=全部 |
| `hackernews` | Hacker News · Popular | 无 |
| `producthunt` | Product Hunt · Today | 无 |
| `juejin` | 稀土掘金 · 文章榜 | `type`: 按分类 ID |
| `csdn` | CSDN · 排行榜 | 无 |
| `51cto` | 51CTO · 推荐榜 | 无 |
| `sspai` | 少数派 · 热榜 | 无 |
| `v2ex` | V2EX · 主题榜 | `type`: hot=最热主题, latest=最新主题 |
| `nodeseek` | NodeSeek · 最新 | 无 |
| `linuxdo` | Linux.do · 热门文章 | 无 |

### IT 资讯

| source | 名称 | 参数 |
|--------|------|------|
| `ithome` | IT之家 · 热榜 | 无 |
| `ithome-xijiayi` | IT之家 · 喜加一 | 无 |
| `dgtle` | 数字尾巴 · 热门文章 | 无 |

### 体育

| source | 名称 | 参数 |
|--------|------|------|
| `hupu` | 虎扑 · 步行街热帖 | `type`: 1=主干道, 6=恋爱区, 11=校园区, 12=历史区, 612=摄影区 |

### 游戏

| source | 名称 | 参数 |
|--------|------|------|
| `genshin` | 原神 · 最新动态 | `type`: 1=公告, 2=活动, 3=资讯 |
| `starrail` | 星穹铁道 · 最新动态 | `type`: 1=公告, 2=活动, 3=资讯 |
| `honkai` | 崩坏3 · 最新动态 | `type`: 1=公告, 2=活动, 3=资讯 |
| `miyoushe` | 米游社 · 公告 | `game`: 1=崩坏3, 2=原神, 3=崩坏学园2, 4=未定事件簿, 5=大别野, 6=星穹铁道, 8=绝区零; `type`: 1=公告, 2=活动, 3=资讯 |
| `lol` | 英雄联盟 · 更新公告 | 无 |
| `gameres` | GameRes 游资网 · 资讯 | 无 |
| `yystv` | 游研社 · 全部文章 | 无 |

### 社区论坛

| source | 名称 | 参数 |
|--------|------|------|
| `coolapk` | 酷安 · 热榜 | 无 |
| `newsmth` | 水木社区 · 热门话题 | 无 |
| `hostloc` | 全球主机交流 · 热门 | `type`: hot=最新热门, digest=最新精华, new=最新回复, newthread=最新发表 |
| `52pojie` | 吾爱破解 · 精华 | `type`: digest=最新精华, hot=最新热门, new=最新回复, newthread=最新发表 |
| `ngabbs` | NGA · 论坛热帖 | 无 |
| `jianshu` | 简书 · 热门推荐 | 无 |
| `guokr` | 果壳 · 热门文章 | 无 |

### 生活工具

| source | 名称 | 参数 |
|--------|------|------|
| `history` | 历史上的今天 | `month`: 月份, `day`: 日期 |
| `earthquake` | 中国地震台 · 地震速报 | 无 |
| `weatheralarm` | 中央气象台 · 气象预警 | `province`: 省份名称 |
