#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按训练日志调整下周计划。

读一份日志（每个动作最近几次的重量/次数/RPE/疼痛），用双进阶规则给出
下一次该加重量、加次数、保持还是降阶，并把结果套回训练计划。

用法:
    python adjust_plan.py --profile p.json --log logs/train-log.json
    python adjust_plan.py --profile p.json --log logs/train-log.json --format json
    python adjust_plan.py --selftest
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import program_builder as pb  # noqa: E402

SAFETY = ("⚠ 安全提示：调整建议基于你自己记录的 RPE 与疼痛评分，"
          "不替代现场教练判断。出现麻木、放射痛、关节刺痛或胸闷，立即停止并就医。")

LABEL = {"up": "加量", "hold": "保持", "down": "降重", "swap": "换动作", "extend": "加时"}


# ---------------------------------------------------------------- 读日志

def load_log(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", data) if isinstance(data, dict) else data
    cleaned = []
    for e in entries:
        reps = e.get("reps", [])
        if isinstance(reps, (int, float)):
            reps = [int(reps)]
        cleaned.append({
            "date": str(e.get("date", "")),
            "exercise": e.get("exercise", ""),
            "weight": float(e.get("weight", 0)),
            "reps": [int(r) for r in reps],
            "rpe": float(e.get("rpe", 7)),
            "pain": float(e.get("pain", 0)),
            "note": e.get("note", ""),
        })
    cleaned.sort(key=lambda x: (x["date"], x["exercise"]))
    return cleaned


def group_by_exercise(entries: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in entries:
        out.setdefault(e["exercise"], []).append(e)
    return out


def rep_range(meta: dict | None, goal: str) -> tuple[int, int]:
    text = (meta or {}).get("reps", "")
    nums = re.findall(r"\d+", text)
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    if len(nums) == 1:
        return int(nums[0]), int(nums[0]) + 2
    lo, hi = re.split(r"[–-]", pb.GOALS[goal]["rep"])
    return int(lo), int(hi)


def is_time_based(meta: dict | None) -> bool:
    return bool(meta) and any(k in str(meta.get("reps", "")) for k in ("秒", "分钟", "米"))


def unit_of(text: str) -> str:
    for u in ("秒", "分钟", "米"):
        if u in text:
            return u
    return "秒"


def step_for(weight: float) -> float:
    if weight <= 0:
        return 0
    if weight < 20:
        return 0.5
    return max(1.0, round(weight * 0.025 * 2) / 2)


# ---------------------------------------------------------------- 规则

def decide(history: list[dict], goal: str, meta: dict | None) -> dict:
    """双进阶：先把次数做满上限且 RPE 可控，再加重量并回到下限。"""
    last, prev = history[-1], (history[-2] if len(history) > 1 else None)
    w, rpe, pain = last["weight"], last["rpe"], last["pain"]
    reps = last["reps"]
    best = max(reps) if reps else 0
    low = min(reps) if reps else 0
    target = float(pb.GOALS[goal]["rpe"])

    if pain >= 4:
        return {"action": "swap", "weight": w, "reps_text": "按医嘱或降阶",
                "reason": f"疼痛 {pain:.0f}/10，先换动作或降阶，不要加量"}

    # 时间 / 距离型：只加时长或距离，不加重量
    if is_time_based(meta):
        unit = unit_of(str(meta.get("reps", "")))
        if rpe >= 9:
            return {"action": "hold", "weight": w, "reps_text": f"{best} {unit}",
                    "reason": f"RPE {rpe:.0f} 已偏高，先稳住 {best} {unit}"}
        return {"action": "extend", "weight": w, "reps_text": f"{best}–{best + 5} {unit}",
                "reason": f"RPE {rpe:.0f} 可控，下次每组加 5 {unit}（{best} → {best + 5} {unit}）"}

    lo, hi = rep_range(meta, goal)

    if w == 0:
        if best >= hi and rpe <= target:
            start = max(hi, best)
            return {"action": "up", "weight": 0, "reps_text": f"{start}–{start + 4}",
                    "reason": f"自重已做到 {best} 次（区间上限 {hi}）、RPE {rpe:.0f}，下次每组多做 2–4 次，或换高一级变式"}
        if rpe >= 9:
            return {"action": "hold", "weight": 0, "reps_text": f"{lo}–{hi}",
                    "reason": "RPE 偏高，先稳定动作质量，不加次数"}
        return {"action": "hold", "weight": 0, "reps_text": f"{lo}–{hi}",
                "reason": "次数未到上限，继续积累"}

    if rpe >= 9:
        if prev and prev["rpe"] >= 9:
            nw = round(max(0, w * 0.95) * 2) / 2
            return {"action": "down", "weight": nw, "reps_text": f"{lo}–{hi}",
                    "reason": "连续两次 RPE ≥ 9，降 5% 重量，先把动作做标准"}
        return {"action": "hold", "weight": w, "reps_text": f"{lo}–{hi}",
                "reason": "RPE 已到 9，维持重量，不要再加"}

    if low < lo:
        nw = round(max(0, w * 0.95) * 2) / 2
        return {"action": "down", "weight": nw, "reps_text": f"{lo}–{hi}",
                "reason": f"最少一组只做了 {low} 次（低于 {lo}），重量偏大"}

    if best >= hi and rpe <= target:
        step = step_for(w)
        nw = round((w + step) * 2) / 2
        return {"action": "up", "weight": nw, "reps_text": f"{lo}–{hi}",
                "reason": f"所有组做到 {best} 次、RPE ≤ {target:.0f}，加 {step:g} kg，次数回到 {lo}"}

    return {"action": "hold", "weight": w, "reps_text": f"{lo}–{hi}",
            "reason": f"还没做满 {hi} 次，先把现有重量做满"}


def analyze(entries: list[dict], profile: dict, library: dict[str, dict]) -> list[dict]:
    rows = []
    for name, hist in group_by_exercise(entries).items():
        meta = library.get(name)
        rows.append({"exercise": name, "meta": meta, "last": hist[-1],
                     "history_n": len(hist), "decision": decide(hist, profile["goal"], meta)})
    rows.sort(key=lambda r: r["exercise"])
    return rows


def weight_label(weight: float, meta: dict | None) -> str:
    if weight > 0:
        return f"{weight:g} kg"
    if meta and "band" in meta.get("equipment", []):
        return "弹力带"
    return "自重"


# ---------------------------------------------------------------- 套回计划

def apply_to_program(program: dict, rows: list[dict]) -> dict:
    by_name = {r["exercise"]: r for r in rows}
    for s in program["sessions"]:
        for e in s["exercises"]:
            r = by_name.get(e["name"])
            if not r:
                continue
            d = r["decision"]
            e["last_weight"] = r["last"]["weight"]
            e["next_weight"] = d["weight"]
            e["adj"] = d["action"]
            if d["action"] in ("up", "down", "hold", "extend"):
                e["reps"] = d["reps_text"]
    return program


def validate_adjust(rows: list[dict]) -> list[dict]:
    checks = []
    jumps = [r for r in rows
             if r["decision"]["action"] == "up" and r["last"]["weight"] > 0
             and r["decision"]["weight"] - r["last"]["weight"] > max(1.0, r["last"]["weight"] * 0.06)]
    checks.append({"ok": not jumps, "title": "增幅合理",
                   "detail": "单次增幅 ≤ max(1 kg, 6%)" if not jumps else f"{len(jumps)} 个动作增幅过大"})

    bad = [r for r in rows if r["last"]["pain"] >= 4 and r["decision"]["action"] == "up"]
    checks.append({"ok": not bad, "title": "疼痛时不加量",
                   "detail": "疼痛 ≥ 4 的动作均未加量" if not bad else f"{len(bad)} 个动作违反"})

    high = [r for r in rows if r["last"]["rpe"] >= 9]
    checks.append({"ok": True, "title": "高 RPE 已标记",
                   "detail": f"{len(high)} 个动作 RPE ≥ 9，已保持或降重" if high else "无 RPE ≥ 9 的动作"})

    checks.append({"ok": bool(rows), "title": "日志可解析",
                   "detail": f"解析到 {len(rows)} 个动作的记录"})
    return checks


# ---------------------------------------------------------------- 输出

def render(rows: list[dict], program: dict, profile: dict) -> str:
    out = [f"> {SAFETY}", "", "# 下周训练调整", ""]
    if not rows:
        out += ["日志里还没有动作记录。先按上周计划练 2–3 次并记录，再回来调整。"]
        return "\n".join(out)

    n = len(rows)
    avg_rpe = sum(r["last"]["rpe"] for r in rows) / n
    avg_pain = sum(r["last"]["pain"] for r in rows) / n
    count = {k: sum(1 for r in rows if r["decision"]["action"] == k) for k in LABEL}

    out += [f"- 记录动作：{n} 个｜平均 RPE：{avg_rpe:.1f}｜平均疼痛：{avg_pain:.1f}",
            f"- 调整：加量 {count['up']}｜加时 {count['extend']}｜保持 {count['hold']}"
            f"｜降重 {count['down']}｜换动作 {count['swap']}", ""]

    out += ["## 逐动作判断", "",
            "| 动作 | 上次 | RPE | 判断 | 下次 |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        last, d = r["last"], r["decision"]
        reps = "/".join(str(x) for x in last["reps"]) if last["reps"] else "—"
        last_txt = f"{weight_label(last['weight'], r['meta'])} × {reps}"
        next_txt = f"{weight_label(d['weight'], r['meta'])} × {d['reps_text']}"
        out.append(f"| {r['exercise']} | {last_txt} | {last['rpe']:.0f} | {LABEL[d['action']]} | {next_txt} |")
    out.append("")

    out += ["## 为什么这么调", ""]
    for r in rows:
        out.append(f"- **{r['exercise']}**：{r['decision']['reason']}")
    out.append("")

    out += ["## 下周计划（已套用调整）", ""]
    for s in program["sessions"]:
        out.append(f"**{s['day']}｜{s['theme']}**")
        out.append("")
        out.append("| 动作 | 重量 | 组 × 次 | RPE |")
        out.append("| --- | --- | --- | --- |")
        for e in s["exercises"]:
            w = e.get("next_weight")
            label = "自重" if w is None else weight_label(w, e)
            out.append(f"| {e['name']} | {label} | {e['sets']} × {e['reps']} | {e['rpe']} |")
        out.append("")

    out += ["## 自检", ""]
    for c in validate_adjust(rows):
        out.append(f"- {'✓' if c['ok'] else '⚠'} **{c['title']}**：{c['detail']}")
    out += ["", "## 提醒", "",
            "- 加重量后第一组如果 RPE 超过 8，当天退回原重量，别硬撑。",
            "- 连续 3 周都在加量，第 4 周做减载：组数降到 60%，重量降到 80%。",
            "- 疼痛 ≥ 4 或出现麻木、放射痛，停止该动作并就医。"]
    return "\n".join(out)


# ---------------------------------------------------------------- 自检

def selftest() -> int:
    lib = {e["name"]: e for e in pb.load_exercises()}
    bench = lib["哑铃弯举"]     # 8–12 次
    plank = lib["平板支撑"]     # 时间型
    squat = lib["箱式深蹲"]     # 自重 8–10

    cases = [
        {"name": "做满上限加重", "meta": bench, "hist": [
            {"weight": 8, "reps": [12, 12, 12], "rpe": 7, "pain": 0}], "want": "up"},
        {"name": "次数不足降重", "meta": bench, "hist": [
            {"weight": 12, "reps": [6, 5, 4], "rpe": 8, "pain": 0}], "want": "down"},
        {"name": "RPE 9 保持", "meta": bench, "hist": [
            {"weight": 12, "reps": [10, 10, 9], "rpe": 9, "pain": 0}], "want": "hold"},
        {"name": "连续 RPE 9 降重", "meta": bench, "hist": [
            {"weight": 12, "reps": [10, 9, 9], "rpe": 9, "pain": 0},
            {"weight": 12, "reps": [10, 9, 9], "rpe": 9, "pain": 0}], "want": "down"},
        {"name": "疼痛换动作", "meta": bench, "hist": [
            {"weight": 8, "reps": [12, 12, 12], "rpe": 7, "pain": 5}], "want": "swap"},
        {"name": "平板支撑加时", "meta": plank, "hist": [
            {"weight": 0, "reps": [40, 35, 30], "rpe": 7, "pain": 0}], "want": "extend"},
        {"name": "自重加次数", "meta": squat, "hist": [
            {"weight": 0, "reps": [10, 10, 10], "rpe": 6, "pain": 0}], "want": "up"},
    ]
    failed = 0
    for c in cases:
        d = decide(c["hist"], "muscle", c["meta"])
        ok = d["action"] == c["want"]
        failed += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] {c['name']}：{LABEL[d['action']]} — {d['reps_text']}")
    return 1 if failed else 0


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="按训练日志调整下周计划")
    ap.add_argument("--profile", help="训练档案 JSON")
    ap.add_argument("--log", help="训练日志 JSON")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.profile or not args.log:
        ap.error("需要 --profile 与 --log")

    raw = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    profile = pb.normalize_profile(raw)
    entries = load_log(Path(args.log))
    library = {e["name"]: e for e in pb.load_exercises()}
    rows = analyze(entries, profile, library)
    program = apply_to_program(pb.build_program(raw), rows)

    if args.format == "json":
        text = json.dumps({"profile": profile, "rows": rows, "checks": validate_adjust(rows)},
                          ensure_ascii=False, indent=2)
    else:
        text = render(rows, program, profile)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写入 {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
