#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为每个力量动作生成教学视频链接，并输出一个可搜索的索引页。

策略：
1. 有明确视频的动作用人工挑选的链接（CURATED）；
2. 其余动作生成 B 站「搜索直达」链接——不会失效，点开就是相关视频列表。

输出：
    assets/videos/videos.json
    assets/videos/index.html
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
LIB = BASE / "strength_exercises.json"
OUT_DIR = ROOT / "assets" / "videos"

# 人工挑过的视频（B 站）。优先短教程；没有的走「10 分钟以内」搜索链接。
CURATED = {
    "箱式深蹲": [("深蹲教学（新手向）", "https://www.bilibili.com/video/BV1xdCbYgEiQ/")],
    "高脚杯深蹲": [("深蹲标准动作讲解", "https://www.bilibili.com/video/BV13WGb6YELm/")],
    "杠铃背蹲": [("三分半学会标准杠铃深蹲", "https://www.bilibili.com/video/BV1FU9LB5EGf/")],
    "哑铃罗马尼亚硬拉": [("罗马尼亚硬拉示范", "https://www.bilibili.com/video/BV1AxwSziEjS/")],
    "单腿硬拉": [("新手硬拉最常见的 5 个错误", "https://www.bilibili.com/video/BV18xkdYQER8/")],
    "徒手弓步蹲": [("弓箭步蹲保姆级教学", "https://www.bilibili.com/video/BV1iV89zME8a/")],
    "行走弓步": [("弓步蹲动作要领", "https://www.bilibili.com/video/BV1rmcXeyExk/")],
    "上斜俯卧撑": [("零基础俯卧撑入门教学", "https://www.bilibili.com/video/BV12KTJzvEWa/")],
    "俯卧撑": [("从零到一做好基础俯卧撑", "https://www.bilibili.com/video/BV13fiqYREPq/")],
    "哑铃单臂划船": [("单臂哑铃划船教学", "https://www.bilibili.com/video/BV1RS42197BT/")],
    "臀桥": [("臀桥 + 背部伸展", "https://www.bilibili.com/video/BV1cNVNzaEHQ/")],
    "死虫": [("死虫式核心发力讲解", "https://www.bilibili.com/video/BV1q28m63ELB/")],
    "高位下拉": [("练背首选高位下拉", "https://www.bilibili.com/video/BV1VfqWBDEzD/")],
    "哑铃肩推": [("坐姿哑铃推肩教学", "https://www.bilibili.com/video/BV1CZhe6JEjM/")],
    "平板支撑": [("平板支撑动作详解与纠错", "https://www.bilibili.com/video/BV1444y1V7t2/")],
    "侧平板": [("平板支撑正确细节", "https://www.bilibili.com/video/BV1fPVy6sEV8/")],
}

PATTERN_CN = {
    "squat": "蹲", "hinge": "髋铰链", "lunge": "单腿蹲",
    "push_h": "水平推", "push_v": "垂直推",
    "pull_h": "水平拉", "pull_v": "垂直拉",
    "core": "核心", "carry": "负重行走", "arms": "手臂",
    "calf": "小腿", "conditioning": "心肺",
}


def search_url(name: str) -> str:
    # duration=1: 只搜 10 分钟以内的短视频
    return ("https://search.bilibili.com/all?keyword=" + quote(f"{name} 标准动作 教学")
            + "&duration=1")


def main() -> int:
    data = json.loads(LIB.read_text(encoding="utf-8"))
    exercises = data["exercises"]

    out = []
    for ex in exercises:
        name = ex["name"]
        curated = CURATED.get(name, [])
        links = [{"title": t, "url": u, "type": "video"} for t, u in curated]
        if links:
            # 再给一条「换更短的」兜底，原视频偏长时用
            links.append({"title": "换更短的（10 分钟内）", "url": search_url(name), "type": "search"})
        else:
            links = [{"title": f"B 站搜索：{name}（10 分钟内）", "url": search_url(name), "type": "search"}]
        out.append({
            "id": ex["id"],
            "name": name,
            "pattern": ex["pattern"],
            "pattern_cn": PATTERN_CN.get(ex["pattern"], ex["pattern"]),
            "primary": ex["primary"],
            "links": links,
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "videos.json").write_text(
        json.dumps({"generated_from": "strength_exercises.json", "items": out},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    rows = []
    for it in out:
        links = " ".join(
            f'<a class="v" href="{l["url"]}" target="_blank" rel="noopener">▶ {l["title"]}</a>'
            for l in it["links"])
        rows.append(
            f'<div class="row" data-k="{it["name"]} {it["pattern_cn"]}">'
            f'<div class="n">{it["name"]}<small>{it["pattern_cn"]} · {"、".join(it["primary"])}</small></div>'
            f'<div class="l">{links}</div></div>')

    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>动作教学视频索引 · posture-coach</title>
<style>
:root{--bg:#f4f2ec;--card:#fff;--ink:#17251f;--muted:#71847d;--line:#e4e0d4;--teal:#0f6b5f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 "PingFang SC","Microsoft YaHei",system-ui,sans-serif;padding:28px 18px 60px}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--muted);font-size:12.5px;margin:0 0 18px}
input{width:100%;padding:10px 14px;border:1px solid var(--line);border-radius:10px;font:inherit;background:#fff}
input:focus{outline:2px solid #d3e8e3;border-color:var(--teal)}
.list{margin-top:14px;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.row{display:flex;gap:12px;align-items:center;padding:11px 14px;border-bottom:1px solid var(--line)}
.row:last-child{border-bottom:0}
.n{flex:1;font-size:13.5px;font-weight:600}
.n small{display:block;font-weight:400;color:var(--muted);font-size:11.5px}
.l{display:flex;gap:8px;flex-wrap:wrap}
a.v{font-size:12px;color:#8a2f16;background:#fdeee8;border:1px solid #f3cdbf;border-radius:999px;padding:4px 10px;text-decoration:none}
a.v:hover{background:#f9ddd2}
.tip{color:var(--muted);font-size:12px;margin-top:14px}
</style></head>
<body><div class="wrap">
<h1>动作教学视频索引</h1>
<p class="sub">36 个力量动作，每个配一条视频入口。带「搜索」的是 B 站搜索直达，点开就是相关视频列表。</p>
<input id="q" placeholder="搜动作名或部位，比如：深蹲 / 背 / 肩">
<div class="list" id="list">
__ROWS__
</div>
<p class="tip">视频来自 B 站公开搜索与人工挑选，版权归原作者；链接失效时用搜索入口重新找。</p>
</div>
<script>
const q=document.getElementById('q'), rows=[...document.querySelectorAll('.row')];
q.addEventListener('input',()=>{const k=q.value.trim();rows.forEach(r=>{r.style.display=!k||r.dataset.k.includes(k)?'':'none';});});
</script>
</body></html>"""

    (OUT_DIR / "index.html").write_text(html.replace("__ROWS__", "\n".join(rows)), encoding="utf-8")
    print(f"videos: {len(out)} 个动作 -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
