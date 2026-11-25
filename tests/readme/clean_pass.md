# lean-answer

让 AI 回复短、像人写、可审计。

## 装

```bash
# 解压到用户级 skills 目录
unzip lean-answer.zip -d ~/.workbuddy/skills/
# 确认安装正常
python ~/.workbuddy/skills/lean-answer/scripts/doctor.py
```

doctor 会输出18项检查。全 PASS 才算装好。若「全局记忆引用」显示 FAIL，说明 skill 装了但对话里不会自动加载，按提示在用户级 MEMORY.md 顶部加一条规则指向该目录。

## 用

三档严格度，默认 standard。

| 档 | 何时用 | 命令 |
|---|---|---|
| lite | 自己要快 | 说「简一点」 |
| standard | 默认，发给同事 | 无需说明 |
| audit | 交甲方、过审 | `python scripts/audit.py 稿件.md` |

常用命令：

```bash
python scripts/gate.py 稿件.md            # 发送前过闸（结构+表达）
python scripts/deai.py 原稿.md            # 去 AI 味，出改动表
python scripts/deai.py 原稿.md --apply    # 另存 <名>.deai.md
python scripts/audit.py 稿件.md --html r.html   # 合规报告
python scripts/doctor.py --brief          # 安装自检
```

## 它做什么

- **结构**：禁开场客套与收尾邀约，重点 ≤3，一轮只推进一个目标，过程流水账要删。
- **表达**：中文用「」，数字与中文不留空格，破折号 ≤1处，10类包浆句式同篇 ≤1次。
- **密度**：>200字无图无表会提示，长回复要求先给结论。

## 它不做什么

- 不改专业内容结构。研报、PPT、讲稿的完整度不受影响，只有表达层受约束。
- 不替你判断事实对错。脚本查的是形式，观点的真假靠人。
- 不做整篇重写。去 AI 味只做点状修改并列位置。

## 目录

```text
SKILL.md              主规范，约3200字，每轮注入
references/           细则，按需加载
  anti-ai-style.md      去 AI 味规则与改写边界
  modes.md              三档严格度的取舍
  focus-rules.md        单主线与注意力预算
  task-modes.md         交付型 vs 事务型
  execution-rules.md    完成判据与三态汇报
  diagram-rules.md      示意图坐标与排版规范
  gotchas.md            18条真实踩坑
  troubleshooting.md    装了没生效怎么查
  test-cases.md         人工验收清单
scripts/              11个脚本，均可独立运行
tests/                43项回归样本
```

## 回归

```bash
python scripts/regress.py     # 改任何规则后必跑，43项全过才可发版
```

回归不符时修脚本，不改预期。把预期改成让测试通过，等于没有测试。

## 许可

[待填：授权方式]

---

本 skill 不含投资、医疗、法律建议。剧本与文案的合规责任由使用者承担。
