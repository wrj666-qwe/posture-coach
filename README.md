# posture-coach · 体态矫正 + 体能训练 Skill

一个可直接放进 Claude Code / Codex / 任意支持 Agent Skills 的工具里的技能包：**按人群、需求、身体状况，生成合理、可执行、可校验的训练计划**——既能纠正体态，也能带人练力量。

不是一份固定清单——它会先排查风险，再按「你是谁、想解决什么、有什么器械、能练多久」编排动作、剂量和每周频次，并且把"为什么这么排"和"有没有排错"一起输出给你看。

```
体态模式：建档（6 人群 / 5 目标 / 4 档时长） → 红旗筛查 → 肌肉失衡评估
        → 放松 → 激活 → 强化 → 收尾 → 10 条规则自检

训练模式：建档（目标 / 水平 / 天数 / 器械 / 伤病） → 红旗筛查 → 选分化
        → 主动作 + 辅助 + 核心 → 容量与强度校验 → 4 周递进
```

## 三步用起来

**① 拿到仓库**

```bash
git clone https://github.com/<你的账号>/posture-coach.git
```

不想用 git 就点右上角 **Code → Download ZIP**，解压即可。

**② 装进 AI 工具**（Claude Code 或任何兼容 Agent Skills 的工具）

```bash
# macOS / Linux
cp -r posture-coach ~/.claude/skills/

# Windows PowerShell
Copy-Item -Recurse posture-coach "$env:USERPROFILE\.claude\skills\posture-coach"
```

然后**新开一个对话**，直接说：

> 用 posture-coach 帮我排一份增肌计划，新手，每周 3 天，家里有哑铃

**③ 不用 AI 也能用**

```bash
cd posture-coach/scripts
python plan_builder.py --profile examples/office.json
python program_builder.py --profile examples/fitness-beginner.json --posture
```

零依赖：Python 3.10+ 标准库即可，不用装包、不用 API Key、不用联网。

## 能做什么

- **两种模式**：体态矫正（怎么站得挺拔）与体能训练（怎么练得强壮），可单独用，也可组合
- **按人群派任务**：办公久坐、学生党、产后恢复、中老年、久站服务、健身爱好者，强度上限与频次不同
- **按需求排优先级**：想好看 / 颈肩酸 / 腰背不适 / 运动表现 / 产后恢复，先练哪块不一样
- **支持照片评估**：发正面 / 侧面 / 背面全身照，Agent 看图后先描述观察、转成参数、请你确认，再生成计划（照片只用于看排列，判断不了疼痛与力量）
- **教动作，不只是排计划**：每个动作给口令、易错、降阶与升阶、"怎么教别人"的步骤，并附教学视频链接
- **自带合理性校验**：体态 10 条 + 训练 8 条，脚本逐条检查并输出结果
- **红旗优先**：持续疼痛、麻木放射痛、脊柱手术史、孕产、心血管问题 → 只给安全模式 + 就医指引

## 目录结构

```
posture-coach/
├── SKILL.md                        # 技能主文件（两种模式 + 硬性边界）
├── README.md
├── references/
│   ├── assessment.md               # 体态观察清单 + 紧张/薄弱肌对照表
│   ├── populations.md              # 6 类人群的强度、频次、禁忌
│   ├── planning-rules.md           # 体态编排 10 条规则
│   ├── training-principles.md      # 训练编排 10 条原则 + 教学流程
│   ├── safety.md                   # 红旗、停止信号、就医话术
│   ├── output-templates.md         # 方案 / 每日卡 / 打卡表模板
│   ├── exercise-library.md         # 45 个体态动作（脚本生成）
│   └── exercise-library-strength.md# 36 个力量动作（脚本生成）
├── assets/
│   └── videos/                     # 每个动作的教学视频入口 + 索引页
└── scripts/
    ├── actions.json                # 体态动作库
    ├── strength_exercises.json     # 力量动作库
    ├── plan_builder.py             # 体态方案生成 + 校验
    ├── program_builder.py          # 训练计划生成 + 校验
    ├── adjust_plan.py              # 按日志调整下周计划
    ├── build_video_index.py        # 生成动作视频索引
    ├── train_log.template.json     # 训练日志模板
    └── examples/                   # 示例档案与日志
```

## 安装

把整个 `posture-coach/` 目录放到技能目录：

```bash
# Claude Code（用户级）
cp -r posture-coach ~/.claude/skills/

# 或项目级
cp -r posture-coach .claude/skills/
```

其他工具同理：放进其 Skills 目录，保证 `SKILL.md` 在目录根。

## 使用

### 1. 交给 Agent

直接说"我每天坐 8 小时，圆肩驼背，帮我排个 15 分钟的计划"，Agent 会按 `SKILL.md` 走完建档 → 评估 → 生成 → 自检。

### 2. 直接跑脚本（可复现、可批量）

```bash
# 体态方案
python scripts/plan_builder.py --profile scripts/examples/office.json
python scripts/plan_builder.py --profile scripts/examples/office.json --adjust up

# 训练计划（增肌 / 力量 / 减脂 / 健康体能）
python scripts/program_builder.py --profile scripts/examples/fitness-beginner.json
python scripts/program_builder.py --profile scripts/examples/fitness-beginner.json --posture

# 按训练日志调整下周计划
python scripts/adjust_plan.py --profile scripts/examples/fitness-beginner.json \
    --log scripts/examples/train-log.json

# 自检
python scripts/plan_builder.py --selftest
python scripts/program_builder.py --selftest

# 重新生成动作库文档
python scripts/plan_builder.py --dump-library --out references/exercise-library.md
python scripts/program_builder.py --dump-library --out references/exercise-library-strength.md
```

体态档案：

```json
{
  "population": "office",
  "goal": "look",
  "minutes": 15,
  "days_per_week": 4,
  "issues": ["head", "round", "ant"],
  "red_flags": []
}
```

| 字段 | 取值 |
| --- | --- |
| population | `office` `student` `postpartum` `senior` `standing` `active` |
| goal | `look` `neck` `back` `sport` `recover` |
| minutes | `10` `15` `20` `30` |
| issues | `head` `round` `ant` `post` `shoulder` `leg` `foot` |
| red_flags | `pain` `numb` `spine` `pregnant` `vertigo` |

训练档案：

```json
{
  "goal": "muscle",
  "level": "beginner",
  "days": 3,
  "minutes": 45,
  "equipment": ["dumbbell", "band"],
  "injuries": [],
  "red_flags": [],
  "posture_focus": ["neck", "shoulder"]
}
```

| 字段 | 取值 |
| --- | --- |
| goal | `muscle` `strength` `fat` `health` |
| level | `beginner` `intermediate` `advanced` |
| days | `2`–`5` |
| minutes | `20`–`90` |
| equipment | `none` `band` `dumbbell` `gym` |
| injuries | `knee` `back` `shoulder` `wrist` `ankle` |
| red_flags | `heart` `hypertension` `surgery` `pregnancy` `acute_pain` |
| posture_focus | `neck` `shoulder` `pelvis` `pelvis_post` `lower` `foot`（可选） |

### 输出示例（节选）

```
### 放松
1. 枕下肌群球压｜目标：后脑勺下缘 / 上颈段｜60–90 秒
2. 背阔肌拉伸｜目标：腋下 → 腰侧｜30 秒 × 2

### 激活
4. 靠墙收下巴｜目标：颈深屈肌｜10 次 × 5 秒 × 2 组

## 合理性自检
✓ 时长匹配：预计 12 分钟 ≤ 设定 15 分钟
✓ 顺序正确：放松 → 激活 → 强化 → 收尾
✓ 问题覆盖：3/3 个主诉有对应动作
✓ 松紧配比：放松 3 / 强化 3
```

## 编排规则（"合理"是可验证的）

前 7 条由 `validate()` 自动校验并输出结果，8–10 条体现在生成逻辑与反馈函数里。

| # | 规则 | 不遵守会怎样 |
| --- | --- | --- |
| 1 | 先放松再强化，顺序固定 | 紧张肌没松开，练的都被代偿掉 |
| 2 | 动作数匹配时长（10 分钟 ≤ 4 个） | 做不完，第二天就放弃 |
| 3 | 主诉优先，第一个动作就相关 | 用户第一分钟就失去信任 |
| 4 | 强度不超过人群上限 | 产后/中老年受伤风险 |
| 5 | 禁忌先于偏好 | 有麻木还拉脖子，可能加重 |
| 6 | 松紧配比 1:1 ~ 1:1.6 | 只拉不练没效果，只练不松越练越紧 |
| 7 | 单侧动作标双侧剂量 | 高低肩越练越歪 |
| 8 | 互斥问题只留一个 | 前倾后倾同时练，自相矛盾 |
| 9 | 4 周周期化 + 连续训练日减量 | 停滞或过用 |
| 10 | 按疼痛/完成率调整 | 该减还加，或该加一直原地 |

规则细节见 [`references/planning-rules.md`](references/planning-rules.md)。

## 训练计划怎么保证合理

| # | 规则 | 不遵守会怎样 |
| --- | --- | --- |
| 1 | 先评估（目标/水平/天数/器械/伤病/红旗）再排 | 用默认值硬编，方案对不上人 |
| 2 | 动作模式优先：蹲、髋、水平推、水平拉 | 只练胸不练背，体态越练越差 |
| 3 | 每个主练肌群 3–24 组/周 | 练了等于没练，或恢复不过来 |
| 4 | 强度用 RPE，新手 6–7 起 | 新手一上来就力竭，动作全变形 |
| 5 | 渐进超负荷一次只动一个变量 | 出问题不知道是哪一步引起的 |
| 6 | 每 4 周减载 | 第 6–8 周疲劳累积、动作变形 |
| 7 | 每次都有热身与放松 | 热身不足，受伤风险升高 |
| 8 | 禁忌用替换，不用硬练 | 膝痛还深蹲，越练越伤 |
| 9 | 每个动作给口令 + 易错 + 降阶 | 用户知道练什么，但不会做 |
| 10 | 不越界：不做诊断、不推极限重量 | 风险大于收益 |

细节见 [`references/training-principles.md`](references/training-principles.md)。

## 按日志调整（双进阶）

练完 2–3 次后，把每次的「重量 / 每组次数 / RPE / 疼痛」记成 JSON：

```json
{"date": "2026-11-02", "exercise": "箱式深蹲", "weight": 20, "reps": [12, 12, 11], "rpe": 7, "pain": 0}
```

跑 `adjust_plan.py`，它会逐动作判断：

| 上次表现 | 判断 | 下次 |
| --- | --- | --- |
| 所有组到次数上限、RPE ≤ 目标 | 加量 | +2.5%（最少 0.5 kg），次数回到下限 |
| 最少一组低于下限 | 降重 | -5% |
| RPE ≥ 9 | 保持 | 连续两次则 -5% |
| 疼痛 ≥ 4 | 换动作 | 不加量，降阶或就医 |
| 自重做满上限 | 加次数 | 多做 2–4 次 |
| 平板 / 农夫走 | 加时 | +5 秒 / +5 米 |

输出会直接给一份「已套用新重量」的下周计划表。

## 和体态矫正搭配

在训练档案里加 `posture_focus`（`neck` `shoulder` `pelvis` `pelvis_post` `lower` `foot`），训练计划会自动做三件事：

1. **改选动作**：圆肩 / 头前伸的人，拉必须 ≥ 推的 1.3 倍，不够就补面拉
2. **加矫正收尾**：每次训练后 5 分钟，3 个矫正动作（按诉求挑，至少 1 个强化）
3. **加校验**：推拉平衡、体态配额两条会出现在自检里

顺序固定：**训练 → 矫正 → 放松**。先练大重量再拉长，不会影响训练表现。

## 每个动作配教学视频

`assets/videos/` 里给 36 个力量动作各配了一条视频入口：

- 生成训练计划时，动作表最后一列就是 **▶ 看视频**
- 打开 [`assets/videos/index.html`](assets/videos/index.html) 可以搜索、按部位筛
- **优先短视频**：搜索链接默认加 `duration=1`，只搜 **10 分钟以内**
- 人工挑的视频后面还附一条 **「换更短的（10 分钟内）」**，原视频偏长时点它

重新生成（改完动作库后跑一次）：

```bash
python scripts/build_video_index.py
```

要换成自己的视频，直接编辑 `scripts/build_video_index.py` 顶部 `CURATED` 字典：

```python
CURATED = {
    "箱式深蹲": [("深蹲教学（新手向）", "https://www.bilibili.com/video/BVxxxx/")],
}
```

> 视频版权归原作者，链接来自公开搜索；失效时用搜索入口重新找。

## 自定义

- **加动作**：编辑 `scripts/actions.json`（体态）或 `scripts/strength_exercises.json`（力量），字段照抄现有条目
- **改人群 / 目标**：`scripts/plan_builder.py` 顶部 `POPULATIONS` / `GOALS` / `ISSUES`
- **改训练规则**：`program_builder.py` 的 `SPLITS` / `LEVELS` / `GOALS`，以及 `build_program()` 与 `validate()`
- **改完跑 `--selftest`**

## 测试

```bash
python scripts/plan_builder.py --selftest     # 体态：9 份档案
python scripts/program_builder.py --selftest  # 训练：7 份档案
python scripts/adjust_plan.py --selftest      # 调整：7 条规则
```

体态覆盖：办公（外观/颈肩）、学生短时、产后、中老年、久站、健身者、安全模式、互斥骨盆。
训练覆盖：新手增肌、中级力量、减脂居家、中老年健康、进阶肩伤、带体态矫正、红旗拦截。
调整覆盖：做满加量、次数不足降重、RPE 9 保持、连续 RPE 9 降重、疼痛换动作、平板加时、自重加次数。

## 已知限制

- 不做医学诊断，也替代不了影像与触诊；结构性问题（如真性脊柱侧弯、骨骼性 O 型腿）训练只能改善代偿
- 动作库是通用动作，未覆盖专项运动矫正（如 Schroth）与竞技举重技术
- 训练计划是规则生成，重量需要用户按 RPE 自评，不能替代现场教练的保护与纠错
- 方案基于规则，不是模型推理；需要个体化微调时，由 Agent 在规则之上调整，调整后仍需过一遍自检

## 安全声明

> 本方案仅体态矫正训练参考，若关节持续疼痛、有脊柱损伤、术后等情况，请停止训练并咨询医生/线下康复师。

## License

代码用 **MIT**（见 `LICENSE`）；文字内容与动作库建议同样以 MIT 发布，保留安全声明即可。

视频链接指向 B 站第三方内容，版权归原作者，本仓库只做索引，不托管视频。
