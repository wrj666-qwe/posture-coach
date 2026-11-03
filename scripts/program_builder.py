#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""力量 / 体能训练计划生成器。

输入一份训练档案 JSON，输出一周可执行的训练计划：分化、动作、组次、
强度（RPE）、休息、教学要点、进阶与减载，并附合理性自检。

设计原则见 references/training-principles.md。

用法:
    python program_builder.py --profile p.json
    python program_builder.py --profile p.json --format json --out plan.json
    python program_builder.py --profile p.json --posture          # 末尾加体态矫正
    python program_builder.py --dump-library
    python program_builder.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
STRENGTH_PATH = BASE / "strength_exercises.json"
POSTURE_PATH = BASE / "actions.json"

SAFETY = ("⚠ 安全提示：本计划仅作训练参考，不替代现场指导与医疗建议。"
          "若有心血管疾病、未控制高血压、关节持续疼痛、术后或孕期，请先咨询医生/康复师再训练。")

GOALS = {
    "muscle":   {"name": "增肌",   "rep": "8–12", "rpe": "7",   "rest": "90 秒",  "cardio": "2 次 × 20 分钟"},
    "strength": {"name": "力量",   "rep": "3–6",  "rpe": "8",   "rest": "150 秒", "cardio": "1–2 次 × 15 分钟"},
    "fat":      {"name": "减脂",   "rep": "10–15", "rpe": "7",  "rest": "60 秒",  "cardio": "3 次 × 25 分钟"},
    "health":   {"name": "健康体能", "rep": "10–12", "rpe": "6", "rest": "75 秒",  "cardio": "3 次 × 20 分钟"},
}

LEVELS = {
    "beginner":     {"name": "新手",  "max_level": 1, "sets": 3, "volume": (3, 16),  "step": "每 2 周 +1 组"},
    "intermediate": {"name": "中级",  "max_level": 2, "sets": 3, "volume": (5, 20),  "step": "每周 +1 次或 +1 组"},
    "advanced":     {"name": "进阶",  "max_level": 3, "sets": 4, "volume": (8, 24),  "step": "每周 +2.5% 重量"},
}

# 每周训练日的动作模式分配
SPLITS = {
    2: [["squat", "push_h", "pull_h", "core"],
        ["hinge", "push_v", "pull_v", "core"]],
    3: [["squat", "push_h", "pull_h"],
        ["hinge", "push_v", "pull_v", "core"],
        ["lunge", "push_h", "pull_h", "core"]],
    4: [["push_h", "push_v", "pull_h", "arms"],
        ["squat", "hinge", "core"],
        ["pull_h", "pull_v", "push_h", "arms"],
        ["lunge", "hinge", "core", "calf"]],
    5: [["push_h", "push_v", "arms"],
        ["pull_h", "pull_v", "arms"],
        ["squat", "hinge", "core"],
        ["push_h", "pull_h", "core"],
        ["lunge", "hinge", "calf"]],
}

DAY_NAMES = {
    2: ["周一", "周四"],
    3: ["周一", "周三", "周五"],
    4: ["周一", "周二", "周四", "周五"],
    5: ["周一", "周二", "周三", "周五", "周六"],
}

RED_FLAGS = {
    "heart": "心血管疾病",
    "hypertension": "未控制的高血压",
    "surgery": "近 6 个月手术",
    "pregnancy": "孕期",
    "acute_pain": "关节急性疼痛 / 肿胀",
}

INJURY_LABEL = {
    "knee": "膝", "back": "腰背", "shoulder": "肩",
    "wrist": "手腕", "ankle": "踝",
}

MUSCLE_GROUPS = ["股四头肌", "臀大肌", "腘绳肌", "背阔肌", "胸大肌",
                 "三角肌前束", "三角肌中束", "后三角", "中斜方", "核心"]

PUSH_MUSCLES = {"胸大肌", "三角肌前束"}
PULL_MUSCLES = {"背阔肌", "中斜方", "菱形肌", "后三角", "斜方肌"}

# 不同动作库里同一肌群的写法归一，避免容量被拆散
MUSCLE_ALIAS = {
    "腹横肌": "核心", "腹直肌": "核心", "腹斜肌": "核心",
    "斜方肌": "中斜方", "菱形肌": "中斜方", "肩袖": "后三角",
}


# ---------------------------------------------------------------- 数据

def load_exercises() -> list[dict]:
    return json.loads(STRENGTH_PATH.read_text(encoding="utf-8"))["exercises"]


def load_posture() -> list[dict]:
    return json.loads(POSTURE_PATH.read_text(encoding="utf-8"))["actions"]


VIDEO_INDEX = BASE.parent / "assets" / "videos" / "videos.json"


def video_links() -> dict[str, str]:
    """动作名 -> 视频链接（没有视频索引时返回空字典）。"""
    if not VIDEO_INDEX.exists():
        return {}
    try:
        data = json.loads(VIDEO_INDEX.read_text(encoding="utf-8"))
        return {it["name"]: it["links"][0]["url"] for it in data.get("items", []) if it.get("links")}
    except Exception:
        return {}


def equipment_allowed(profile: dict) -> set[str]:
    own = set(profile.get("equipment", []) or [])
    if "gym" in own:
        return {"none", "band", "dumbbell", "gym", "kettlebell"}
    return own | {"none"}


def blocked_tags(profile: dict) -> set[str]:
    tags = set(profile.get("injuries", []) or [])
    tags |= set(profile.get("red_flags", []) or [])
    return tags


def usable(ex: dict, profile: dict) -> bool:
    if ex["level"] > LEVELS[profile["level"]]["max_level"]:
        return False
    if not (set(ex["equipment"]) & equipment_allowed(profile)):
        return False
    if set(ex.get("contra", [])) & blocked_tags(profile):
        return False
    return True


REST_FACTOR = {"strength": 3.0, "muscle": 2.2, "fat": 1.6, "health": 1.9}


def estimate_minutes(ex: dict, goal: str = "muscle") -> int:
    # 按目标估算单动作耗时：组数 × 每组含休息的分钟 + 准备
    return max(4, round(ex["sets"] * REST_FACTOR.get(goal, 2.2) + 1))


# ---------------------------------------------------------------- 生成

def build_program(profile: dict) -> dict:
    profile = normalize_profile(profile)
    if profile["red_flags"]:
        return safe_program(profile)

    exs = load_exercises()
    level = LEVELS[profile["level"]]
    days = profile["days"]
    split = SPLITS[days]
    names = DAY_NAMES[days]
    goal = GOALS[profile["goal"]]

    used_ids: set[str] = set()
    weekly: dict[str, float] = {}
    cap = {"beginner": 14, "intermediate": 18, "advanced": 22}[profile["level"]]
    sessions = []
    for di, patterns in enumerate(split):
        session = build_session(patterns, exs, profile, used_ids, di, weekly, cap)
        session["day"] = names[di]
        session["index"] = di + 1
        sessions.append(session)

    program = {
        "mode": "standard",
        "goal": profile["goal"],
        "level": profile["level"],
        "sessions": sessions,
        "days": days,
        "minutes": profile["minutes"],
        "cardio": goal["cardio"],
        "notes": [
            f"目标是「{goal['name']}」，{LEVELS[profile['level']]['name']}水平，每周 {days} 天，"
            f"每次约 {profile['minutes']} 分钟。",
            "每次训练结构固定：热身 5 分钟 → 主动作（大肌群、多关节）→ 辅助动作 → 核心 → 放松 4 分钟。",
            "主动作放在最前面，因为体力最好；技术难度高的动作不要放到最后。",
        ],
    }

    if profile.get("posture_focus"):
        program["posture"] = pick_posture(profile)
        # 圆肩 / 头前伸的人，拉要明显多于推，否则越练越前扣
        if {"neck", "shoulder"} & set(profile["posture_focus"]):
            exs = load_exercises()
            if push_pull_ratio(muscle_sets(sessions)) < 1.3:
                face = next((e for e in exs if e["id"] == "ar_facepull"), None)
                if face:
                    target = min(sessions, key=lambda s: s["minutes"])
                    item = dict(face)
                    item["sets"] = 3
                    item["reps"] = "15"
                    item["rpe"] = "6"
                    item["rest"] = "45 秒"
                    target["exercises"].append(item)
                    target["minutes"] += 4
                    program["notes"].append("你的体态诉求包含圆肩/头前伸，所以额外补了一组面拉，把拉的量抬上去。")
        for s in sessions:
            s["minutes"] += 5
        program["notes"].append("每次训练末尾加 5 分钟体态矫正，放在放松之前做；休息日也可以单独做一次。")
    return program


def muscle_sets(sessions: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for s in sessions:
        for e in s["exercises"]:
            for m in e["primary"]:
                out[m] = out.get(m, 0) + e["sets"]
    return out


def push_pull_ratio(sets: dict[str, float]) -> float:
    push = sum(v for k, v in sets.items() if k in PUSH_MUSCLES)
    pull = sum(v for k, v in sets.items() if k in PULL_MUSCLES)
    return (pull / push) if push else 99.0


def build_session(patterns, exs, profile, used_ids, di, weekly, cap) -> dict:
    budget = profile["minutes"]
    level = LEVELS[profile["level"]]
    goal = GOALS[profile["goal"]]

    main: list[dict] = []
    minutes = 5 + 4  # 热身 + 放松
    daily: dict[str, float] = {}

    def fits(e) -> bool:
        for m in e["primary"]:
            m2 = MUSCLE_ALIAS.get(m, m)
            if weekly.get(m2, 0) + e["sets"] > cap:
                return False
            if daily.get(m2, 0) + e["sets"] > 8:   # 单日同肌群不超过 8 组
                return False
        return True

    def commit(e):
        for m in e["primary"]:
            m2 = MUSCLE_ALIAS.get(m, m)
            weekly[m2] = weekly.get(m2, 0) + e["sets"]
            daily[m2] = daily.get(m2, 0) + e["sets"]
        used_ids.add(e["id"])
        main.append(e)

    pref = level["max_level"]

    def rank(e):
        # 越接近本水平上限越优先，避免进阶者拿到最基础的动作
        return (abs(e["level"] - pref), e["level"], e["equipment"] != "none")

    for pattern in patterns:
        candidates = [e for e in exs
                      if e["pattern"] == pattern and usable(e, profile) and e["id"] not in used_ids]
        candidates.sort(key=rank)
        if not candidates:
            continue
        ex = dict(candidates[0])
        ex["sets"] = level["sets"] if ex["pattern"] not in ("conditioning", "core") else ex["sets"]
        if ex["pattern"] == "core":
            ex["sets"] = 3
        # 时间型动作（平板、农夫走、心肺）保留原剂量，不套用次数区间
        if not any(k in str(ex["reps"]) for k in ("秒", "分钟", "米")):
            ex["reps"] = goal["rep"]
        ex["rest"] = goal["rest"] if ex["pattern"] not in ("core", "calf", "conditioning") else ex["rest"]
        ex["rpe"] = goal["rpe"] if ex["pattern"] not in ("core", "calf", "conditioning") else ex["rpe"]
        cost = estimate_minutes(ex, profile["goal"])
        if minutes + cost > budget + 3 or not fits(ex):
            continue
        commit(ex)
        minutes += cost

    # 补足到时间预算：同一动作模式一天只排一次，优先小肌群
    pats = {e["pattern"] for e in main}
    fill = ["arms", "calf", "carry", "core"]
    guard = 0
    while minutes < profile["minutes"] - 4 and len(main) < 8 and guard < 20:
        guard += 1
        pool = [e for e in exs
                if e["pattern"] in fill and e["pattern"] not in pats
                and usable(e, profile) and e["id"] not in used_ids]
        pool.sort(key=rank)
        if not pool:
            break
        ex = pool[0]
        e = dict(ex)
        e["sets"] = 3 if e["pattern"] == "core" else LEVELS[profile["level"]]["sets"]
        cost = estimate_minutes(e, profile["goal"])
        if minutes + cost > profile["minutes"] or not fits(e):
            break
        commit(e)
        minutes += cost
        pats.add(e["pattern"])

    # 时间还有余量：给大肌群补第二个动作（同模式、不同动作），最多 7 个
    for pattern in patterns:
        if pattern in ("core", "calf", "carry", "conditioning"):
            continue
        if len(main) >= 7 or minutes >= profile["minutes"] - 5:
            break
        if sum(1 for x in main if x["pattern"] == pattern) >= 2:
            continue
        cand = [e for e in exs
                if e["pattern"] == pattern and usable(e, profile) and e["id"] not in used_ids]
        if not cand:
            continue
        cand.sort(key=rank)
        e = dict(cand[0])
        e["sets"] = LEVELS[profile["level"]]["sets"]
        if not any(k in str(e["reps"]) for k in ("秒", "分钟", "米")):
            e["reps"] = goal["rep"]
        e["rest"] = goal["rest"]
        e["rpe"] = goal["rpe"]
        cost = estimate_minutes(e, profile["goal"])
        if minutes + cost > profile["minutes"] or not fits(e):
            continue
        commit(e)
        minutes += cost

    # 兜底：任何一次训练至少 3 个动作，宁可略超周容量也不给空计划
    guard = 0
    while len(main) < 3 and guard < 12:
        guard += 1
        pool = [e for e in exs if usable(e, profile) and e["id"] not in used_ids]
        if not pool:
            break
        pool.sort(key=lambda e: (
            sum(weekly.get(MUSCLE_ALIAS.get(m, m), 0) for m in e["primary"]), e["level"]))
        e = dict(pool[0])
        e["sets"] = 3
        cost = estimate_minutes(e, profile["goal"])
        if minutes + cost > budget + 5:
            break
        commit(e)
        minutes += cost

    return {
        "theme": " + ".join(sorted({pattern_name(p) for p in patterns})),
        "exercises": main,
        "minutes": minutes,
        "warmup": "5 分钟：快走/开合跳 2 分钟 + 关节绕环 + 空手做 1 组主动作",
        "cooldown": "4 分钟：练到的部位各拉伸 20–30 秒",
    }


def pattern_name(p: str) -> str:
    return {"squat": "蹲", "hinge": "髋", "lunge": "单腿", "push_h": "水平推", "push_v": "垂直推",
            "pull_h": "水平拉", "pull_v": "垂直拉", "core": "核心", "carry": "负重行走",
            "arms": "手臂", "calf": "小腿", "conditioning": "心肺"}.get(p, p)


def safe_program(profile: dict) -> dict:
    return {
        "mode": "safe",
        "goal": profile["goal"],
        "level": profile["level"],
        "sessions": [],
        "days": profile["days"],
        "minutes": profile["minutes"],
        "cardio": "医生允许前只做步行",
        "notes": [
            "档案里有需要先排除的情况，所以这次不给力量训练计划。",
            "先完成医学评估（心血管 / 骨科 / 康复科），确认可以训练后再说强度。",
            "在此之前只建议：低强度步行（能说话的速度）、呼吸练习，出现胸闷头晕立即停止。",
        ],
    }


POSTURE_PRIORITY = {
    "neck": ["n4", "n1", "n2"],
    "shoulder": ["s4", "s1", "s2"],
    "pelvis": ["p4", "p1", "p7"],
    "pelvis_post": ["p10", "p9", "p7"],
    "lower": ["l1", "l4", "l2"],
    "foot": ["f1", "f3", "l5"],
}


def pick_posture(profile: dict) -> list[dict]:
    """从体态动作库挑 3 个作收尾：至少 1 个放松 + 1 个强化，遵守禁忌。"""
    focus = set(profile.get("posture_focus", []) or [])
    if not focus:
        return []
    actions = load_posture()
    ex = set(profile.get("injuries", []) or []) | set(profile.get("red_flags", []) or [])
    pool = [a for a in actions
            if a["modules"] and set(a["modules"]) & focus
            and a["level"] <= 2
            and not (set(a.get("contra", [])) & ex)]
    prio: list[str] = []
    for f in profile["posture_focus"]:
        prio.extend(POSTURE_PRIORITY.get(f, []))
    pool.sort(key=lambda a: (prio.index(a["id"]) if a["id"] in prio else 99,
                             a["level"], a["minutes"]))
    by_id = {a["id"]: a for a in pool}

    # 每个诉求轮流取 1 个，保证颈和肩各有一个
    chosen, seen = [], set()
    lists = [POSTURE_PRIORITY.get(f, []) for f in profile["posture_focus"]]
    for _ in range(3):
        for lst in lists:
            if len(chosen) >= 3:
                break
            for pid in lst:
                a = by_id.get(pid)
                if a and a["id"] not in seen:
                    seen.add(a["id"])
                    chosen.append(a)
                    break
    for a in pool:
        if len(chosen) >= 3:
            break
        if a["id"] not in seen:
            seen.add(a["id"])
            chosen.append(a)

    picked = chosen

    out = []
    for a in picked:
        item = dict(a)
        item["dose_display"] = a["dose"]
        out.append(item)
    out.sort(key=lambda a: a["type"] != "relax")
    return out


def normalize_profile(profile: dict) -> dict:
    p = {
        "goal": profile.get("goal", "health"),
        "level": profile.get("level", "beginner"),
        "days": int(profile.get("days", 3)),
        "minutes": int(profile.get("minutes", 45)),
        "equipment": list(profile.get("equipment", ["none"])),
        "injuries": list(profile.get("injuries", [])),
        "red_flags": list(profile.get("red_flags", [])),
        "posture_focus": list(profile.get("posture_focus", [])),
    }
    if p["goal"] not in GOALS:
        raise SystemExit(f"未知目标: {p['goal']}，可选: {', '.join(GOALS)}")
    if p["level"] not in LEVELS:
        raise SystemExit(f"未知水平: {p['level']}，可选: {', '.join(LEVELS)}")
    p["days"] = max(2, min(5, p["days"]))
    p["minutes"] = max(20, min(90, p["minutes"]))
    return p


# ---------------------------------------------------------------- 校验

def validate(program: dict, profile: dict) -> list[dict]:
    checks = []
    if program["mode"] == "safe":
        return [{"ok": True, "title": "安全模式", "detail": "已改为步行与呼吸，未安排力量训练"}]

    sessions = program["sessions"]
    checks.append({"ok": len(sessions) == profile["days"], "title": "训练日完整",
                   "detail": f"{len(sessions)}/{profile['days']} 天已排"})

    over = [s for s in sessions if s["minutes"] > profile["minutes"] + 5]
    checks.append({"ok": not over, "title": "时长匹配",
                   "detail": f"每次 ≤ {profile['minutes'] + 5} 分钟" if not over else f"{len(over)} 次超时"})

    patterns = {e["pattern"] for s in sessions for e in s["exercises"]}
    need = {"squat", "hinge", "push_h", "pull_h"}
    missing = need - patterns
    exs = load_exercises()
    unavailable = {p for p in missing
                   if not any(e["pattern"] == p and usable(e, profile) for e in exs)}
    real_missing = missing - unavailable
    if real_missing:
        detail = f"缺：{'、'.join(pattern_name(p) for p in sorted(real_missing))}"
    elif unavailable:
        detail = ("已按器械/禁忌跳过：" +
                  "、".join(f"{pattern_name(p)}（{'器械' if not any(e['pattern']==p for e in exs) else '禁忌'}）"
                            for p in sorted(unavailable)))
    else:
        detail = "蹲、髋、水平推、水平拉每周都练到"
    checks.append({"ok": not real_missing, "title": "动作模式覆盖", "detail": detail})

    # 每周组数：只看被安排为主练的肌群；低于 3 组算"练了等于没练"
    sets: dict[str, float] = {}
    for s in sessions:
        for e in s["exercises"]:
            for m in e["primary"]:
                m2 = MUSCLE_ALIAS.get(m, m)
                if m2 in MUSCLE_GROUPS:
                    sets[m2] = sets.get(m2, 0) + e["sets"]
    lo, hi = 3, LEVELS[profile["level"]]["volume"][1]
    low = {m: v for m, v in sets.items() if v < lo}
    high = {m: v for m, v in sets.items() if v > hi}
    dist = "、".join(f"{m} {v:.0f}" for m, v in sorted(sets.items(), key=lambda kv: -kv[1]))
    if not low and not high:
        detail = f"主练肌群 {dist}（组/周），均在 {lo}–{hi} 区间"
    else:
        parts = []
        if low:
            parts.append("偏低：" + "、".join(f"{m} {v:.0f}" for m, v in low.items()))
        if high:
            parts.append("偏高：" + "、".join(f"{m} {v:.0f}" for m, v in high.items()))
        detail = "；".join(parts)
    checks.append({"ok": not low and not high, "title": "每周容量", "detail": detail})

    # 推拉平衡：圆肩 / 头前伸的人，拉要明显多于推
    raw = muscle_sets(sessions)
    ratio = push_pull_ratio(raw)
    need = 1.3 if ({"neck", "shoulder"} & set(profile.get("posture_focus", []))) else 1.0
    checks.append({"ok": ratio >= need, "title": "推拉平衡",
                   "detail": f"拉 {ratio:.2f} 倍于推（要求 ≥ {need:.1f}）"
                   if ratio < 99 else "本计划无推动作，无需平衡"})

    # 体态配额
    if profile.get("posture_focus"):
        corr = program.get("posture", [])
        ok = len(corr) >= 2 and any(a["type"] == "train" for a in corr)
        checks.append({"ok": ok, "title": "体态配额",
                       "detail": f"每次训练后 {len(corr)} 个矫正动作（含 "
                                 f"{sum(1 for a in corr if a['type'] == 'train')} 个强化）"})

    checks.append({"ok": True, "title": "动作不重复",
                   "detail": f"{sum(len(s['exercises']) for s in sessions)} 个动作位，同一天不重复"})

    blocked = blocked_tags(profile)
    all_ex = [e for s in sessions for e in s["exercises"]]
    conflict = [e for e in all_ex if set(e.get("contra", [])) & blocked]
    checks.append({"ok": not conflict, "title": "禁忌已排除",
                   "detail": "无冲突动作" if not conflict else f"{len(conflict)} 个需替换"})

    checks.append({"ok": all(s["warmup"] and s["cooldown"] for s in sessions),
                   "title": "热身与放松", "detail": "每次都有热身和放松段"})

    checks.append({"ok": True, "title": "进阶与减载",
                   "detail": f"{LEVELS[profile['level']]['step']}；第 4 周减量到 60%"})
    return checks


# ---------------------------------------------------------------- 输出

def render_markdown(program: dict, profile: dict) -> str:
    out = [f"> {SAFETY}", ""]
    g = GOALS[profile["goal"]]["name"]
    lv = LEVELS[profile["level"]]["name"]
    eq = "、".join({"none": "徒手", "band": "弹力带", "dumbbell": "哑铃", "gym": "健身房"}.get(e, e)
                   for e in profile["equipment"]) or "徒手"
    out += [f"# 训练计划 · {g}（{lv}）", "",
            f"- 目标：{g}｜水平：{lv}｜每周 {program['days']} 天｜每次约 {profile['minutes']} 分钟",
            f"- 器械：{eq}",
            f"- 心肺：{program['cardio']}",
            f"- 禁忌：{'、'.join(INJURY_LABEL.get(i, i) for i in profile['injuries']) or '无'}",
            ""]

    if program["mode"] == "safe":
        out += ["## 先别急着练", ""] + [f"- {n}" for n in program["notes"]]
        return "\n".join(out)

    out += ["## 本周概览", "", "| 日 | 主题 | 动作数 | 预计 |", "| --- | --- | --- | --- |"]
    for s in program["sessions"]:
        out.append(f"| {s['day']} | {s['theme']} | {len(s['exercises'])} | {s['minutes']} 分钟 |")
    out.append("")

    for s in program["sessions"]:
        out.append(f"## {s['day']}｜{s['theme']}")
        out.append("")
        out.append(f"**热身**　{s['warmup']}")
        out.append("")
        out.append("| 动作 | 组 × 次 | RPE | 休息 | 主练 | 视频 |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        vids = video_links()
        for e in s["exercises"]:
            url = vids.get(e["name"])
            cell = f"[▶ 看视频]({url})" if url else "—"
            out.append(f"| {e['name']} | {e['sets']} × {e['reps']} | {e['rpe']} | {e['rest']} | "
                       f"{'、'.join(e['primary'])} | {cell} |")
        out.append("")
        out.append("**教学要点**")
        for e in s["exercises"]:
            url = vids.get(e["name"])
            link = f"　[▶ 看视频]({url})" if url else ""
            out.append(f"- **{e['name']}**：{'；'.join(e['cue'])}。易错：{e['mistake']}。教法：{e['teach']}{link}")
        out.append("")
        out.append(f"**放松**　{s['cooldown']}")
        out.append("")

    if program.get("posture"):
        out += ["## 体态矫正收尾（每次训练后 5 分钟，放在放松之前）", ""]
        for a in program["posture"]:
            out.append(f"- **{a['name']}**（{'放松' if a['type'] == 'relax' else '强化'}）"
                       f"｜目标：{a['target']}｜{a.get('dose_display', a['dose'])}｜易错：{a['mistake']}")
        out.append("")
        out.append("休息日也可以单独做这一组，每周至少 3 次。")
        out.append("")

    out += ["## 进阶与减载", "",
            "| 周 | 安排 |", "| --- | --- |",
            "| 第 1 周 | 按本表执行，RPE 控制在目标值以下，先把动作做标准 |",
            "| 第 2 周 | 每个动作 +1 组，或主动作 +2.5% 重量 |",
            "| 第 3 周 | 再 +2.5% 重量；动作质量下降就停在上周 |",
            "| 第 4 周 | 减载：组数降到 60%，重量降到 80%，让身体恢复 |",
            "", "同一肌群两次训练之间至少间隔 48 小时。连续两天训练时，第二天只做上肢或只做核心。", ""]

    out += ["## 合理性自检", ""]
    for c in validate(program, profile):
        out.append(f"- {'✓' if c['ok'] else '⚠'} **{c['title']}**：{c['detail']}")
    out.append("")
    out.append("> 训练中出现胸闷、头晕、关节刺痛或麻木，立即停止；持续疼痛请就医。")
    return "\n".join(out)


def dump_library() -> str:
    exs = load_exercises()
    out = ["# 力量动作库（自动生成，勿手改）", "",
           "> 由 `python scripts/program_builder.py --dump-library` 生成。", "",
           "| ID | 动作 | 模式 | 难度 | 器械 | 组次 | 主练 | 禁忌 |",
           "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for e in exs:
        out.append(f"| {e['id']} | {e['name']} | {pattern_name(e['pattern'])} | L{e['level']} | "
                   f"{'/'.join(e['equipment'])} | {e['sets']}×{e['reps']} | {'、'.join(e['primary'])} | "
                   f"{'、'.join(e.get('contra', [])) or '—'} |")
    return "\n".join(out)


# ---------------------------------------------------------------- 自检

SELFTEST = [
    {"name": "新手·增肌·3 天·徒手", "p": {"goal": "muscle", "level": "beginner", "days": 3, "minutes": 45,
                                        "equipment": ["dumbbell", "band"], "injuries": [], "red_flags": []}},
    {"name": "中级·力量·4 天·健身房", "p": {"goal": "strength", "level": "intermediate", "days": 4, "minutes": 60,
                                          "equipment": ["gym"], "injuries": [], "red_flags": []}},
    {"name": "减脂·新手·2 天·居家", "p": {"goal": "fat", "level": "beginner", "days": 2, "minutes": 30,
                                        "equipment": ["none"], "injuries": [], "red_flags": []}},
    {"name": "健康·中老年·3 天", "p": {"goal": "health", "level": "beginner", "days": 3, "minutes": 40,
                                     "equipment": ["band"], "injuries": ["knee"], "red_flags": []}},
    {"name": "进阶·5 天·肩伤", "p": {"goal": "muscle", "level": "advanced", "days": 5, "minutes": 60,
                                   "equipment": ["gym"], "injuries": ["shoulder"], "red_flags": []}},
    {"name": "带体态矫正", "p": {"goal": "muscle", "level": "beginner", "days": 3, "minutes": 50,
                               "equipment": ["dumbbell"], "injuries": [], "red_flags": [],
                               "posture_focus": ["neck", "shoulder"]}},
    {"name": "红旗拦截", "p": {"goal": "fat", "level": "beginner", "days": 3, "minutes": 30,
                             "equipment": ["none"], "injuries": [], "red_flags": ["heart"]}},
]


def selftest() -> int:
    failed = 0
    for case in SELFTEST:
        profile = normalize_profile(case["p"])
        prog = build_program(case["p"])
        checks = validate(prog, profile)
        bad = [c for c in checks if not c["ok"]]
        flag = "PASS" if not bad else "FAIL"
        n = sum(len(s["exercises"]) for s in prog["sessions"])
        print(f"[{flag}] {case['name']}: {len(prog['sessions'])} 天 / {n} 个动作位 / {prog['mode']}")
        for c in bad:
            print(f"   ⚠ {c['title']}: {c['detail']}")
        failed += len(bad)
    return 1 if failed else 0


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="力量 / 体能训练计划生成器")
    ap.add_argument("--profile")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--out")
    ap.add_argument("--posture", action="store_true", help="末尾加体态矫正")
    ap.add_argument("--dump-library", action="store_true")
    ap.add_argument("--selftest", action="store_true")
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
    if args.posture and not raw.get("posture_focus"):
        raw["posture_focus"] = ["neck", "shoulder"]
    profile = normalize_profile(raw)
    program = build_program(raw)

    if args.format == "json":
        payload = {"profile": profile, "program": program, "checks": validate(program, profile)}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = render_markdown(program, profile)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写入 {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
