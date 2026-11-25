# lean-answer

让 AI 回复短、像人写、可审计。

一个可以直接运行的回复规范：不只告诉模型「该怎么做」，还带着11个校验脚本和44个回归样本：每条规则都有一个可执行的检查，每次改版都要过闸。

## 为什么不是又一个 prompt

市面上的「简洁回复」提示词只做一件事：在 system prompt 里写「请简洁」。结果取决于模型当天的状态，没有任何东西拦得住退化。

lean-answer 的做法是把规则变成代码：

| 你写的 | 它跑的 | 它拦的 |
|---|---|---|
| 任何文本 | `gate.py`（一条命令） | 开场客套、收尾邀约、平行方案堆砌、过程流水账、重点超量、篇幅超限、主题夹带 |
| 带 AI 味的稿子 | `deai.py` | 逐处改写10类包浆句式，出改动表，改不动的转人工 |
| 要交付的文档 | `audit.py` | 100分制合规报告，逐条给位置与改法，MD+HTML |
| 示意图 | `validate_svg.py` | 溢出、越界、重叠、文字裁切 |

改坏了规则也不怕：44个回归样本一条命令跑完，规则退化当场现形。

## 三档严格度

| 档 | 何时用 | 行为 |
|---|---|---|
| lite | 自己要快 | 只砍废话，不查句式标点 |
| standard | 默认，发给同事 | 全套规则+过闸 |
| audit | 交甲方、过审 | standard + 出合规报告 |

## 安装

```bash
# Claude Code 等70+ 兼容 agent（skills.sh 生态）
npx skills add zhewenzhang/lean-answer

# WorkBuddy
解压 zip 到 ~/.workbuddy/skills/

# 装完自检（18项，输出哪一环没通、怎么修）
python scripts/doctor.py
```

若 doctor 的「全局记忆引用」报 FAIL：skill 装了但对话不会自动加载，需要在用户级 MEMORY.md 顶部加一条规则指向本目录。这是「装了没生效」的头号原因，详见 `references/troubleshooting.md`。

## 常用命令

```bash
python scripts/gate.py 稿件.md                  # 发送前过闸（结构+表达）
python scripts/deai.py 原稿.md                  # 去 AI 味，出改动表
python scripts/deai.py 原稿.md --apply          # 另存 <名>.deai.md
python scripts/audit.py 稿件.md --html r.html   # 合规报告（100分制）
python scripts/doctor.py --brief                # 安装自检
python scripts/regress.py                       # 44项回归，改规则后必跑
```

## 效果示例

同一段状态汇报，改写前后：

```text
改前：「我先连接了微云，然后查看文件夹，发现需要建目录，于是建了目录，接着开始上传……」（128字）

改后：「备份完成12/14档；2档 >100MB 跳过。明早照常。」（38字）
```

同一句包浆句式：

```text
改前：「这不是一个技术问题，而是一个协作问题。」
改后：「这是协作问题，技术问题不是关键。」
```

## 诚实的数字

token 总账是算出来的，不是宣称的。口径：中文1.6字/token+ASCII 4字/token（保守）与中文1.2+ASCII 3（宽松），给区间。

| 项 | 字数 | 估算token |
|---|---|---|
| 主文件每轮注入 | 3236 | 1282~1709 |
| 单轮输出节省（3场景实测均值） | N/A | 228~303 |
| 盈亏平衡 | N/A | **约6轮/天** |

- 每天对话超过6轮才开始净省token；少于6轮，注入成本大于节省。
- 这基于合成样本与粗估tokenizer。装上后跑你自己的10轮对比，才是你的真实账。
- gotchas 的隐性收益：单次避坑≈一次返工（500~2000 token），3条已实际拦下返工。

## 它不做什么

- 不改专业内容结构。研报、PPT、讲稿的完整度不受影响，只有表达层受约束。
- 不替你判断事实对错。脚本查形式，观点真假靠人。
- 不做整篇重写。去 AI 味只做点状修改并列出位置。
- 高后果任务（医疗、法律、安全、生产代码）可靠性优先于篇幅。

## 目录

```text
SKILL.md              主规范，约3200字，每轮注入
references/           细则，按需加载
  anti-ai-style.md      去AI味规则与改写边界
  modes.md              三档严格度的取舍
  focus-rules.md        单主线与注意力预算
  task-modes.md         交付型 vs 事务型
  execution-rules.md    完成判据与三态汇报
  diagram-rules.md      示意图坐标与排版规范
  gotchas.md            18条真实踩坑
  troubleshooting.md    装了没生效怎么查
  test-cases.md         人工验收清单
scripts/              11个脚本，均可独立运行
tests/                44项回归样本（制图/回复/表达/计划/台账）
```

## 改版纪律

```bash
python scripts/regress.py     # 44项全过才可发版
```

两条铁律：回归不符时修脚本不改预期。把预期改成让测试通过，等于没有测试；新增规则必须同步补一个 `_pass` 或 `_fail` 样本，没有样本的规则无法回归。

## License

MIT
