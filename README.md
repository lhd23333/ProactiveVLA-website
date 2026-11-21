# ProactiveVLA 项目主页

论文 *ProactiveVLA: Augmenting Embodied Memory through Proactive Environment Exploration*（arXiv 2610.06999）的静态项目主页。纯 HTML、CSS、JS，没有框架和构建工具；字体、图片、视频全部放在本地，不依赖任何 CDN，国内网络和微信内置浏览器都能完整打开。

## 目录

```
index.html              页面本体；正文手写，<!-- build:NAME --> 标记之间的部分由脚本生成
static/css/style.css    全部样式，按 @layer reset → tokens → base → layout → components 分层
static/js/main.js       交互：导航高亮、视频进入视口自动播放、探索账本、视频标签页、复制 BibTeX、首屏视频带
static/fonts/           Archivo（标题、界面、表格）与 Source Serif 4（正文），latin 子集 woff2
static/images/          论文图（WebP/SVG）、遮挡对比逐帧图、favicon、分享卡片 og-card.jpg
static/videos/          仿真视频（约 36 MB，含 RoboCasa 墙格截取片段）
static/posters/         视频首帧海报
static/data/ledger.json 探索账本数据
tools/build_assets.py   生成 static/ 下的视频、海报、论文图和账本数据
tools/build_html.py     把首屏视频带、账本、表 1–3、遮挡对比图、视频标签页写进 index.html
tools/manifest.json     视频时长、图片尺寸等，供 build_html.py 读取
tools/instructions.json 各任务的英文指令
```

## 本地预览

```bash
python -m http.server 8000
```

然后打开 <http://127.0.0.1:8000/>。不要直接双击 `index.html`：`file://` 下浏览器会拦截 ES module 脚本，交互全部失效。

## 重建

依赖 Python 3.10+、PyMuPDF（`pip install pymupdf`）和 PATH 中的 ffmpeg / ffprobe。`build_html.py` 只用标准库。

1. 重新生成资源（论文源码包属于外部下载内容，用 `-I` 隔离运行）：

   ```bash
   python -I tools/build_assets.py --videos <宣传视频目录> --robocasa <RoboCasa 成功视频目录> --eprint <论文源码目录> --ledger <exploration_layers.json>
   ```

   各参数可以只给一部分，只重建对应资源，其余沿用 `tools/manifest.json` 里的记录。例如只改了论文图：`--eprint <论文源码目录>`；只更新 RoboCasa 墙格片段：`--robocasa <RoboCasa 成功视频目录>`。

2. 回填页面：

   ```bash
   python -I tools/build_html.py
   ```

   脚本只替换 `<!-- build:wall -->`、`ledger`、`table-libero`、`table-robocasa`、`table-ablation`、`occlusion`、`videos` 这七个标记块，并检查页面引用的每个 `static/` 文件都存在。摘要、方法、分析等正文在 `index.html` 里直接改。表格里的数字写在 `build_html.py` 顶部的常量中，与论文表格逐项对应。

## 数据来源

| 页面内容 | 来源 |
|---|---|
| 摘要、方法、表 1–3、图 1–3、预算曲线 | 论文 |
| Exploration 一节的探索账本 | 组内适配日志（LIBERO-Pro Spatial-T，seed 0），论文里没有这份逐场景明细，页面上已注明 |
| Videos 的 Head-to-head 标签 | 组内 Goal-T 重跑，与表 1 的评测分开，页面上有披露说明，并列出了反方向的 7 个案例 |
| 其余视频 | 各设置中挑选的成功片段，页面已注明是挑选的 |
| 首屏视频带的 RoboCasa 片段 | O 组 RoboCasa-365 成功 rollout（2026-11-21 批次）每段截 6 秒，仅作背景装饰；完整视频留作后续案例分析 |

如果不打算公开内部数据：删掉 `index.html` 中 `id="exploration"` 的整节和导航里的 Exploration 链接；Head-to-head 标签从 `build_html.py` 的 `build_videos` 里去掉后重新运行脚本。

## 部署到 GitHub Pages

线上地址：<https://lhd23333.github.io/ProactiveVLA-website/>，仓库：<https://github.com/lhd23333/ProactiveVLA-website>（public）。

- 本目录是独立 git 仓库，main 分支根目录即站点根目录；根目录的 `.nojekyll` 让 GitHub 跳过 Jekyll 处理，原样发布。
- 视频随仓库一起提交，单个文件最大约 2.9 MB，远低于 GitHub 的 100 MB 限制。
- 日常更新：改完内容后 `git add -A && git commit -m "<说明>" && git push`，Pages 自动重新构建。
- `index.html` 头部的 `og:url` / `og:image` 已填线上绝对地址；若更换域名，需同步修改这两处（`og:url`、`og:image` 必须是绝对地址，否则微信、Twitter 等抓不到卡片图）。

## 实现约定

- 浅色、深色跟随系统设置，不设切换按钮。颜色只在 `style.css` 的 tokens 层定义（`light-dark()`），文字与背景的对比度已逐对核对，改色后请重新检查。
- 首屏是一整幅深色色块（页脚同一套颜色，首尾呼应），标题占满一行；整个首屏背景铺满仿真视频带，由 `build_html.py` 的 `build:wall` 块从 `tools/manifest.json` 生成：十一条斜带、每排 28 格（14 段视频 + 14 张同名海报图作复制件），每条绕自身中心逆时针转 40°，相邻两条反向横移，排距按 `cos 40°` 反推，转过来之后的格子间隙与排内间隙一致，宽屏四角也能盖住。复制件用 `<img>` 而不是第二个 `<video>`，可解码的元素减半；横移只在中间位置左右各走一份复制件的一半（`translateX(±25%)`），整排两端始终留有余量，不会扫到排头露缝。窄屏首屏短，最外侧四条斜带隐藏。只用 6 组短片段共 28 段（约 3.0 MB），其中 RoboCasa 每段是 6 秒截取版；`explore`、`h2h` 这类长片段没有放进来。
- 压暗与取景：视频带左缘用遮罩淡出，标题区让位给纯色底；上面再压一层独立的渐变（左侧最重、右侧留亮，另叠左上冷光、一道约 5% 白色的斜向掠光、底部沉降），保证标题区对比度的同时让右侧透出画面。首屏至少一屏高（`100svh`），正文不会从折线处提前露头。页脚底部同样有一层很轻的渐亮收尾。
- 正文沿用同一套 40° 语言：每节标题上方一道 40° 的短斜线；Abstract 与 Videos 两节铺满视口的浅蓝色带（内容宽度与其它节严格对齐，靠左右内边距居中，不用负外边距，不会产生横向滚动）带一层纵向渐变与 40° 细斜纹；探索账本选中行、表格里 ProactiveVLA 的行与列也铺同一角度的细斜纹；摘要做成左侧引线 + 略大字号，BibTeX 用深色代码块（右上角一点主题色微光）收尾。
- 视频带共三百来个格子（其中一半是可播放的 `<video>`），但同时解码的只留 20 个：`main.js` 按当前画面位置挑出离右中部最近的一批播放，其余停在海报帧，左侧被遮罩压掉的格子不参与；离开首屏即全部暂停、横移动画停住；系统要求减少动效或开启省流量时只显示海报帧。视频带是纯装饰，`aria-hidden`，读屏软件跳过。
- 导航高亮用 CSS 原生 `scroll-target-group`；不支持的浏览器由 `main.js` 用 IntersectionObserver 兜底，两种情况都会同步 `aria-current`。
- 视频进入视口才播放、离开即暂停；系统开启“减少动态效果”或省流量模式时一律不自动播放；用户手动暂停过的视频不会被自动续播。
- 未选中的视频标签面板用 `hidden="until-found"`，浏览器的页内查找能搜到其中文字并自动切到对应标签。
- 复制 BibTeX 用 `command` / `commandfor`，旧浏览器退回普通点击事件；Clipboard API 不可用时改用 `execCommand('copy')`。
- 页面只有两处非交互动效：账本条形随滚动展开、首屏视频带斜向横移；都只在用户未要求减少动效时启用。

## 字体许可

Archivo（Omnibus-Type）与 Source Serif 4（Adobe）都以 SIL Open Font License 1.1 发布，允许随网站自托管分发。来源：<https://github.com/Omnibus-Type/Archivo>、<https://github.com/adobe-fonts/source-serif>。
