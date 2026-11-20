// ProactiveVLA 项目主页交互（ES module，HTML 解析完成后执行）
// 1. 导航高亮  2. 视频进入视口自动播放  3. 探索账本  4. 视频标签页  5. 复制 BibTeX  6. 首屏视频带
// 没有 JS 时页面照样可读：视频有原生控件，标签页默认显示第一个面板，视频带停在海报帧。

const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
const saveData = navigator.connection?.saveData === true;
const canAutoplay = () => !reduceMotion.matches && !saveData;

/* ---------- 1. 导航高亮（scrollspy） ---------- */
const navList = document.querySelector('.nav-links');
const navLinks = [...navList.querySelectorAll('a')];

// 窄屏上导航横向滚动，把当前区块的链接滚进可见范围；只滚导航本身，不动页面
function reveal(link) {
  if (!link || navList.scrollWidth <= navList.clientWidth) return;
  const view = navList.scrollLeft;
  const left = link.getBoundingClientRect().left - navList.getBoundingClientRect().left + view;
  const right = left + link.offsetWidth;
  if (left >= view && right <= view + navList.clientWidth) return;
  navList.scrollTo({
    left: left < view ? left : right - navList.clientWidth,
    behavior: reduceMotion.matches ? 'instant' : 'smooth',
  });
}

if (CSS.supports('scroll-target-group: auto')) {
  // 浏览器原生支持时高亮由 CSS 完成，这里只在滚动结束后同步 aria-current。
  // :target-current 要到下一帧渲染时才更新，scrollend 当下读到的还是旧值，所以隔两帧再读。
  const sync = () => {
    const current = document.querySelector('.nav-links a:target-current');
    for (const a of navLinks) a.setAttribute('aria-current', a === current ? 'true' : 'false');
    reveal(current);
  };
  const syncLater = () => requestAnimationFrame(() => requestAnimationFrame(sync));
  syncLater();
  document.addEventListener('scrollend', syncLater);
} else {
  const markCurrent = (link) => {
    for (const a of navLinks) {
      a.classList.toggle('target-current', a === link);
      a.setAttribute('aria-current', a === link ? 'true' : 'false');
    }
    reveal(link);
  };
  // 视口正中那条线落在哪个区块，就高亮哪个；回到首屏时全部取消
  const spy = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) markCurrent(navLinks.find((a) => a.hash === `#${entry.target.id}`));
    }
  }, { rootMargin: '-50% 0px -50% 0px' });
  for (const id of ['top', ...navLinks.map((a) => a.hash.slice(1))]) {
    const section = document.getElementById(id);
    if (section) spy.observe(section);
  }
}

/* ---------- 2. 视频：进入视口播放、离开暂停；用户手动暂停过的不再自动播放 ---------- */
const autoPaused = new WeakSet();

function tryPlay(video) {
  if (!canAutoplay() || video.dataset.userPaused) return;
  video.play().catch(() => {});   // 浏览器拒绝自动播放时停在海报帧
}
function autoPause(video) {
  if (video.paused) return;
  autoPaused.add(video);
  video.pause();
}

const viewer = new IntersectionObserver((entries) => {
  for (const { target: video, isIntersecting } of entries) {
    video.dataset.inView = isIntersecting ? 'true' : '';
    if (isIntersecting) tryPlay(video);
    else autoPause(video);
  }
}, { threshold: 0.5 });

for (const video of document.querySelectorAll('video[data-autoplay]')) {
  viewer.observe(video);
  video.addEventListener('pause', () => {
    if (autoPaused.has(video)) autoPaused.delete(video);
    else video.dataset.userPaused = 'true';
  });
  video.addEventListener('play', () => { delete video.dataset.userPaused; });
}

reduceMotion.addEventListener('change', () => {
  for (const video of document.querySelectorAll('video[data-autoplay]')) {
    if (!canAutoplay()) autoPause(video);
    else if (video.dataset.inView) tryPlay(video);
  }
});

/* ---------- 3. 探索账本：选场景换视频，切换倍速 ---------- */
const ledger = document.querySelector('.ledger');
if (ledger) {
  const video = ledger.querySelector('video');
  const caption = ledger.querySelector('.ledger-caption');
  const speed = ledger.querySelector('.speed');
  const setRate = (rate) => {
    video.defaultPlaybackRate = rate;   // 换片源后 playbackRate 会回到 defaultPlaybackRate
    video.playbackRate = rate;
  };
  speed.hidden = false;
  setRate(Number(speed.querySelector('input:checked').value));

  ledger.addEventListener('change', (event) => {
    const input = event.target;
    if (input.name === 'speed') {
      setRate(Number(input.value));
    } else if (input.name === 'scene') {
      const { src, poster, scene, instruction } = input.dataset;
      autoPause(video);   // 先由脚本暂停，避免换源时的 pause 事件被当成用户暂停
      video.poster = poster;
      video.src = src;
      caption.replaceChildren(
        Object.assign(document.createElement('strong'), { textContent: scene }),
        ` ${instruction}`,
      );
      delete video.dataset.userPaused;   // 主动选了新场景，视为想看
      if (video.dataset.inView) tryPlay(video);
    }
  });
}

/* ---------- 4. 标签页：方向键移动焦点（roving tabindex），Enter/空格或点击才切换 ---------- */
for (const root of document.querySelectorAll('.tabs')) {
  const tablist = root.querySelector('[role="tablist"]');
  const tabs = [...tablist.querySelectorAll('[role="tab"]')];
  const panels = tabs.map((tab) => root.querySelector(`[role="tabpanel"][aria-labelledby="${tab.id}"]`));
  const selectedIndex = () => tabs.findIndex((tab) => tab.getAttribute('aria-selected') === 'true');
  const setRoving = (index) => tabs.forEach((tab, i) => { tab.tabIndex = i === index ? 0 : -1; });

  const select = (index) => {
    tabs.forEach((tab, i) => {
      const on = i === index;
      tab.setAttribute('aria-selected', String(on));
      if (on) panels[i].removeAttribute('hidden');
      else panels[i].setAttribute('hidden', 'until-found');
    });
    setRoving(index);
  };

  tabs.forEach((tab, i) => tab.addEventListener('click', () => select(i)));
  tablist.addEventListener('keydown', (event) => {
    const i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    const last = tabs.length - 1;
    const next = { ArrowRight: i === last ? 0 : i + 1, ArrowLeft: i === 0 ? last : i - 1, Home: 0, End: last }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    setRoving(next);
    tabs[next].focus();
  });
  // 焦点离开标签栏后，下次 Tab 进来应落在当前选中的标签上
  tablist.addEventListener('focusout', (event) => {
    if (!tablist.contains(event.relatedTarget)) setRoving(selectedIndex());
  });
  // 页内查找命中隐藏面板时，浏览器先触发 beforematch，这里同步切换标签
  panels.forEach((panel, i) => panel.addEventListener('beforematch', () => select(i)));
}

/* ---------- 5. 复制 BibTeX（command/commandfor，旧浏览器退回 click） ---------- */
const timers = new WeakMap();

function report(button, ok) {
  const tip = button.nextElementSibling;   // role="status" 的提示气泡
  clearTimeout(timers.get(button));
  button.removeAttribute('data-copied');
  button.removeAttribute('data-failed');
  tip.textContent = '';
  void button.offsetWidth;
  button.setAttribute(ok ? 'data-copied' : 'data-failed', '');
  requestAnimationFrame(() => { tip.textContent = ok ? 'Copied' : 'Copy failed'; });
  timers.set(button, setTimeout(() => {
    button.removeAttribute('data-copied');
    button.removeAttribute('data-failed');
    tip.textContent = '';
  }, 2000));
}

function legacyCopy(text) {
  const previousFocus = document.activeElement;
  const field = Object.assign(document.createElement('textarea'), { value: text });
  field.setAttribute('readonly', '');
  field.style.cssText = 'position:fixed;inset-block-start:0;opacity:0';
  document.body.append(field);
  field.select();
  try {
    return document.execCommand('copy');
  } finally {
    field.remove();
    previousFocus?.focus({ preventScroll: true });
  }
}

async function copy(button, target) {
  const text = target.innerText.trim();
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    report(button, true);
  } catch {
    // 本地 file:// 打开或权限被拒时 Clipboard API 不可用，再试一次旧接口
    report(button, legacyCopy(text));
  }
}

if ('CommandEvent' in window) {
  // command 事件派发在目标元素上且不冒泡，所以在 document 的捕获阶段监听
  document.addEventListener('command', (event) => {
    if (event.command === '--copy') copy(event.source, event.target);
  }, true);
} else {
  document.addEventListener('click', (event) => {
    if (event.defaultPrevented) return;
    const button = event.target.closest('button[command="--copy"]');
    const target = button && document.getElementById(button.getAttribute('commandfor'));
    if (target) copy(button, target);
  });
}

/* ---------- 6. 首屏视频带：十一条 40° 斜带横移；只挑看得见的少数格子下载、播放 ---------- */
const wall = document.querySelector('.hero-wall');
if (wall) {
  // 每排后半段是海报图（复制件），只有 <video> 能播；图始终停在海报帧
  const clips = [...wall.querySelectorAll('video.wall-clip')];
  const onScreen = new Set();
  const MAX_PLAY = 20;   // 同时解码的视频数上限：格子有三百来个，全开会拖垮显卡
  let armed = false;     // 先让字体和首屏内容加载，稍后才放行视频请求

  const sync = () => {
    const go = armed && canAutoplay();
    // 斜带在动，按当前实际位置挑：离画面右中部最近的那批先播，其余停在海报帧
    const targetX = innerWidth * 0.68;
    const targetY = innerHeight * 0.5;
    const ranked = [];
    for (const clip of onScreen) {
      const r = clip.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      if (cx < innerWidth * 0.35) continue;   // 左侧被遮罩压掉，播放了也看不见
      ranked.push([Math.hypot(cx - targetX, cy - targetY), clip]);
    }
    ranked.sort((a, b) => a[0] - b[0]);
    const chosen = new Set(ranked.slice(0, MAX_PLAY).map(([, clip]) => clip));
    for (const clip of clips) {
      if (go && chosen.has(clip)) {
        if (clip.paused) clip.play().catch(() => {});   // 拒绝自动播放时停在海报帧
      } else if (!clip.paused) {
        clip.pause();
      }
    }
    wall.dataset.running = go && chosen.size ? 'true' : 'false';   // 没有播放中的格子时连带停掉横移动画
  };

  const tileView = new IntersectionObserver((entries) => {
    for (const { target, isIntersecting } of entries) {
      if (isIntersecting) onScreen.add(target);
      else onScreen.delete(target);
    }
    sync();
  }, { threshold: 0.25 });
  for (const clip of clips) tileView.observe(clip);

  setTimeout(() => { armed = true; sync(); }, 800);
  reduceMotion.addEventListener('change', sync);
}
