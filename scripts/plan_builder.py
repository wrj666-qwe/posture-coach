#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""体态训练方案生成器（确定性规则引擎）。

输入一份档案 JSON，输出一份可执行、可校验的训练方案。
动作库来自同目录 actions.json；方案规则写在 SKILL.md 与 references/ 里。

用法:
    python plan_builder.py --profile profile.json
    python plan_builder.py --profile profile.json --format json --out plan.json
    python plan_builder.py --profile profile.json --adjust up
    python plan_builder.py --dump-library
    python plan_builder.py --selftest
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
LIB_PATH = BASE / "actions.json"

SAFETY = ("⚠ 安全提示：本方案仅体态矫正训练参考，若关节持续疼痛、有脊柱损伤、术后等情况，"
          "请停止训练并咨询医生/线下康复师。")

POPULATIONS = {
    "office":     {"name": "办公久坐族", "max_level": 2, "days": 4, "modules": ["neck", "shoulder", "pelvis"]},
    "student":    {"name": "学生党",     "max_level": 2, "days": 4, "modules": ["neck", "shoulder", "pelvis"]},
    "postpartum": {"name": "产后恢复期", "max_level": 1, "days": 3, "modules": ["breath", "pelvis", "shoulder"],
                   "exclude": ["postpartum"]},
    "senior":     {"name": "中老年",     "max_level": 2, "days": 3, "modules": ["balance", "neck", "foot"]},
    "standing":   {"name": "久站服务族", "max_level": 2, "days": 4, "modules": ["foot", "lower", "pelvis"]},
    "active":     {"name": "健身爱好者", "max_level": 3, "days": 5, "modules": ["shoulder", "pelvis", "core"],
                   "allow_band": True},
}

GOALS = {
    "look":    {"name": "看起来更挺拔", "modules": ["shoulder", "neck"]},
    "neck":    {"name": "缓解颈肩僵硬", "modules": ["neck", "shoulder"]},
    "back":    {"name": "缓解腰背不适", "modules": ["pelvis", "core"]},
    "sport":   {"name": "提升运动表现", "modules": ["shoulder", "core", "lower"]},
    "recover": {"name": "产后恢复",     "modules": ["breath", "pelvis"]},
}

ISSUES = {
    "head":     {"name": "头前伸 / 探颈",     "modules": ["neck"]},
    "round":    {"name": "圆肩驼背",          "modules": ["shoulder"]},
    "ant":      {"name": "骨盆前倾",          "modules": ["pelvis"]},
    "post":     {"name": "骨盆后倾",          "modules": ["pelvis_post"]},
    "shoulder": {"name": "高低肩",            "modules": ["side", "shoulder"]},
    "leg":      {"name": "X / O 型腿",        "modules": ["lower"]},
    "foot":     {"name": "扁平足 / 足弓塌陷", "modules": ["foot"]},
}

RED_FLAGS = {
    "pain":     "颈肩腰膝有持续疼痛",
    "numb":     "手脚麻木或放射痛",
    "spine":    "脊柱侧弯 / 骨折 / 手术史",
    "pregnant": "孕期或产后 6 周内",
    "vertigo":  "经常头晕 / 头痛",
}

MODULE_NAMES = {
    "neck": "颈部", "shoulder": "肩背", "side": "左右对称",
    "pelvis": "骨盆（前倾）", "pelvis_post": "骨盆（后倾）",
    "lower": "下肢", "foot": "足踝", "breath": "呼吸",
    "balance": "平衡", "core": "核心", "walk": "步行",
}

PHASES = [
    ("relax", "放松", "把紧张缩短的肌肉松开"),
    ("activate", "激活", "低强度唤醒薄弱肌群"),
    ("strength", "强化", "在正确姿势下加负荷"),
    ("close", "收尾", "呼吸与整合，降回静息"),
]

PHASE_LABEL = {pid: name for pid, name, _ in PHASES}

TARGET_COUNT = {10: 4, 15: 6, 20: 8, 30: 11}


# ---------------------------------------------------------------- 工具

def load_library(path: Path = LIB_PATH) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["actions"]


def phase_of(action: dict) -> str:
    if action["type"] == "relax":
        return "close" if "breath" in action["modules"] else "relax"
    return "strength" if action["level"] >= 2 else "activate"


def adjust_dose(dose: str, direction: str) -> str:
    """按方向增减组数，保持剂量文本可读。"""
    if direction == "up":
        if "× 2–3 组" in dose:
            return dose.replace("× 2–3 组", "× 3–4 组")
        if "× 2 组" in dose:
            return dose.replace("× 2 组", "× 3 组")
        if "× 2 / 侧" in dose:
            return dose.replace("× 2 / 侧", "× 3 / 侧")
        if re.search(r"× 2$", dose):
            return re.sub(r"× 2$", "× 3", dose)
        return dose
    if direction == "down":
        if "× 2–3 组" in dose:
            return dose.replace("× 2–3 组", "× 1–2 组")
        if "× 2 组" in dose:
            return dose.replace("× 2 组", "× 1 组")
        if "× 2 / 侧" in dose:
            return dose.replace("× 2 / 侧", "× 1 / 侧")
        if re.search(r"× 2$", dose):
            return re.sub(r"× 2$", "× 1", dose)
        return dose
    return dose


# ---------------------------------------------------------------- 引擎

def max_level_for(profile: dict) -> int:
    pop = POPULATIONS.get(profile.get("population", "office"), POPULATIONS["office"])
    level = pop["max_level"]
    if profile.get("goal") == "sport" and level >= 2:
        level = 3
    if profile.get("goal") == "recover":
        level = min(level, 1)
    return level


def excluded(profile: dict) -> set[str]:
    ex = set(profile.get("red_flags", []))
    pop = POPULATIONS.get(profile.get("population", "office"), {})
    ex.update(pop.get("exclude", []))
    if profile.get("goal") == "recover":
        ex.add("postpartum")
    return ex


def usable(action: dict, profile: dict, library: list[dict]) -> bool:
    if action["level"] > max_level_for(profile):
        return False
    if action.get("equipment") == "band" and not POPULATIONS.get(profile.get("population", ""), {}).get("allow_band"):
        return False
    if set(action.get("contra", [])) & excluded(profile):
        return False
    if "walk" in action["modules"]:
        return False
    return True


def score(action: dict, profile: dict) -> float:
    pop_id = profile.get("population", "office")
    goal = GOALS.get(profile.get("goal", ""), {})
    s = 0.0
    if pop_id in action.get("populations", []):
        s -= 0.6
    if set(action["modules"]) & set(goal.get("modules", [])):
        s -= 0.5
    s += (action["level"] - 1) * 0.7
    s += action["minutes"] * 0.15
    return s


def ordered_modules(profile: dict) -> list[str]:
    mods: list[str] = []
    for issue in profile.get("issues", []):
        mods.extend(ISSUES.get(issue, {}).get("modules", []))
    mods.extend(GOALS.get(profile.get("goal", ""), {}).get("modules", []))
    pop = POPULATIONS.get(profile.get("population", "office"), {})
    mods.extend(pop.get("modules", []))
    return list(dict.fromkeys(mods))


def safe_plan() -> dict:
    library = {a["id"]: a for a in load_library()}
    items = []
    for aid, dose in (("w1", "10–15 分钟，能说话的速度"),
                      ("b1", "10 次呼吸 × 2 组"),
                      ("p3", "8–10 次（轻柔，不追幅度）")):
        a = dict(library[aid])
        a["dose_display"] = dose
        items.append(a)
    order = {p[0]: i for i, p in enumerate(PHASES)}
    items.sort(key=lambda a: order[phase_of(a)])
    return {
        "mode": "safe",
        "items": items,
        "minutes": 14,
        "modules": ["walk", "breath"],
        "issues": [],
        "notes": [
            "档案里有安全筛查项，因此本次不安排强化训练，只保留呼吸、活动和步行。",
            "这类情况（持续疼痛、麻木、术后、孕产）需要先由医生或线下康复师确认能不能练。",
            "排查清楚、症状稳定后，再回到常规方案。",
        ],
    }


def build_plan(profile: dict, adjust: str | None = None) -> dict:
    profile = normalize_profile(profile)
    if profile["red_flags"]:
        return safe_plan()

    library = load_library()
    budget = profile["minutes"]
    target_count = TARGET_COUNT.get(budget, 6)
    used: set[str] = set()
    items: list[dict] = []
    notes: list[str] = []

    # 1) 互斥：骨盆前倾 / 后倾 只能保留一个
    issues = list(profile["issues"])
    if "ant" in issues and "post" in issues:
        keep = "ant" if profile["goal"] == "back" else ("ant" if issues.index("ant") < issues.index("post") else "post")
        drop = "post" if keep == "ant" else "ant"
        issues = [i for i in issues if i != drop]
        notes.append(
            f"「{ISSUES[drop]['name']}」和「{ISSUES[keep]['name']}」不会同时存在，"
            f"已按勾选顺序保留「{ISSUES[keep]['name']}」。如果判断错了，请回到建档修改。"
        )
    profile["issues"] = issues

    mods = ordered_modules(profile)
    minutes_of = lambda arr: sum(a["minutes"] for a in arr)

    def pick(module: str, kind: str) -> dict | None:
        pool = [a for a in library
                if module in a["modules"] and a["type"] == kind
                and usable(a, profile, library) and a["id"] not in used]
        pool.sort(key=lambda a: score(a, profile))
        return pool[0] if pool else None

    # 2) 逐模块：1 放松 + 1 强化，预算允许再补第 2 个强化
    for m in mods:
        if len(items) >= target_count:
            break
        r = pick(m, "relax")
        if r and minutes_of(items) + r["minutes"] <= budget + 1:
            used.add(r["id"]); items.append(r)
        t = pick(m, "train")
        if t and len(items) < target_count and minutes_of(items) + t["minutes"] <= budget + 1:
            used.add(t["id"]); items.append(t)

    # 3) 预算有余：补足动作数，松紧交替
    guard = 0
    while len(items) < target_count and guard < 40:
        guard += 1
        pool = [a for a in library
                if set(a["modules"]) & set(mods) and usable(a, profile, library) and a["id"] not in used]
        relax_n = sum(1 for a in items if a["type"] == "relax")
        train_n = len(items) - relax_n
        prefer = "train" if train_n < relax_n else "relax"
        if prefer == "train" and not any(a["type"] == "train" for a in pool if a["id"] not in used):
            break
        if prefer == "relax" and train_n and (relax_n + 1) / train_n > 1.6:
            break
        pool.sort(key=lambda a: (0 if a["type"] == prefer else 1, score(a, profile)))
        nxt = next((a for a in pool if minutes_of(items) + a["minutes"] <= budget + 1), None)
        if not nxt:
            break
        used.add(nxt["id"]); items.append(nxt)

    # 4) 收尾呼吸
    if len(items) < target_count and not any("breath" in a["modules"] for a in items):
        b = next((a for a in library if a["id"] == "b1" and usable(a, profile, library)), None)
        if b and minutes_of(items) + b["minutes"] <= budget + 2:
            items.append(b)

    # 5) 排序：放松 → 激活 → 强化 → 收尾
    order = {p[0]: i for i, p in enumerate(PHASES)}
    items.sort(key=lambda a: order[phase_of(a)])

    # 6) 剂量调整
    for a in items:
        a["dose_display"] = adjust_dose(a["dose"], adjust) if adjust else a["dose"]

    total = round(minutes_of(items) + len(items) * 0.4)

    pop_name = POPULATIONS[profile["population"]]["name"]
    goal_name = GOALS[profile["goal"]]["name"]
    notes.insert(0, f"你属于「{pop_name}」，目标「{goal_name}」，单次 {budget} 分钟，"
                    f"所以排了 {len(items)} 个动作、约 {total} 分钟。")
    notes.append("顺序固定为「放松 → 激活 → 强化 → 收尾」：先松开紧张肌，再唤醒薄弱肌，最后用呼吸降回静息。")
    if "neck" in mods and "shoulder" in mods:
        notes.append("颈和肩背一起排：头前伸与圆肩互相加重，分开练容易反复。")
    if profile["goal"] == "back" and "pelvis" in mods:
        notes.append("你有腰背诉求，所以骨盆与核心放在强化段，先求稳再求强。")
    if adjust == "up":
        notes.append("按反馈加量：每个动作多 1 组，动作质量下降就退回原剂量。")
    if adjust == "down":
        notes.append("按反馈减量：先保证动作标准、疼痛不加重，再考虑加回去。")

    return {
        "mode": "light" if adjust == "down" else "standard",
        "items": items,
        "minutes": total,
        "modules": mods,
        "issues": issues,
        "notes": notes,
    }


def normalize_profile(profile: dict) -> dict:
    p = {
        "population": profile.get("population", "office"),
        "goal": profile.get("goal", "look"),
        "minutes": int(profile.get("minutes", 15)),
        "days_per_week": int(profile.get("days_per_week", POPULATIONS.get(profile.get("population", "office"), {}).get("days", 4))),
        "issues": list(profile.get("issues", [])),
        "red_flags": list(profile.get("red_flags", [])),
    }
    if p["population"] not in POPULATIONS:
        raise SystemExit(f"未知人群: {p['population']}，可选: {', '.join(POPULATIONS)}")
    if p["goal"] not in GOALS:
        raise SystemExit(f"未知目标: {p['goal']}，可选: {', '.join(GOALS)}")
    bad = [i for i in p["issues"] if i not in ISSUES]
    if bad:
        raise SystemExit(f"未知体态问题: {bad}，可选: {', '.join(ISSUES)}")
    bad = [i for i in p["red_flags"] if i not in RED_FLAGS]
    if bad:
        raise SystemExit(f"未知安全项: {bad}，可选: {', '.join(RED_FLAGS)}")
    if p["minutes"] not in TARGET_COUNT:
        p["minutes"] = min(TARGET_COUNT, key=lambda x: abs(x - p["minutes"]))
    p["days_per_week"] = max(2, min(5, p["days_per_week"]))
    return p


# ---------------------------------------------------------------- 校验

def validate(plan: dict, profile: dict) -> list[dict]:
    checks = []
    items = plan["items"]
    budget = profile["minutes"]
    total = sum(a["minutes"] for a in items) + len(items) * 0.4

    checks.append({"ok": total <= budget + 2, "title": "时长匹配",
                   "detail": f"预计 {round(total)} 分钟 ≤ 设定 {budget} 分钟"})

    order = {p[0]: i for i, p in enumerate(PHASES)}
    idx = [order[phase_of(a)] for a in items]
    checks.append({"ok": all(idx[i] <= idx[i + 1] for i in range(len(idx) - 1)),
                   "title": "顺序正确", "detail": "放松 → 激活 → 强化 → 收尾"})

    covered = [i for i in plan.get("issues", profile["issues"])
               if set(ISSUES[i]["modules"]) & {m for a in items for m in a["modules"]}]
    want = plan.get("issues", profile["issues"])
    if plan["mode"] == "safe":
        checks.append({"ok": True, "title": "问题覆盖", "detail": "安全模式下暂不做针对性训练，先完成排查"})
    else:
        checks.append({"ok": len(covered) == len(want),
                       "title": "问题覆盖",
                       "detail": f"{len(covered)}/{len(want)} 个主诉有对应动作" if want else "未勾选具体问题，按人群默认部位排"})

    lv = max_level_for(profile)
    checks.append({"ok": all(a["level"] <= lv for a in items), "title": "强度不越级",
                   "detail": f"最高难度不超过 {lv} 级"})

    ex = excluded(profile)
    bad = [a for a in items if set(a.get("contra", [])) & ex]
    checks.append({"ok": not bad, "title": "禁忌已排除",
                   "detail": "无冲突动作" if not bad else f"{len(bad)} 个动作需替换"})

    if plan["mode"] == "safe":
        checks.append({"ok": not any(a["type"] == "train" for a in items),
                       "title": "安全模式无强化", "detail": "仅呼吸 / 活动 / 步行"})
    else:
        relax = [a for a in items if a["type"] == "relax"]
        train = [a for a in items if a["type"] == "train"]
        ratio = (len(relax) / len(train)) if train else 99
        checks.append({"ok": 0.4 <= ratio <= 1.6, "title": "松紧配比",
                       "detail": f"放松 {len(relax)} / 强化 {len(train)}"})

    ids = [a["id"] for a in items]
    checks.append({"ok": len(ids) == len(set(ids)), "title": "无重复动作",
                   "detail": f"{len(ids)} 个动作均不重复"})

    return checks


def suggest_adjustment(checkins: list[dict]) -> dict:
    """按最近打卡给下一次的调整建议。"""
    recent = checkins[-7:]
    if not recent:
        return {"action": "keep", "reason": "还没有打卡记录，先完成一次再谈调整。"}
    rate = sum(c.get("done", 0) for c in recent) / max(1, sum(c.get("total", 1) for c in recent))
    pain = sum(c.get("pain", 0) for c in recent) / len(recent)
    if pain >= 4:
        return {"action": "down", "reason": f"近 {len(recent)} 次平均疼痛 {pain:.1f}，先减量，疼痛降到 2 分以下再加。"}
    if rate >= 0.8 and pain <= 2:
        return {"action": "up", "reason": f"完成率 {rate:.0%}、平均疼痛 {pain:.1f}，可以每个动作加 1 组。"}
    if rate < 0.5:
        return {"action": "keep", "reason": f"完成率 {rate:.0%} 偏低，先把单次改成 10 分钟，保证每天都做。"}
    return {"action": "keep", "reason": f"完成率 {rate:.0%}、平均疼痛 {pain:.1f}，维持当前剂量。"}


# ---------------------------------------------------------------- 输出

def render_markdown(plan: dict, profile: dict) -> str:
    pop = POPULATIONS[profile["population"]]["name"]
    goal = GOALS[profile["goal"]]["name"]
    issues = "、".join(ISSUES[i]["name"] for i in profile["issues"]) or "未勾选"
    flags = "、".join(RED_FLAGS[f] for f in profile["red_flags"]) or "无"
    mode = {"standard": "常规版", "light": "减量版", "safe": "安全模式"}[plan["mode"]]

    out = [f"> {SAFETY}", "", "# 体态训练方案（{mode}）".replace("{mode}", mode), ""]
    out += [f"- 人群：{pop}", f"- 目标：{goal}", f"- 单次：{plan['minutes']} 分钟｜每周 {profile['days_per_week']} 天",
            f"- 体态问题：{issues}", f"- 安全筛查：{flags}", ""]

    grouped = {p[0]: [] for p in PHASES}
    for a in plan["items"]:
        grouped[phase_of(a)].append(a)

    out.append("## 训练清单")
    out.append("")
    n = 0
    for pid, name, note in PHASES:
        if not grouped[pid]:
            continue
        out.append(f"### {name}（{note}）")
        out.append("")
        for a in grouped[pid]:
            n += 1
            out.append(f"{n}. **{a['name']}**｜{PHASE_LABEL[phase_of(a)]}")
            out.append(f"   - 目标：{a['target']}")
            out.append(f"   - 剂量：{a.get('dose_display', a['dose'])}")
            out.append(f"   - 做法：{a['how']}")
            out.append(f"   - 易错：{a['mistake']}")
        out.append("")

    out.append("## 编排理由")
    out.append("")
    for note in plan["notes"]:
        out.append(f"- {note}")
    out.append("")

    out.append("## 合理性自检")
    out.append("")
    for c in validate(plan, profile):
        out.append(f"- {'✓' if c['ok'] else '⚠'} **{c['title']}**：{c['detail']}")
    out.append("")

    out.append("## 本周安排")
    out.append("")
    out.append(render_week(profile, plan))
    out.append("")
    out.append("> 训练中出现麻木、放射痛、头晕或关节刺痛，立即停止；持续疼痛请先就医。")
    return "\n".join(out)


def render_week(profile: dict, plan: dict) -> str:
    days = profile["days_per_week"]
    slots = {2: ["一", "四"], 3: ["一", "三", "五"], 4: ["一", "二", "四", "五"],
             5: ["一", "二", "三", "四", "五"]}[days]
    focus = " + ".join(MODULE_NAMES[m] for m in plan["modules"] if m in MODULE_NAMES)[:60]
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    lines = []
    for i, d in enumerate(weekdays):
        if d in slots:
            if i > 0 and weekdays[i - 1] in slots:
                lines.append(f"- 周{d}：轻量版（前一天练过），只做放松 + 激活段，约 6 分钟")
            else:
                lines.append(f"- 周{d}：全套训练，{focus}，约 {plan['minutes']} 分钟")
        elif d == "六":
            lines.append("- 周六：主动恢复，步行 20–30 分钟 + 任选 2 个拉伸")
        else:
            lines.append(f"- 周{d}：休息")
    lines += ["", "连续两天训练时，第二天只做放松 + 激活段，避免同一部位堆量。", ""]
    lines += ["**4 周递进**：第 1 周建立动作模式 → 第 2 周每个动作 +1 组 → 第 3 周加次数或换高一阶 → "
                  "第 4 周减量到 60% 后进入下一周期。"]
    return "\n".join(lines)


def dump_library() -> str:
    acts = load_library()
    out = ["# 动作库（自动生成，勿手改）", "",
           "> 由 `python scripts/plan_builder.py --dump-library` 从 `scripts/actions.json` 生成。", "",
           "| ID | 动作 | 类型 | 难度 | 时长 | 目标位置 | 剂量 | 易错 | 部位 |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for a in acts:
        out.append("| {id} | {name} | {type} | L{level} | {minutes} 分 | {target} | {dose} | {mistake} | {mods} |".format(
            id=a["id"], name=a["name"], type="放松" if a["type"] == "relax" else "强化",
            level=a["level"], minutes=a["minutes"], target=a["target"], dose=a["dose"],
            mistake=a["mistake"], mods="、".join(MODULE_NAMES.get(m, m) for m in a["modules"])))
    return "\n".join(out)


# ---------------------------------------------------------------- 自检

SELFTEST_PROFILES = [
    {"name": "办公久坐·外观", "profile": {"population": "office", "goal": "look", "minutes": 15,
                                        "days_per_week": 4, "issues": ["head", "round", "ant"], "red_flags": []}},
    {"name": "办公久坐·颈肩", "profile": {"population": "office", "goal": "neck", "minutes": 10,
                                        "days_per_week": 3, "issues": ["head"], "red_flags": []}},
    {"name": "学生·短时", "profile": {"population": "student", "goal": "look", "minutes": 10,
                                     "days_per_week": 4, "issues": ["round", "shoulder"], "red_flags": []}},
    {"name": "产后恢复", "profile": {"population": "postpartum", "goal": "recover", "minutes": 15,
                                    "days_per_week": 3, "issues": ["ant"], "red_flags": []}},
    {"name": "中老年", "profile": {"population": "senior", "goal": "back", "minutes": 10,
                                  "days_per_week": 3, "issues": ["foot"], "red_flags": []}},
    {"name": "久站族", "profile": {"population": "standing", "goal": "back", "minutes": 15,
                                  "days_per_week": 4, "issues": ["foot", "leg"], "red_flags": []}},
    {"name": "健身者", "profile": {"population": "active", "goal": "sport", "minutes": 30,
                                  "days_per_week": 5, "issues": ["round", "ant"], "red_flags": []}},
    {"name": "安全模式", "profile": {"population": "office", "goal": "look", "minutes": 15,
                                    "days_per_week": 4, "issues": ["head"], "red_flags": ["numb"]}},
    {"name": "互斥骨盆", "profile": {"population": "office", "goal": "look", "minutes": 15,
                                    "days_per_week": 4, "issues": ["post", "ant"], "red_flags": []}},
]


def selftest() -> int:
    failed = 0
    for case in SELFTEST_PROFILES:
        profile = normalize_profile(case["profile"])
        plan = build_plan(case["profile"])
        checks = validate(plan, profile)
        bad = [c for c in checks if not c["ok"]]
        flag = "PASS" if not bad else "FAIL"
        print(f"[{flag}] {case['name']}: {len(plan['items'])} 动作 / {plan['minutes']} 分钟 / {plan['mode']}")
        for c in bad:
            print(f"   ⚠ {c['title']}: {c['detail']}")
        failed += len(bad)
    # 加减量
    base = {"population": "office", "goal": "look", "minutes": 15, "issues": ["head", "round"], "red_flags": []}
    up = build_plan(base, "up")
    down = build_plan(base, "down")
    print("[INFO] 加量示例:", ", ".join(a["dose_display"] for a in up["items"][:3]))
    print("[INFO] 减量示例:", ", ".join(a["dose_display"] for a in down["items"][:3]))
    print("[INFO] 调整建议:", suggest_adjustment([{"done": 5, "total": 6, "pain": 1}]))
    return 1 if failed else 0


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="体态训练方案生成器")
    ap.add_argument("--profile", help="档案 JSON 路径")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--out", help="输出文件路径（默认打印到 stdout）")
    ap.add_argument("--adjust", choices=["up", "down"], help="加量 / 减量")
    ap.add_argument("--dump-library", action="store_true", help="输出动作库 Markdown")
    ap.add_argument("--selftest", action="store_true", help="跑内置档案自检")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.dump_library:
        text = dump_library()
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0
    if not args.profile:
        ap.error("需要 --profile，或使用 --selftest / --dump-library")

    raw = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    profile = normalize_profile(raw)
    plan = build_plan(raw, args.adjust)

    if args.format == "json":
        payload = {
            "profile": profile,
            "plan": plan,
            "checks": validate(plan, profile),
            "suggestion": suggest_adjustment([]),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = render_markdown(plan, profile)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写入 {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
