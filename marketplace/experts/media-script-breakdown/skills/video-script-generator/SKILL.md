---
name: video-script-generator
description: 生成短视频脚本和分镜。输入产品/主题描述、目标受众、时长，输出完整脚本+分镜结构（JSON/YAML）。支持多种模板：痛点-解决、反转剧情、before-after。触发词：视频脚本、短视频文案、分镜、storyboard、video script。
---

# 短视频脚本+分镜生成

## 工作流程

1. 收集输入信息
2. 选择模板风格
3. 生成脚本+分镜结构
4. 输出结构化数据供下游消费

## 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| topic | ✓ | 产品/主题描述 |
| audience | ✓ | 目标受众 |
| duration | ✓ | 时长：15s / 30s / 60s / 90s |
| template | - | 模板：pain-solution / before-after / plot-twist |
| platform | - | 平台：douyin / xiaohongshu / youtube-shorts |
| tone | - | 语气：professional / casual / humorous / dramatic |

## 模板说明

### pain-solution（默认）
痛点引入 → 解决方案 → 效果展示 → CTA

### before-after
对比前的状态 → 转折点 → 对比后的状态 → CTA

### plot-twist
正常叙事 → 意外反转 → 揭示真相 → CTA

详见 [templates/](templates/) 目录。

## 输出格式

```yaml
meta:
  title: "脚本标题"
  duration: 30s
  platform: douyin
  template: pain-solution

script:
  hook: "开场钩子文案"
  
  scenes:
    - id: 1
      type: hook           # hook/pain/solution/demo/cta
      duration: 3s
      narration: "旁白/台词"
      shot_description: "镜头描述：特写/中景/全景，动作，表情"
      visual_style: "画面风格提示"
      demo_insert: false
      
    - id: 2
      type: pain
      duration: 5s
      narration: "..."
      shot_description: "..."
      demo_insert: false
      
    - id: 3
      type: solution
      duration: 8s
      narration: "..."
      shot_description: "产品界面展示"
      demo_insert: true
      demo_action: "点击生成按钮，展示结果"
      
    - id: 4
      type: cta
      duration: 3s
      narration: "链接在评论区"
      shot_description: "logo + 二维码"
      demo_insert: false

  cta: "链接在评论区 / 点击头像私信"
  
music_suggestion: "轻快节奏 / 紧张悬疑 / 温馨治愈"
```

## 场景类型

| type | 用途 | 典型时长 |
|------|------|----------|
| hook | 开场吸引 | 2-3s |
| pain | 痛点展示 | 3-5s |
| solution | 解决方案 | 5-10s |
| demo | 产品演示 | 5-15s |
| result | 效果展示 | 3-5s |
| twist | 反转 | 3-5s |
| cta | 行动号召 | 2-3s |

## 时长分配参考

| 总时长 | 场景数 | 分配建议 |
|--------|--------|----------|
| 15s | 3-4 | hook(2) + core(10) + cta(3) |
| 30s | 4-6 | hook(3) + pain(5) + solution(15) + cta(3) |
| 60s | 6-8 | hook(3) + pain(8) + solution(35) + result(10) + cta(4) |

## 使用示例

用户：帮我写一个30秒的短视频脚本，推广我的AI写作工具，目标用户是自媒体博主

执行：
1. 确认参数：topic=AI写作工具, audience=自媒体博主, duration=30s
2. 选择模板：pain-solution（默认）
3. 生成脚本+分镜
4. 输出 YAML 结构

## 下游对接

输出的结构化数据可直接用于：
- `digital-avatar` skill：提取 narration 生成口播
- `scene-video-generator` skill：按 shot_description 生成画面
- `video-stitcher` skill：按 duration 拼接
