"""构建 ProactiveVLA 项目主页的静态资源。

做三件事（都可重复运行，输出覆盖写入 static/ 下）：
1. 视频：从宣传素材目录挑选片段，ffmpeg 无损重封装（-movflags +faststart，去元数据），
   并截取首帧生成 WebP 海报；时长写入 tools/manifest.json。
2. 论文图：用 PyMuPDF 从 arXiv 源码包的 PDF 渲染架构图和预算曲线 SVG，并取出遮挡案例 PDF 里嵌入的逐帧原图。
3. 探索账本：从 exploration_layers.json（UTF-16）抽取 Spatial-T 十个场景的轮数与判定，
   写入 static/data/ledger.json。
4. 真机 demo：把三段实拍按 6× 压缩到 720 宽并生成海报，写入 static/videos/real 与 static/posters/real。

用法（论文源码包属外部下载内容，务必用 -I 隔离运行）：
    python -I tools/build_assets.py --videos <视频目录> --robocasa <RoboCasa 成功视频目录> \
        --wall-extras --real <真机视频目录> --eprint <论文源码目录> --ledger <exploration_layers.json>
各参数可以只给一部分，只重建对应资源，其余沿用 tools/manifest.json 里的记录。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import pymupdf

SITE = Path(__file__).resolve().parent.parent
STATIC = SITE / "static"

# 源文件名正则 -> (输出子目录, 输出文件名模板)
VIDEO_RULES = [
    ("01_探索与记忆", re.compile(r"Spatial-T探索_task(\d\d)_interest"), "explore", "scene-{t}"),
    ("02_GOAL-T_O组成功", re.compile(r"GOAL-T_task(\d\d)_seed(\d\d)_成功"), "goal-t", "task-{t}-seed-{s}"),
    ("03_GOAL-T_O与H同cell", re.compile(r"GOAL-T_task(\d\d)_seed(\d\d)_H失败"), "h2h", "task-{t}-seed-{s}-harness"),
    ("03_GOAL-T_O与H同cell", re.compile(r"GOAL-T_task(\d\d)_seed(\d\d)_O成功"), "h2h", "task-{t}-seed-{s}-proactive"),
    ("04_O组_最佳结果_对齐后", re.compile(r"Object-T对齐_task(\d\d)_seed(\d\d)_成功"), "object-t", "task-{t}-seed-{s}"),
    ("04_O组_最佳结果_对齐后", re.compile(r"Spatial-T对齐_task(\d\d)_seed(\d\d)_成功"), "spatial-t", "task-{t}-seed-{s}"),
    ("04_O组_最佳结果_对齐后", re.compile(r"L10-S对齐_task(\d\d)_seed(\d\d)_成功"), "l10-s", "task-{t}-seed-{s}"),
    ("05_Object-S_92%", re.compile(r"Object-S_task(\d\d)_seed(\d\d)_成功"), "object-s", "task-{t}-seed-{s}"),
]


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def probe_duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return round(float(out.strip()), 1)


def build_videos(src_root: Path) -> dict:
    manifest: dict[str, list] = {}
    for folder, pattern, group, template in VIDEO_RULES:
        for src in sorted((src_root / folder).glob("*.mp4")):
            m = pattern.search(src.name)
            if not m:
                continue
            groups = m.groups()
            name = template.format(t=groups[0], s=groups[1] if len(groups) > 1 else "")
            out_video = STATIC / "videos" / group / f"{name}.mp4"
            out_poster = STATIC / "posters" / group / f"{name}.webp"
            out_video.parent.mkdir(parents=True, exist_ok=True)
            out_poster.parent.mkdir(parents=True, exist_ok=True)
            # 无损重封装：moov 前置便于边下边播；去掉容器与流元数据
            run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-c", "copy",
                 "-an", "-map_metadata", "-1", "-map_chapters", "-1", "-movflags", "+faststart", str(out_video)])
            # 首帧海报（同一 task+seed 的两段对照视频首帧一致，正好体现“同一起点”）
            run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-frames:v", "1",
                 "-c:v", "libwebp", "-quality", "80", str(out_poster)])
            manifest.setdefault(group, []).append({
                "name": name,
                "task": int(groups[0]),
                "seed": int(groups[1]) if len(groups) > 1 else 0,
                "duration": probe_duration(out_video),
                "bytes": out_video.stat().st_size,
            })
    return manifest


# 首屏视频带按“每个片段全局最多出现一次”设计：11 排 × 每排 14 段 = 154 个视频位，
# 素材池需要至少 154 段互不相同的片子。现有 LIBERO 短片段 32 段 + RoboCasa 每条 2 段（30）
# + explore / h2h(O 成功段) 的墙格截取（94 段），共 156 段，正好覆盖且略有富余。
# 截取统一 6 秒、CRF 30；完整视频留给 Videos 区与案例分析。
WALL_SEGMENT_SECONDS = 6.0
ROBOCASA_START_RATIOS = (0.3, 0.65)

# 真机 demo：源片段 154–183 秒，按 6× 压缩到 26–31 秒；720 宽、CRF 28、无音轨。
# 文件名固定，页面上右上角徽标（O ✓ / H × / O ✓）与这里的映射一一对应。
REAL_DEMO_SPEED = 6.0
REAL_DEMOS = [
    ("片段1.mp4", "success-1"),
    ("片段2.mp4", "fail-harness"),
    ("片段3.mp4", "success-3"),
]


def build_real_demos(src_root: Path) -> list:
    """把三段真机视频按 6× 压缩到 720 宽并生成海报，返回 manifest 条目列表。"""
    entries = []
    video_dir = STATIC / "videos" / "real"
    poster_dir = STATIC / "posters" / "real"
    video_dir.mkdir(parents=True, exist_ok=True)
    poster_dir.mkdir(parents=True, exist_ok=True)
    for src_name, name in REAL_DEMOS:
        src = src_root / src_name
        if not src.exists():
            raise FileNotFoundError(src)
        out_video = video_dir / f"{name}.mp4"
        out_poster = poster_dir / f"{name}.webp"
        run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
             "-map", "0:v:0", "-vf", f"setpts=PTS/{REAL_DEMO_SPEED:g},fps=30,scale=720:-2:flags=lanczos",
             "-c:v", "libx264", "-crf", "28", "-preset", "slow", "-pix_fmt", "yuv420p",
             "-an", "-map_metadata", "-1", "-map_chapters", "-1", "-movflags", "+faststart", str(out_video)])
        run(["ffmpeg", "-y", "-v", "error", "-i", str(out_video), "-frames:v", "1",
             "-c:v", "libwebp", "-quality", "80", str(out_poster)])
        entries.append({
            "name": name,
            "source": src_name,
            "speed": REAL_DEMO_SPEED,
            "duration": probe_duration(out_video),
            "bytes": out_video.stat().st_size,
        })
    return entries


def _cut_wall_segment(src: Path, out_video: Path, out_poster: Path, start: float) -> None:
    """从源视频 start 秒起截 6 秒，重编码为墙格片段，并截取同帧海报。"""
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:g}", "-t", f"{WALL_SEGMENT_SECONDS:g}",
         "-i", str(src), "-map", "0:v:0", "-c:v", "libx264", "-crf", "30", "-preset", "slow",
         "-pix_fmt", "yuv420p", "-an", "-map_metadata", "-1", "-map_chapters", "-1",
         "-movflags", "+faststart", str(out_video)])
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:g}", "-i", str(src), "-frames:v", "1",
         "-c:v", "libwebp", "-quality", "80", str(out_poster)])


def build_robocasa(src_root: Path) -> list:
    """把 RoboCasa-365 成功视频切成两段 6 秒墙格片段并生成海报，返回 manifest 条目列表。
    源视频已是 256×256 / 20 fps，统一重编码到 CRF 30 控制体积。"""
    entries = []
    out_dir = STATIC / "videos" / "robocasa"
    poster_dir = STATIC / "posters" / "robocasa"
    out_dir.mkdir(parents=True, exist_ok=True)
    poster_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(src_root.glob("*/O_*_success.mp4")):
        m = re.match(r"O_(.+)_seed(\d+)_success\.mp4$", src.name)
        if not m:
            continue
        task, seed = m.group(1), int(m.group(2))
        base = f"{task.lower()}-seed{seed:02d}"
        src_duration = probe_duration(src)
        for idx, ratio in enumerate(ROBOCASA_START_RATIOS):
            name = base if idx == 0 else f"{base}-{chr(ord('a') + idx)}"
            out_video = out_dir / f"{name}.mp4"
            out_poster = poster_dir / f"{name}.webp"
            start = round(src_duration * ratio, 1)
            if start + WALL_SEGMENT_SECONDS > src_duration:
                start = max(0.0, src_duration - WALL_SEGMENT_SECONDS)
            _cut_wall_segment(src, out_video, out_poster, start)
            entries.append({
                "name": name,
                "task": task,
                "seed": seed,
                "duration": probe_duration(out_video),
                "bytes": out_video.stat().st_size,
                "source_duration": src_duration,
                "segment_start": start,
            })
    return entries


# explore 与 h2h 的完整片段太长，直接进墙会让首屏负担翻几倍；各取几个 6 秒切片，
# 输出到 static/videos/wall/，只服务首屏背景，不进入 Videos 标签页。
WALL_EXTRA_RULES = [
    ("explore", re.compile(r"scene-\d+$"), (0.15, 0.3, 0.45, 0.6, 0.75)),
    ("h2h", re.compile(r".+-proactive$"), (0.15, 0.35, 0.55, 0.75)),
]


def build_wall_extras() -> list:
    """从已有 explore / h2h(O 成功) 视频生成墙格截取片段，返回 manifest 条目列表。"""
    entries = []
    out_dir = STATIC / "videos" / "wall"
    poster_dir = STATIC / "posters" / "wall"
    out_dir.mkdir(parents=True, exist_ok=True)
    poster_dir.mkdir(parents=True, exist_ok=True)
    for group, pattern, ratios in WALL_EXTRA_RULES:
        for src in sorted((STATIC / "videos" / group).glob("*.mp4")):
            if not pattern.search(src.stem):
                continue
            src_duration = probe_duration(src)
            for idx, ratio in enumerate(ratios, 1):
                name = f"{src.stem}-{idx}"
                out_video = out_dir / f"{name}.mp4"
                out_poster = poster_dir / f"{name}.webp"
                start = round(src_duration * ratio, 1)
                if start + WALL_SEGMENT_SECONDS > src_duration:
                    start = max(0.0, src_duration - WALL_SEGMENT_SECONDS)
                _cut_wall_segment(src, out_video, out_poster, start)
                seed_match = re.search(r"seed-(\d+)", src.stem)
                entries.append({
                    "name": name,
                    "task": int(re.search(r"(\d+)", src.stem).group(1)),
                    "seed": int(seed_match.group(1)) if seed_match else 0,
                    "duration": probe_duration(out_video),
                    "bytes": out_video.stat().st_size,
                    "source_group": group,
                    "source_duration": src_duration,
                    "segment_start": start,
                })
    return entries


def render_pdf_page(pdf: Path, out: Path, width_px: int, page_no: int = 0, clip=None, quality: int = 90) -> tuple[int, int]:
    doc = pymupdf.open(pdf)
    page = doc[page_no]
    rect = clip or page.rect
    zoom = width_px / rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=rect, alpha=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".png")
    pix.save(tmp)
    # PNG 转 WebP（ffmpeg 的 libwebp，避免额外依赖）
    run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-c:v", "libwebp", "-quality", str(quality),
         "-compression_level", "6", str(out)])
    tmp.unlink()
    return pix.width, pix.height


def save_square_frame(doc, xref: int, out: Path, max_px: int = 360) -> tuple[int, int]:
    """取 PDF 里嵌入的原始帧，居中裁成正方形（不放大，最长 max_px）后转 WebP。"""
    raw = doc.extract_image(xref)   # 原始 JPEG 字节；软蒙版已核实为全不透明，可忽略
    side = min(raw["width"], raw["height"])
    size = min(side, max_px)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix("." + raw["ext"])
    tmp.write_bytes(raw["image"])
    run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-vf", f"crop={side}:{side},scale={size}:{size}:flags=lanczos",
         "-c:v", "libwebp", "-quality", "84", "-compression_level", "6", str(out)])
    tmp.unlink()
    return size, size


def build_figures(eprint: Path) -> dict:
    figs = eprint / "figures"
    img = STATIC / "images"
    info: dict[str, object] = {}
    # 架构图：两档宽度供 srcset 选择
    for w in (1200, 2000):
        info[f"architecture-{w}"] = render_pdf_page(figs / "architecture.pdf", img / f"architecture-{w}.webp", w)
    # 遮挡案例：两页（ProactiveVLA / Harness VLA），每页 7 帧。直接取嵌入的原始帧而不按页面区域渲染：
    # 区域渲染会把相邻帧之间的箭头、叠加的编号框一起截进来，且 Harness 一页各帧比例不一。编号由网页 CSS 画。
    doc = pymupdf.open(figs / "occlusion_recovery.pdf")
    for page_no, agent in ((0, "proactive"), (1, "harness")):
        frames = sorted(doc[page_no].get_image_info(xrefs=True), key=lambda i: i["bbox"][0])
        for idx, frame in enumerate(frames, start=1):
            info[f"occ-{agent}-{idx}"] = save_square_frame(doc, frame["xref"], img / "occlusion" / f"{agent}-{idx}.webp")
    # 预算曲线：矢量 SVG（文字转路径，避免依赖字体）
    for name in ("goal_t_budget", "goal_s_ablation_budget"):
        page = pymupdf.open(figs / f"{name}.pdf")[0]
        svg = page.get_svg_image(text_as_path=True)
        (img / f"{name.replace('_', '-')}.svg").write_text(svg, encoding="utf-8")
        info[name] = (round(page.rect.width, 1), round(page.rect.height, 1))
    return info


def build_ledger(ledger_json: Path) -> list:
    data = json.loads(ledger_json.read_bytes().decode("utf-16"))["Spatial-T O"]
    scenes = []
    for t in data["tasks"]:
        scenes.append({
            "scene": t["task"],
            "attempts": t["target_attempts"],
            "target_turns": t["target_turns"],
            "explore_turns": t["interest_requests"],
            "stop": t["interest_stop_reason"],
            "goals": [{"level": g["level"], "verdict": g["verdict"]} for g in t["ledger_tasks"]],
        })
    out = STATIC / "data" / "ledger.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"suite": "LIBERO-Pro Spatial-T", "seed": 0, "scenes": scenes}, indent=1), encoding="utf-8")
    return scenes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", type=Path, help="宣传视频目录；省略则沿用 manifest.json 里已有的视频记录")
    ap.add_argument("--robocasa", type=Path, help="RoboCasa-365 成功视频目录（每条截两段 6 秒做首屏视频带）")
    ap.add_argument("--wall-extras", action="store_true", help="从已有 explore / h2h(O 成功) 视频生成墙格截取片段")
    ap.add_argument("--real", type=Path, help="真机 demo 源视频目录（片段1–3.mp4）；按 6× 压缩并生成海报")
    ap.add_argument("--eprint", type=Path, help="论文源码目录；省略则沿用已有的图片记录")
    ap.add_argument("--ledger", type=Path, help="exploration_layers.json；省略则不重建账本")
    args = ap.parse_args()
    if not (args.videos or args.robocasa or args.wall_extras or args.real or args.eprint or args.ledger):
        ap.error("至少给出 --videos、--robocasa、--wall-extras、--real、--eprint、--ledger 中的一项")
    path = SITE / "tools" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if args.videos:
        manifest["videos"] = build_videos(args.videos)
    if args.robocasa:
        manifest.setdefault("videos", {})["robocasa"] = build_robocasa(args.robocasa)
    if args.wall_extras:
        manifest.setdefault("videos", {})["wall"] = build_wall_extras()
    if args.real:
        # 单独放在 real_demos 下，不进 videos：首屏墙的素材池只从 videos 取，避免误把实拍混进去。
        manifest["real_demos"] = build_real_demos(args.real)
    if args.eprint:
        manifest["figures"] = build_figures(args.eprint)
    if args.ledger:
        build_ledger(args.ledger)
    path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    videos = manifest.get("videos", {})
    total = sum(v["bytes"] for g in videos.values() for v in g)
    print(f"videos: {sum(len(g) for g in videos.values())} files, {total / 1e6:.1f} MB")
    if manifest.get("real_demos"):
        print("real demos:", ", ".join(f"{d['name']} {d['duration']}s" for d in manifest["real_demos"]))
    print("figures:", manifest.get("figures"))


if __name__ == "__main__":
    main()
