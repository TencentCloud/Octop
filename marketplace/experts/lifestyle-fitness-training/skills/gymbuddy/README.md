

<h1 align="center">GymBuddy.skill</h1>

<p align="center">
  <strong><em
    >"致敬最不雄竞，最不虚荣，最善待新手的健身圈"</em
  ></strong>
</p>

<div align="center">
  <table border="1" cellpadding="14" cellspacing="0" width="92%">
    <tbody>
      <tr>
        <td align="left">
          <ol>
            <li>你是否想要找一个私教，但是囊中羞涩，同时害怕私教敷衍了事。</li>
            <li>你是否希望完整跟练 克里斯，罗尼，谭成义等等大Pro，但是直播切片和 跟练教程让你眼花缭乱。</li>
            <li>你是否焦虑现状，排一晚上队，只为上麦让网友给你诊断体态，结果只连线了1 分钟。</li>
            <li>你是否想要获得认可，但是发照片到网上只获得如潮水般的雄竞和浮夸炫耀，反而自己皮质醇爆炸。</li>
          </ol>
        </td>
      </tr>
    </tbody>
  </table>
</div>

<p align="center">
你们的强来了，蒸馏你的赛博私教，打造的你的专属健身领域 Skill，诊断你的训练现状，回答你的训练疑惑，制定你的训练计划，甚至疯狂的夸奖你的训练成果。
</p>

---
## 功能概览

- **人格与 SOP**：见 [`prompts/persona.md`](prompts/persona.md)、[`prompts/expert_sop.md`](prompts/expert_sop.md)。
- **知识库**：见 [`data/knowledge/`](data/knowledge/)（原创整理摘要，非版权书籍原文）。
- **索引**：更新知识文件后运行 `python build_index.py`，生成 `data/index/knowledge_chunks.jsonl` 便于按章节定位。

## 安装（Cursor）

将本仓库（或其中 Skill 目录）放到项目的 `.cursor/skills/gymbuddy-skill/`（或个人 `~/.cursor/skills/`），确保根目录存在 [`SKILL.md`](SKILL.md)。详细规则见 [Cursor Agent Skills](https://docs.cursor.com)。

## 安装（Claude Code）

可将本目录克隆到 `.claude/skills/gymbuddy-skill`，按 [Claude Code Skills](https://docs.anthropic.com) 说明启用。

## 依赖

Python **3.9+**。`build_index.py` 与 `tools/fitness_calc.py` 仅使用标准库；[`requirements.txt`](requirements.txt) 留空占位，便于日后追加。

## 使用提示

- 对 Agent：`SKILL.md` 中已写明「先读 prompts → 再读 data/knowledge → 引用文件名」。
- 命令行 TDEE 示例：

```bash
python tools/fitness_calc.py --weight 70 --height 175 --age 30 --gender male --activity 1.55
```

## 致谢

思路与单仓库 Skill 的组织方式参考 [colleague-skill / dot-skill](https://github.com/titanwings/colleague-skill)。

## 许可证

见 [`LICENSE`](LICENSE)（继承上游 MIT 等声明；若上游限制不同，以保持 `LICENSE` 文件为准）。
