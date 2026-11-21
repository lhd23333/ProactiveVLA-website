"""生成 index.html 里由数据驱动的片段：探索账本、三张结果表、遮挡帧、视频标签页、首屏视频墙。

用法（在网站根目录运行，可重复运行）：
    python -I tools/build_html.py

读取：
    static/data/ledger.json   探索账本（build_assets.py 生成）
    tools/manifest.json       视频清单、插图尺寸（build_assets.py 生成）
    tools/instructions.json   各任务的英文指令
写入：
    index.html 中 <!-- build:NAME --> 与 <!-- /build:NAME --> 之间的内容

结果表的数字全部抄自论文 tables/main_results.tex 与 tables/ablations.tex，改数字前先核对论文。
"""
from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
SR = '<span class="visually-hidden">{}</span>'   # 只给读屏软件的文字


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def instruction(instructions: dict, suite: str, task: int) -> str:
    """取该任务第一条非空指令，首字母大写、去掉句号。"""
    for text in instructions.get(f"{suite}/{task}", []):
        text = text.strip().rstrip(".")
        if text:
            return text[0].upper() + text[1:]
    raise KeyError(f"缺少指令：{suite}/{task}")


def fmt(value: float) -> str:
    return f"{value:.1f}"


def video_tag(group: str, name: str, preload: str = "none") -> str:
    lazy = ' loading="lazy"' if preload == "none" else ""
    return (f'<video data-autoplay controls muted loop playsinline preload="{preload}"{lazy} '
            f'width="256" height="256" poster="static/posters/{group}/{name}.webp" '
            f'src="static/videos/{group}/{name}.mp4"></video>')


# ---------------- 探索账本 ----------------
GLYPH = {"passed": "g-pass", "failed": "g-fail", "uncertain": "g-unsure"}
STOP_TEXT = {"coverage_complete": "coverage complete", "turn_budget": "turn budget used up"}


def short_spatial(text: str) -> str:
    """Spatial 指令只差“哪只碗”，列表里只显示这一段。"""
    m = re.match(r"pick (?:up )?the akita black bowl (.+?) and place it on the plate$", text, re.I)
    return f"Bowl {m.group(1)}" if m else text


def verdicts_by_level(scene: dict) -> dict[int, list[str]]:
    return {lvl: [g["verdict"] for g in scene["goals"] if g["level"] == lvl] for lvl in (1, 2, 3)}


def level_summary(level: int, verdicts: list[str]) -> str:
    if not verdicts:
        return f"Level {level}: no goals proposed."
    text = f"Level {level}: {verdicts.count('passed')} of {len(verdicts)} passed"
    unsure = verdicts.count("uncertain")
    return text + (f", {unsure} uncertain." if unsure else ".")


def level_cell(verdicts: list[str]) -> str:
    if not verdicts:
        return "none proposed"
    unsure = verdicts.count("uncertain")
    return f"{verdicts.count('passed')} of {len(verdicts)}" + (f" ({unsure} uncertain)" if unsure else "")


def ledger_row(scene: dict, video: dict, ins: str, checked: bool) -> str:
    n, a, b = scene["scene"], scene["target_turns"], scene["explore_turns"]
    lv = verdicts_by_level(scene)
    budget_out = scene["stop"] == "turn_budget"
    desc = f"{a} turns on the target task, {b} on exploration"
    desc += " (stopped when the turn budget ran out). " if budget_out else ". "
    desc += " ".join(level_summary(lvl, lv[lvl]) for lvl in (1, 2, 3))
    turns = f"{a} + {b} turns" + (", budget used up" if budget_out else "")
    groups = "".join(
        f'<span class="goals"><span class="lvl">L{lvl}</span>'
        + ("".join(f'<svg class="g"><use href="#{GLYPH[v]}"/></svg>' for v in lv[lvl])
           or '<span class="goals-none">none</span>')   # 该层没有提出目标时写明，免得被当成缺数据
        + "</span>"
        for lvl in (1, 2, 3)
    )
    name = video["name"]
    return f"""<label class="ledger-row">
  <input type="radio" name="scene" value="{n}"{" checked" if checked else ""} aria-labelledby="scene-{n}-name scene-{n}-task" aria-describedby="scene-{n}-desc" data-src="static/videos/explore/{name}.mp4" data-poster="static/posters/explore/{name}.webp" data-scene="Scene {n}" data-instruction="{escape(ins)}">
  <span class="ledger-scene"><span class="ledger-name" id="scene-{n}-name">Scene {n}</span><span class="ledger-task" id="scene-{n}-task">{escape(short_spatial(ins))}</span></span>
  <span class="ledger-turns" aria-hidden="true"><span class="turns-text">{turns}</span><span class="bar" style="--a: {a}; --b: {b}"><span class="seg seg-target"></span><span class="seg seg-explore"></span></span></span>
  <span class="ledger-goals" aria-hidden="true">{groups}</span>
  <span class="visually-hidden" id="scene-{n}-desc">{escape(desc)}</span>
</label>"""


def build_ledger(ledger: dict, manifest: dict, instructions: dict) -> str:
    scenes = ledger["scenes"]
    videos = {v["task"]: v for v in manifest["videos"]["explore"]}
    first = scenes[0]
    ins = {s["scene"]: instruction(instructions, "libero_spatial_task", s["scene"]) for s in scenes}
    scale = max(s["target_turns"] + s["explore_turns"] for s in scenes)   # 所有行共用的比例尺

    rows = "\n".join(ledger_row(s, videos[s["scene"]], ins[s["scene"]], s is first) for s in scenes)
    rows = "\n".join("      " + line for line in rows.splitlines())

    allv = [g["verdict"] for s in scenes for g in s["goals"]]
    per = {lvl: [v for s in scenes for v in verdicts_by_level(s)[lvl]] for lvl in (1, 2, 3)}
    ratio = {lvl: f"{per[lvl].count('passed')} of {len(per[lvl])}" for lvl in (1, 2, 3)}

    table_rows = "\n".join(
        f'        <tr><th scope="row">Scene {s["scene"]}</th><td>{s["attempts"]}</td><td>{s["target_turns"]}</td>'
        f'<td>{s["explore_turns"]}</td>'
        + "".join(f"<td>{level_cell(verdicts_by_level(s)[lvl])}</td>" for lvl in (1, 2, 3))
        + f'<td class="is-text">{STOP_TEXT[s["stop"]]}</td></tr>'
        for s in scenes
    )
    sums = {k: sum(s[k] for s in scenes) for k in ("attempts", "target_turns", "explore_turns")}

    return f"""<div class="ledger">
  <figure class="ledger-player">
    {video_tag("explore", videos[first["scene"]]["name"], preload="metadata").replace("<video ", '<video id="ledger-video" aria-describedby="ledger-caption" ')}
    <figcaption class="ledger-caption" id="ledger-caption"><strong>Scene {first["scene"]}</strong> {escape(ins[first["scene"]])}</figcaption>
    <div class="speed" role="radiogroup" aria-labelledby="speed-label" hidden>
      <span class="speed-label" id="speed-label">Speed</span>
      <label><input type="radio" name="speed" value="1">1×</label>
      <label><input type="radio" name="speed" value="2" checked>2×</label>
      <label><input type="radio" name="speed" value="4">4×</label>
    </div>
  </figure>
  <div class="ledger-list" role="radiogroup" aria-label="Scene" style="--max: {scale}">
    <div class="ledger-head" aria-hidden="true">
      <span>Scene and target task</span><span>Turns: target task + exploration</span><span>Level 1</span><span>Level 2</span><span>Level 3</span>
    </div>
    <div class="ledger-rows">
{rows}
    </div>
    <ul class="ledger-legend" role="list">
      <li><span class="swatch swatch-target" aria-hidden="true"></span>Target-task turns</li>
      <li><span class="swatch swatch-explore" aria-hidden="true"></span>Exploration turns</li>
      <li><svg class="g" aria-hidden="true"><use href="#g-pass"/></svg>Goal passed</li>
      <li><svg class="g" aria-hidden="true"><use href="#g-fail"/></svg>Failed</li>
      <li><svg class="g" aria-hidden="true"><use href="#g-unsure"/></svg>Uncertain</li>
      <li class="legend-levels">L1 to L3: goal levels</li>
    </ul>
  </div>
</div>
        <p class="ledger-total">{len(allv)} goals: {allv.count("passed")} passed, {allv.count("failed")} failed, {allv.count("uncertain")} uncertain. Pass rate falls with level: {ratio[1]} (L1), {ratio[2]} (L2), {ratio[3]} (L3).</p>
<details class="table-view">
  <summary>Show the ledger as a table</summary>
  <div class="table-wrap" role="region" aria-labelledby="ledger-table-caption" tabindex="0">
    <table class="data-table">
      <caption id="ledger-table-caption">Turns and exploration goals per scene, LIBERO-Pro Spatial-T, seed 0</caption>
      <thead>
        <tr><th scope="col" class="col-first">Scene</th><th scope="col" class="is-wrapping">Attempts at the target task</th><th scope="col" class="is-wrapping">Target-task turns</th><th scope="col" class="is-wrapping">Exploration turns</th><th scope="col" class="is-wrapping">Level 1 goals passed</th><th scope="col" class="is-wrapping">Level 2 goals passed</th><th scope="col" class="is-wrapping">Level 3 goals passed</th><th scope="col" class="is-wrapping is-text">Exploration ended because</th></tr>
      </thead>
      <tbody>
{table_rows}
      </tbody>
      <tfoot>
        <tr><th scope="row">All scenes</th><td>{sums["attempts"]}</td><td>{sums["target_turns"]}</td><td>{sums["explore_turns"]}</td><td>{ratio[1]}</td><td>{ratio[2]}</td><td>{ratio[3]}</td><td></td></tr>
      </tfoot>
    </table>
  </div>
</details>"""


# ---------------- 表 1：LIBERO-Pro（论文 Table 1，按论文分组） ----------------
SUITES = ["Spatial", "Object", "Goal", "LIBERO-10"]
LIBERO_GROUPS = [
    [("OpenVLA", [0, 0, 0, 0, 0, 0, 0, 0], 0.0),
     ("π<sub>0</sub>", [0, 0, 0, 2, 0, 0, 0, 0], 0.3),
     ("π<sub>0.5</sub>", [1, 20, 1, 17, 2, 38, 1, 8], 11.0),
     ("MolmoAct", [0, 0, 0, 6, 0, 0, 6, 0], 1.5),
     ("NORA", [0, 0, 0, 0, 0, 0, 0, 0], 0.0),
     ("X-VLA", [0, 0, 8, 2, 9, 1, 10, 0], 3.8),
     ("AtomVLA", [1, 16, 0, 10, 11, 2, 9, 1], 6.3)],
    [("Cap-X", [14, 12, 18, 22, 17, 26, None, None], 18.2),
     ("RATS", [31, 29, 63, 61, 36, 43, None, None], 43.8)],
    [("π<sub>RLinf</sub>", [42, 59, 71, 78, 45, 42, 49, 14], 50.0),
     ("Harness VLA", [81, 69, 94, 91, 75, 66, 52, 49], 72.1)],
    [("ProactiveVLA", [85, 75, 98, 92, 88, 71, 44, 58], 76.4)],
]
UNREPORTED = '<span aria-hidden="true">/</span>' + SR.format("not reported")


def build_libero() -> str:
    rows = [r for g in LIBERO_GROUPS for r in g]
    cols = list(zip(*[r[1] + [r[2]] for r in rows]))
    best = [max(v for v in col if v is not None) for col in cols]   # 每列最高分加粗（与论文一致）

    def cell(v, j, dagger=False):
        if v is None:
            return f"<td>{UNREPORTED}</td>"
        text = fmt(v) + ("<sup>†</sup>" if dagger else "")
        return f"<td><strong>{text}</strong></td>" if v == best[j] else f"<td>{text}</td>"

    bodies = []
    for group in LIBERO_GROUPS:
        trs = []
        for name, vals, overall in group:
            ours = ' class="is-ours"' if name == "ProactiveVLA" else ""
            tds = "".join(cell(v, j) for j, v in enumerate(vals))
            tds += cell(overall, 8, dagger=None in vals)
            trs.append(f'      <tr{ours}><th scope="row">{name}</th>{tds}</tr>')
        bodies.append("    <tbody>\n" + "\n".join(trs) + "\n    </tbody>")

    ts = (f'<th scope="col"><span aria-hidden="true">T</span>{SR.format("instruction redirection")}</th>'
          f'<th scope="col"><span aria-hidden="true">S</span>{SR.format("position swap")}</th>')
    groups = "".join(f'<th scope="colgroup" colspan="2">{s}</th>' for s in SUITES)
    return f"""<div class="table-wrap" role="region" aria-labelledby="libero-caption" tabindex="0">
  <table class="data-table">
    <caption id="libero-caption"><span class="table-label">Table 1.</span> Success rates (%) on LIBERO-Pro</caption>
    <colgroup><col><col span="2"><col span="2"><col span="2"><col span="2"><col></colgroup>
    <thead>
      <tr><th scope="col" rowspan="2" class="col-first">Method</th>{groups}<th scope="col" rowspan="2">Overall</th></tr>
      <tr>{ts * 4}</tr>
    </thead>
{chr(10).join(bodies)}
  </table>
</div>
<p class="table-note">T: instruction redirection. S: position swap. Overall is the unweighted mean of the eight settings, except for Cap-X and RATS (marked †), which average the six settings they report. A slash marks an unreported entry. Bold marks the best score in each column.</p>"""


# ---------------- 表 2：RoboCasa365 Composite-Seen（论文 Table 2，每行最高分加粗，含并列） ----------------
ROBOCASA_METHODS = ["GR00T N1.5", "StarVLA-OFT", "StarVLA-PI", "StarVLA-GR00T", "Harness VLA", "ProactiveVLA"]
ROBOCASA = [
    ("DeliverStraw", [3, 0, 4, 0, 20, 20]),
    ("GetToastedBread", [0, 4, 56, 52, 20, 20]),
    ("KettleBoiling", [53, 28, 54, 60, 20, 20]),
    ("LoadDishwasher", [47, 30, 64, 42, 60, 40]),
    ("PackIdenticalLunches", [17, 2, 0, 0, 20, 20]),
    ("PreSoakPan", [70, 28, 48, 58, 60, 60]),
    ("PrepareCoffee", [13, 2, 28, 28, 0, 0]),
    ("RinseSinkBasin", [60, 28, 76, 80, 20, 40]),
    ("ScrubCuttingBoard", [70, 8, 54, 18, 80, 80]),
    ("SearingMeat", [27, 0, 12, 10, 0, 0]),
    ("SetUpCuttingStation", [33, 10, 30, 40, 20, 40]),
    ("StackBowlsCabinet", [83, 64, 60, 72, 100, 100]),
    ("SteamInMicrowave", [30, 8, 26, 12, 20, 60]),
    ("StirVegetables", [33, 0, 10, 24, 0, 60]),
    ("StoreLeftoversInBowl", [43, 18, 40, 4, 0, 0]),
    ("WashLettuce", [67, 20, 68, 66, 40, 100]),
]
ROBOCASA_AVG = [40.6, 15.6, 39.4, 35.4, 30.0, 41.3]


def row_cells(vals: list[float]) -> str:
    top = max(vals)
    return "".join(f"<td><strong>{fmt(v)}</strong></td>" if v == top else f"<td>{fmt(v)}</td>" for v in vals)


def build_robocasa() -> str:
    head = "".join(f'<th scope="col">{m}</th>' for m in ROBOCASA_METHODS)
    body = "\n".join(f'      <tr><th scope="row">{t}</th>{row_cells(v)}</tr>' for t, v in ROBOCASA)
    return f"""<details class="more">
  <summary>Per-task results on all 16 tasks</summary>
  <div class="table-wrap" role="region" aria-labelledby="robocasa-caption" tabindex="0">
    <table class="data-table">
      <caption id="robocasa-caption"><span class="table-label">Table 2.</span> Per-task success rates (%) on RoboCasa365 Composite-Seen</caption>
      <colgroup><col><col span="5"><col class="is-ours"></colgroup>
      <thead>
        <tr><th scope="col" class="col-first">Task</th>{head}</tr>
      </thead>
      <tbody>
{body}
      </tbody>
      <tfoot>
        <tr><th scope="row">Average</th>{row_cells(ROBOCASA_AVG)}</tr>
      </tfoot>
    </table>
  </div>
  <p class="table-note">GR00T N1.5 is evaluated with 30 rollouts per task and the StarVLA variants with 50. Harness VLA and ProactiveVLA use 5 rollouts per task, one per evaluation seed, with 30 agent turns each. Bold marks the best score in each row, ties included.</p>
</details>"""


# ---------------- 表 3：Goal-S 消融（论文 Table 3；论文只加粗 Overall 行，这里照做） ----------------
ABLATION_COLS = ["ProactiveVLA", "w/o initial task guidance", "w/o memory management", "w/o three-level exploration"]
GOAL_S_TASKS = [  # 论文附录的 Goal-S 任务表：task00–task09 对应的指令
    "Open the middle drawer of the cabinet", "Put the bowl on the stove", "Put the wine bottle on top of the cabinet",
    "Open the top drawer and put the bowl inside", "Put the bowl on top of the cabinet",
    "Push the plate to the front of the stove", "Put the cream cheese in the bowl", "Turn on the stove",
    "Put the bowl on the plate", "Put the wine bottle on the rack",
]
ABLATION = [[0, 0, 0, 0], [90, 90, 80, 30], [70, 80, 80, 50], [80, 70, 80, 10], [100, 100, 100, 90],
            [20, 0, 10, 0], [70, 70, 80, 30], [100, 100, 100, 100], [100, 100, 90, 70], [80, 70, 50, 40]]
ABLATION_OVERALL = [71.0, 68.0, 67.0, 42.0]


def build_ablation() -> str:
    wrap = ' class="is-wrapping"'
    head = "".join(f'<th scope="col"{wrap if i else ""}>{c}</th>' for i, c in enumerate(ABLATION_COLS))
    body = "\n".join(
        f'      <tr><th scope="row">{escape(t)}<span class="row-id">task{i:02d}</span></th>'
        + "".join(f"<td>{fmt(v)}</td>" for v in vals) + "</tr>"
        for i, (t, vals) in enumerate(zip(GOAL_S_TASKS, ABLATION))
    )
    overall = "".join(f"<td><strong>{fmt(v)}</strong></td>" if i == 0 else f"<td>{fmt(v)}</td>"
                      for i, v in enumerate(ABLATION_OVERALL))
    return f"""<div class="table-wrap" role="region" aria-labelledby="ablation-caption" tabindex="0">
  <table class="data-table has-long-rows">
    <caption id="ablation-caption"><span class="table-label">Table 3.</span> Task-level success rates (%) on LIBERO-Pro Goal-S</caption>
    <colgroup><col><col class="is-ours"><col span="3"></colgroup>
    <thead>
      <tr><th scope="col" class="col-first">Task</th>{head}</tr>
    </thead>
    <tbody>
{body}
    </tbody>
    <tfoot>
      <tr><th scope="row">Overall</th>{overall}</tr>
    </tfoot>
  </table>
</div>"""


# ---------------- 图 3：遮挡案例的逐帧对比 ----------------
OCCLUSION = [
    ("proactive", "ProactiveVLA, succeeded", "g-pass",
     ["Initial state", "VLA_act", "Occlusion", "Move_to", "Re-localize", "Move_to", "Release"]),
    ("harness", "Harness VLA, failed", "s-fail",
     ["Initial state", "VLA_act", "Occlusion", "Move_to", "No re-localize", "Wrong position", "Failed"]),
]
KEY_STEP = 5   # 两条轨迹从第 5 步开始分叉


def build_occlusion(manifest: dict) -> str:
    sizes = manifest["figures"]
    rows = []
    for agent, label, icon, steps in OCCLUSION:
        items = []
        for k, step in enumerate(steps, start=1):
            w, h = sizes[f"occ-{agent}-{k}"]
            key = ' class="is-key"' if k == KEY_STEP else ""
            items.append(f'      <li{key}><img src="static/images/occlusion/{agent}-{k}.webp" width="{w}" height="{h}" '
                         f'loading="lazy" decoding="async" alt=""><span>{step}</span></li>')
        rows.append(f"""<div class="occ-row">
  <p class="occ-agent" id="occ-{agent}"><svg class="status" aria-hidden="true"><use href="#{icon}"/></svg>{label}</p>
  <ol class="occ-steps" role="list" aria-labelledby="occ-{agent}">
{chr(10).join(items)}
  </ol>
</div>""")
    return "\n".join(rows)


# ---------------- 视频标签页 ----------------
# (分组目录, 标签文字, 指令表, 套件说明, ProactiveVLA 在该设置的成功率，取自表 1)
VIDEO_TABS = [
    ("goal-t", "Goal-T", "libero_goal_task", "LIBERO-Goal with instruction redirection", 88),
    ("object-t", "Object-T", "libero_object_task", "LIBERO-Object with instruction redirection", 98),
    ("object-s", "Object-S", "libero_object_swap", "LIBERO-Object with position swap", 92),
    ("spatial-t", "Spatial-T", "libero_spatial_task", "LIBERO-Spatial with instruction redirection", 85),
    ("l10-s", "LIBERO-10-S", "libero_10_swap", "LIBERO-10 with position swap", 58),
]
H2H_LEAD = ("Same task, seed and budget: Harness VLA fails, ProactiveVLA succeeds.")
H2H_DISCLOSURE = (
    "These pairs come from our own re-run of Goal-T, separate from the evaluation in Table 1. "
    "They are every task and seed in that re-run where ProactiveVLA succeeded and Harness VLA failed. "
    "The reverse happened in 7 cases: task 0 seed 10, task 2 seeds 2 and 5, task 5 seeds 2, 9 and 10, and task 6 seed 4."
)


def clip_caption(ins: str, task: int, seed: int) -> str:
    return f'<span>{escape(ins)}</span><span class="clip-meta">Task {task}, seed {seed}</span>'


def build_single_panel(group: str, suite: str, setting: str, rate: int, clips: list, instructions: dict) -> str:
    n = len(clips)
    shown = "10 of 10 tasks" if n == 10 else f"{n} of 10 tasks"
    items = "\n".join(
        f'  <li><figure class="clip">{video_tag(group, c["name"])}'
        f'<figcaption>{clip_caption(instruction(instructions, suite, c["task"]), c["task"], c["seed"])}</figcaption></figure></li>'
        for c in sorted(clips, key=lambda c: c["task"])
    )
    lead = f"{setting} &middot; {rate}% success &middot; {shown}."
    return f'<p class="panel-lead">{lead}</p>\n<ul class="clip-grid" role="list">\n{items}\n</ul>'


def build_h2h_panel(clips: list, instructions: dict) -> str:
    pairs: dict[tuple[int, int], dict[str, dict]] = {}
    for c in clips:
        side = "harness" if c["name"].endswith("-harness") else "proactive"
        pairs.setdefault((c["task"], c["seed"]), {})[side] = c
    items = []
    for (task, seed), p in sorted(pairs.items()):
        ins = escape(instruction(instructions, "libero_goal_task", task))
        items.append(f"""  <li class="pair">
    <h3><span>{ins}</span><span class="clip-meta">Task {task}, seed {seed}</span></h3>
    <div class="pair-clips">
      <figure class="clip">{video_tag("h2h", p["harness"]["name"])}<figcaption class="verdict"><svg class="status" aria-hidden="true"><use href="#s-fail"/></svg>Harness VLA, failed</figcaption></figure>
      <figure class="clip">{video_tag("h2h", p["proactive"]["name"])}<figcaption class="verdict"><svg class="status" aria-hidden="true"><use href="#g-pass"/></svg>ProactiveVLA, succeeded</figcaption></figure>
    </div>
  </li>""")
    return (f'<p class="panel-lead">{H2H_LEAD}</p>\n<p class="disclosure">{H2H_DISCLOSURE}</p>\n'
            f'<ul class="pair-grid" role="list">\n' + "\n".join(items) + "\n</ul>")


def build_videos(manifest: dict, instructions: dict) -> str:
    tabs = [(g, label, build_single_panel(g, suite, setting, rate, manifest["videos"][g], instructions))
            for g, label, suite, setting, rate in VIDEO_TABS]
    tabs.append(("h2h", "Head-to-head", build_h2h_panel(manifest["videos"]["h2h"], instructions)))
    buttons, panels = [], []
    for i, (g, label, body) in enumerate(tabs):
        first = i == 0
        buttons.append(f'    <button type="button" role="tab" id="tab-{g}" aria-selected="{str(first).lower()}" '
                       f'tabindex="{0 if first else -1}">{label}</button>')
        hidden = "" if first else ' hidden="until-found"'
        body = "\n".join("  " + line for line in body.splitlines())
        panels.append(f'  <div class="tabpanel" role="tabpanel" id="panel-{g}" aria-labelledby="tab-{g}"{hidden}>\n{body}\n  </div>')
    return ('<div class="tabs">\n  <div class="tablist" role="tablist" aria-label="Rollout videos by setting">\n'
            + "\n".join(buttons) + "\n  </div>\n" + "\n".join(panels) + "\n</div>")


# ---------------- 首屏视频墙 ----------------
# 墙按“每个片段全局最多出现一次”设计：11 排 × 每排 14 段 = 154 个视频位，
# 素材池 156 段（LIBERO 短片段 32 + RoboCasa 每条两段 30 + explore/h2h 墙格截取 94）。
# explore/h2h 只进 6 秒截取版（wall 组），完整视频仍留给 Videos 区，避免首屏负担翻倍。
WALL_GROUPS = ["goal-t", "object-t", "object-s", "robocasa", "spatial-t", "l10-s", "wall"]
WALL_ROWS = 11       # 每排是一条斜带；逆时针转 40° 后，十一条才盖得住宽屏首屏的四个角
WALL_UNIQUE = 14     # 每排 14 段不重复；池长 156 ≥ 11×14，全墙每段视频最多出现一次


def build_wall(manifest: dict) -> str:
    """首屏背景：十一条 40° 倾斜、相邻反向横移的仿真视频带，铺满整个首屏。
    按设置轮转取片，相邻两格不会是同一个任务；每排内容复制一份（第二份用海报图，
    不再排一遍 <video>），复制件长度盖过首屏最长的斜弦，横移时两端始终有余量。
    池子收下全部 156 段，每排取连续 14 段：11 排正好用掉 154 段，每段视频全墙只出现
    一次（连同同帧海报最多重复一次），相邻斜带必然不共用片段。
    排与排之间的间距由样式里的 --pitch 控制，--k 标出这一排在中线上下第几格。"""
    pairs = [(g, manifest["videos"][g]) for g in WALL_GROUPS]
    pool: list[tuple[str, str]] = []
    round_no = 0
    while any(round_no < len(seq) for _, seq in pairs):
        for group, seq in pairs:
            if round_no < len(seq):
                pool.append((group, seq[round_no]["name"]))
        round_no += 1

    def tile(group: str, name: str) -> str:
        # 装饰性视频：无控件、不可聚焦、不预载，poster 先顶上；播放由 main.js 决定
        return (f'<video class="wall-clip" muted loop playsinline preload="none" tabindex="-1" '
                f'width="256" height="256" poster="static/posters/{group}/{name}.webp" '
                f'src="static/videos/{group}/{name}.mp4"></video>')

    def still(group: str, name: str) -> str:
        # 复制件的海报帧：同样的画面，不额外占一个解码器
        return (f'<img class="wall-clip" alt="" width="256" height="256" decoding="async" '
                f'src="static/posters/{group}/{name}.webp">')

    rows = []
    for row in range(WALL_ROWS):
        start = (row * WALL_UNIQUE) % len(pool)   # 每排错开取片，相邻两排不重复
        picks = [pool[(start + i) % len(pool)] for i in range(WALL_UNIQUE)]
        tiles = "".join(tile(g, n) for g, n in picks) + "".join(still(g, n) for g, n in picks)
        direction = "rev" if row % 2 else "fwd"
        k = row - (WALL_ROWS - 1) / 2             # -5 … 5，0 是正中间那排
        rows.append(f'<div class="wall-row" data-dir="{direction}" style="--k:{k:g}">{tiles}</div>')
    return "".join(rows)


# ---------------- 写回 index.html ----------------
def replace_block(html: str, name: str, content: str) -> str:
    start, end = f"<!-- build:{name} -->", f"<!-- /build:{name} -->"
    i = html.find(start)
    j = html.find(end, i)
    if i < 0 or j < 0:
        raise SystemExit(f"index.html 里找不到标记 {start} … {end}")
    line_start = html.rfind("\n", 0, i) + 1
    indent = html[line_start:i]
    if indent.strip():
        raise SystemExit(f"标记 {start} 前面只能有缩进")
    body = "\n".join(indent + line if line else line for line in content.splitlines())
    return html[: i + len(start)] + "\n" + body + "\n" + indent + html[j:]


def check_assets(html: str) -> list[str]:
    """确认页面引用的本地文件都存在。"""
    refs = set(re.findall(r'(?:src|poster|data-src|data-poster|href)="(static/[^"]+)"', html))
    for srcset in re.findall(r'srcset="([^"]+)"', html):
        refs.update(part.split()[0] for part in srcset.split(","))
    return sorted(r for r in refs if not (ROOT / r).is_file())


def main() -> None:
    ledger = load_json(ROOT / "static" / "data" / "ledger.json")
    manifest = load_json(ROOT / "tools" / "manifest.json")
    instructions = load_json(ROOT / "tools" / "instructions.json")

    html = INDEX.read_text(encoding="utf-8")
    blocks = {
        "wall": build_wall(manifest),
        "ledger": build_ledger(ledger, manifest, instructions),
        "table-libero": build_libero(),
        "table-robocasa": build_robocasa(),
        "table-ablation": build_ablation(),
        "occlusion": build_occlusion(manifest),
        "videos": build_videos(manifest, instructions),
    }
    for name, content in blocks.items():
        html = replace_block(html, name, content)

    missing = check_assets(html)
    if missing:
        raise SystemExit("以下文件不存在：\n  " + "\n  ".join(missing))
    INDEX.write_text(html, encoding="utf-8", newline="\n")
    print(f"已更新 {INDEX.name}：{', '.join(blocks)}；视频 {html.count('<video ')} 个，引用文件全部存在")


if __name__ == "__main__":
    main()
