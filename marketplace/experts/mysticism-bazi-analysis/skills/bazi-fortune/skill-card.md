## Description: <br>

生辰八字排盘与运势分析（bazi-fortune）根据出生日期时间、性别与出生地点排出标准八字四柱命盘（十神、纳音、十二长生、空亡、地支藏干、胎元命宫），量化判断日主强弱与喜用神，列出大运与逐年流年运势，并结合姓名、成长经历与家庭条件进行参断，最终输出可视化 HTML 命理报告。<br>

支持真太阳时校正（经度时差 + 均时差）、中国夏令时回退（1986–1991）、十二时辰定盘（未知时辰时用人生事件反推）、姓名五格剖象与五行补益分析。<br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>

[待填写：你的 SkillHub / ClawHub 用户名](https://clawhub.ai/user/your-name) <br>

### License/Terms of Use: <br>

MIT <br>


## Use Case: <br>

面向对命理、传统文化感兴趣的个人用户：想了解自己的八字构成、五行喜忌、事业财运方向、婚姻感情倾向、健康养生提醒，以及未来数年逐年运势。<br>

也可用于新生儿起名/成人改名的五行补益参考，以及结合过往人生事件校验出生时辰（定盘）。<br>

### Deployment Geography for Use: <br>

Global（中文场景为主） <br>

## Known Risks and Mitigations: <br>

Risk: 输出结果属于命理与民俗范畴，可能被误当成医疗、法律、投资、择业的决定性依据。<br>
Mitigation: 技能内置措辞红线（禁用"必然、注定、一定会"），健康内容只作养生提醒并注明以医嘱为准，报告强制保留免责声明，重大决策一律提示咨询专业人士。<br>

Risk: 出生时辰或地点不准会导致排盘错误，进而给出偏差结论。<br>
Mitigation: 时辰不明时要求先跑 `--hour-scan` 十二时辰比对并结合人生事件定盘，报告中明确标注"时辰待定"；地点未匹配到坐标时提示用 `--lon` 指定经度，不做静默假设。<br>

Risk: 脚本依赖第三方库 `lunar-python`，可能在无网络环境下安装失败。<br>
Mitigation: 脚本启动时自动尝试 pip 安装，失败时给出明确手动安装命令；README 中列出了依赖与版本要求。<br>

Risk: 姓名五格依赖康熙笔画表，生僻字可能缺失或笔画存疑。<br>
Mitigation: 缺字时不强行计算，返回明确提示并要求用 `--stroke 字=数字` 人工补充，报告中标注该字未参与计算。<br>


## Reference(s): <br>

- [README](README.md) <br>
- [Skill definition](SKILL.md) <br>
- [排盘引擎](scripts/bazi.py) <br>
- [判读规则](references/bazi_theory.md) <br>
- [分项断语库](references/interpretation.md) <br>
- [报告撰写规范](references/report_writing.md) <br>


## Skill Output: <br>

**Output Type(s):** [text, markdown, structured JSON, HTML report] <br>
**Output Format:** [对话内结构化文字结论，或浅色中式排版的 HTML 命理报告] <br>
**Output Parameters:** [四柱干支、十神、纳音、星运、空亡、藏干、五行力量评分、日主强弱与喜用神、神煞、刑冲合害、大运流年逐年表、姓名五格与三才、定时校正说明] <br>
**Other Properties Related to Output:** [不输出疾病诊断、死亡预测、灾祸断言；所有结论均为倾向性描述并附免责声明。] <br>

## Skill Version(s): <br>

1.0.0 — 首发：四柱排盘、真太阳时与夏令时校正、强弱与喜用神、神煞与刑冲合害、大运流年、时辰定盘、姓名五格、HTML 报告。 <br>
