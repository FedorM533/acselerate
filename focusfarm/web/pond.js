// Пруд (Carpo Pond v2). Рисует пруд на одном холсте и показывает прогресс, который считает сервер
// (focusfarm/pond/). Сам ничего не начисляет: только отображает.
// Эталон отрисовки — carpo-pond-kit/v2/preview/pond-preview-v2.html, правила — config/pond/*.json.
import { api, renderHooks, eventHooks, tabLoaders, askStrictPassword, formatTime } from "./app.js";

const $ = (sel) => document.querySelector(sel);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const ease = (t) => 1 - Math.pow(1 - clamp(t, 0, 1), 3);
const fmt = (s, o) => s.replace(/\{(\w+)\}/g, (_, k) => o[k]);
const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Режим скриншота для сравнения «до/после»: ?shot=1&t=12&tod=dusk&seed=7&scene=all
// Фиксирует случайность, время суток и момент анимации; игровую логику не трогает.
const Q = new URLSearchParams(location.search);
const SHOT = Q.has("shot") ? { t: parseFloat(Q.get("t") || "10"), tod: Q.get("tod"), all: Q.get("scene") === "all" } : null;
function mulberry32(a) {
  return () => { a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const rnd = SHOT ? mulberry32(parseInt(Q.get("seed") || "1", 10)) : Math.random;
if (SHOT) document.body.classList.add("pond-shot");

let CFG, VIS, PAL, STR, REASONS, DW, DH, MOT, UND;
const imgs = {};
const P = {
  ready: false, looping: false, running: false, hidden: false, planned: 25, phoneOk: true,
  shown: [], items: new Map(), koi: new Map(), ambientList: [], ambient: [], ambientKey: null,
  ripples: [], particles: [], staticDirty: true, shadowK: 1, revealing: false, lastResult: null,
  wasCompleted: false, endPassword: undefined,
};
const view = { tod: null, waterFrom: null, waterStart: 0, tint: [255, 255, 255, 0], caus: 1 };
const cv = $("#pond-canvas"), ctx = cv.getContext("2d");
const stat = document.createElement("canvas"), sctx = stat.getContext("2d");
let k = 1;   // пикселей экрана на единицу дизайн-холста

// ---------------------------------------------------------------- загрузка
function assetNames(cfg) {
  const names = new Set(["koi_shadow", "water_day", "water_dusk", "water_night", "caustics_a", "caustics_b"]);
  const add = (list) => (list || []).forEach((x) => x.asset && names.add(x.asset));
  add(cfg.base.placements); add(cfg.base.koi);
  for (const u of cfg.unlocks) {
    add(u.placements); add(u.replace); add(u.koi);
    if (u.ambient) names.add(u.ambient.asset);
  }
  return [...names];
}

function loadAll(names) {
  return Promise.all(names.map((name) => new Promise((res) => {
    const im = new Image();
    im.onload = () => { imgs[name] = im; res(); };
    im.onerror = () => res();   // нет картинки — просто не рисуем её
    im.src = `pond/img/${name}.webp`;
  })));
}

// Спрайты теней: силуэт + размытие. Считаются один раз.
const shadowCache = new Map();
function shadowSprite(name, blurDesign, drawWidth) {
  const key = name + "|" + blurDesign;
  if (shadowCache.has(key)) return shadowCache.get(key);
  const im = imgs[name];
  const blur = Math.max(1, blurDesign * (im.width / drawWidth));
  const pad = Math.ceil(blur * 2.5);
  const tmp = document.createElement("canvas"); tmp.width = im.width; tmp.height = im.height;
  const t = tmp.getContext("2d"); t.drawImage(im, 0, 0);
  t.globalCompositeOperation = "source-in"; t.fillStyle = "#01161c"; t.fillRect(0, 0, im.width, im.height);
  const c = document.createElement("canvas"); c.width = im.width + pad * 2; c.height = im.height + pad * 2;
  const x = c.getContext("2d"); x.filter = `blur(${blur}px)`; x.drawImage(tmp, pad, pad);
  const sp = { canvas: c, pad };
  shadowCache.set(key, sp);
  return sp;
}

// ---------------------------------------------------------------- время суток
function todNow() {
  if (SHOT && SHOT.tod) return SHOT.tod;
  const n = new Date(), m = n.getHours() * 60 + n.getMinutes();
  const toMin = (s) => { const [h, mm] = s.split(":").map(Number); return h * 60 + mm; };
  for (const t of PAL.timeOfDay) {
    const a = toMin(t.from), b = toMin(t.to);
    if (a < b ? (m >= a && m < b) : (m >= a || m < b)) return t.id;
  }
  return "day";
}

// ---------------------------------------------------------------- сцена
function buildScene(unlocked) {
  const placements = new Map(), koi = new Map(), ambient = [];
  for (const p of CFG.base.placements) placements.set(p.key, { ...p, source: "base" });
  for (const kk of CFG.base.koi) koi.set(kk.key, kk);
  const byId = Object.fromEntries(CFG.unlocks.map((u) => [u.id, u]));
  for (const id of [...unlocked].filter((i) => byId[i]).sort((a, b) => byId[a].order - byId[b].order)) {
    const u = byId[id];
    for (const p of u.placements || []) placements.set(p.key, { ...p, source: id });
    for (const r of u.replace || []) { const p = placements.get(r.key); if (p) placements.set(r.key, { ...p, ...r, source: id }); }
    for (const kk of u.koi || []) koi.set(kk.key, { ...kk, source: id });
    if (u.ambient) ambient.push({ ...u.ambient, source: id });
  }
  return { placements, koi, ambient };
}

function applyScene(revealIds = new Set(), now = performance.now()) {
  const { placements, koi, ambient } = buildScene(P.shown);
  for (const [key, p] of placements) {
    const it = P.items.get(key);
    const reveal = revealIds.has(p.source);
    if (!it) {
      P.items.set(key, { ...p, sway: SWAY_ASSETS.has(p.asset), todA: 1, bob: rnd() * 6.28, bobP: lerp(...VIS.surfaceBob.periodSec, rnd()),
        revealStart: reveal ? now : null });
      if (reveal) addRipple(p.x * DW, p.y * DH, Math.max(140, p.width * DW * 0.9), now, 1800);
    } else if (it.asset !== p.asset || it.width !== p.width) {
      it.prevAsset = it.asset; it.prevWidth = it.width; it.swapStart = now;
      Object.assign(it, p);
      if (reveal) addRipple(p.x * DW, p.y * DH, Math.max(140, p.width * DW * 0.9), now, 1800);
    }
  }
  for (const key of [...P.items.keys()]) if (!placements.has(key)) P.items.delete(key);
  for (const [key, kk] of koi) if (!P.koi.has(key)) addKoi(key, kk, revealIds.has(kk.source), now);
  for (const key of [...P.koi.keys()]) if (!koi.has(key)) P.koi.delete(key);
  P.ambientList = ambient; P.ambientKey = null;
  P.staticDirty = true;
}

// ---------------------------------------------------------------- карпы
function randIn(z) { return [lerp(z.x1, z.x2, rnd()) * DW, lerp(z.y1, z.y2, rnd()) * DH]; }

function addKoi(key, kk, reveal, now) {
  const z = CFG.canvas.swimZone;
  let [x, y] = randIn(z), a = rnd() * Math.PI * 2;
  if (reveal && VIS.reveal.koiEntersFromEdge) {          // новый карп приплывает из-за края
    const side = rnd() < 0.5 ? -1 : 1;
    x = side < 0 ? -120 : DW + 120; y = lerp(0.3, 0.6, rnd()) * DH; a = side < 0 ? 0 : Math.PI;
  }
  const f = { key, asset: kk.asset, len: kk.length * DH, x, y, a, omega: 0, speed: 0, cruise: lerp(0.85, 1.15, rnd()),
    phase: rnd() * 6, slowUntil: 0, attractUntil: 0, revealStart: reveal ? now : null };
  [f.tx, f.ty] = randIn(z);
  if (reveal) { [f.tx, f.ty] = [DW / 2, DH * 0.45]; f.attractUntil = now + 4000; }
  P.koi.set(key, f);
}

function stepKoi(f, dt, now, fishes) {
  const z = CFG.canvas.swimZone;
  const calm = P.running ? MOT.sessionCalm.speedFactor : 1;     // спокойный режим во время сессии
  const slow = (reduceMotion ? 1 / 3 : 1) * calm;
  let desired = Math.atan2(f.ty - f.y, f.tx - f.x);
  for (const o of fishes) if (o !== f) {
    const dx = f.x - o.x, dy = f.y - o.y, d = Math.hypot(dx, dy);
    if (d < 200 && d > 0) desired = Math.atan2(Math.sin(desired) + dy / d * 0.8, Math.cos(desired) + dx / d * 0.8);
  }
  const diff = ((desired - f.a + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
  const maxTurn = MOT.turnRateDegPerSec * Math.PI / 180 * slow * (now < f.attractUntil ? 1.6 : 1);
  const turn = clamp(diff, -maxTurn * dt, maxTurn * dt);
  f.a += turn;
  f.omega = lerp(f.omega, dt > 0 ? turn / dt : 0, Math.min(1, dt * 4));
  if (now > f.slowUntil && now > f.attractUntil && rnd() < dt * 0.04) f.slowUntil = now + 2500 + rnd() * 3500;
  const boost = now < f.attractUntil ? MOT.tapAttraction.speedBoost : 1;
  const dist = Math.hypot(f.tx - f.x, f.ty - f.y);
  let target = MOT.speedCanvasPerSec * DH * f.cruise * slow * boost * (now < f.slowUntil ? 0.3 : 1);
  if (now < f.attractUntil && dist < 160) target *= 0.25;        // у точки касания почти замирает
  f.speed = lerp(f.speed, target, Math.min(1, dt * 0.9));
  f.x += Math.cos(f.a) * f.speed * dt; f.y += Math.sin(f.a) * f.speed * dt;
  if (now > f.attractUntil && dist < 90) [f.tx, f.ty] = randIn(z);
  const base = MOT.speedCanvasPerSec * DH;
  f.phase += dt * Math.PI * 2 * UND.hz * (UND.idleAmplitudeFactor + f.speed / base);
}

function drawKoi(c, f, now, shadow) {
  const im = imgs[shadow ? "koi_shadow" : f.asset];
  if (!im) return;
  const L = f.len, W = L * im.width / im.height;
  const alpha = f.revealStart ? ease((now - f.revealStart) / VIS.reveal.durationMs) : 1;
  const base = MOT.speedCanvasPerSec * DH;
  const amp = UND.amplitude * W * (UND.idleAmplitudeFactor + (1 - UND.idleAmplitudeFactor) * clamp(f.speed / base, 0, 1.5)) * (reduceMotion ? 0.4 : 1);
  c.save();
  if (shadow) {                                       // тень размыта: рисуем одним куском, без изгиба
    const sh = MOT.shadow;
    c.translate(f.x + sh.offset[0], f.y + sh.offset[1]); c.rotate(f.a + Math.PI / 2); c.scale(sh.scale, sh.scale);
    c.globalAlpha = sh.opacity * alpha * P.shadowK;
    c.drawImage(im, -W / 2, -L / 2, W, L); c.restore();
    return;
  }
  // Изгиб: полосы собираем в буфере по ЦЕЛЫМ пикселям, без перекрытий (иначе на плавниках швы),
  // потом буфер рисуем повёрнутым одним вызовом.
  const pad = W * 0.6, bw = Math.ceil((W + pad * 2) * k), bh = Math.ceil(L * k);
  if (!f.buf) { f.buf = document.createElement("canvas"); f.bctx = f.buf.getContext("2d"); }
  if (f.buf.width !== bw || f.buf.height !== bh) { f.buf.width = bw; f.buf.height = bh; }
  const b = f.bctx; b.clearRect(0, 0, bw, bh);
  // Рыбу один раз масштабируем до целых пикселей и режем полосы по целым строкам: так на краях полос
  // нет пересэмплирования по вертикали, и на теле не видно ровных линий-швов.
  const fw = Math.max(1, Math.round(W * k));
  if (!f.sprite || f.sprite.width !== fw || f.sprite.height !== bh || f.spriteAsset !== f.asset) {
    f.sprite = document.createElement("canvas"); f.sprite.width = fw; f.sprite.height = bh; f.spriteAsset = f.asset;
    const s = f.sprite.getContext("2d"); s.imageSmoothingQuality = "high"; s.drawImage(im, 0, 0, fw, bh);
  }
  const N = UND.strips;
  for (let i = 0; i < N; i++) {
    const y0 = Math.round(i * bh / N), y1 = Math.round((i + 1) * bh / N);
    const v = (i + 0.5) / N;
    const env = 0.08 + 0.92 * Math.pow(Math.max(0, (v - 0.2) / 0.8), 1.6);
    const off = amp * env * Math.sin(f.phase - v * Math.PI * 2 * UND.waves) - UND.turnBend * f.omega * v * v * L;
    b.drawImage(f.sprite, 0, y0, fw, y1 - y0, (pad + off) * k, y0, fw, y1 - y0);
  }
  shadeKoi(b, f, W, L, pad, bw, bh, now);
  c.translate(f.x, f.y); c.rotate(f.a + Math.PI / 2); c.globalAlpha = alpha;
  c.drawImage(f.buf, -(W / 2 + pad), -L / 2, bw / k, bh / k);
  c.restore();
}

// Реализм на самом карпе (рисуется поверх уже собранного тела, только там, где есть пиксели рыбы):
// подводный оттенок, светотень поперёк тела от единого света сверху-слева, блики каустики.
function shadeKoi(b, f, W, L, pad, bw, bh, now) {
  const theta = f.a + Math.PI / 2;
  b.save();
  b.setTransform(1, 0, 0, 1, 0, 0);
  b.globalCompositeOperation = "source-atop";
  // вода поглощает красное и контраст: чуть сине-зелёный тон
  b.globalAlpha = 0.14; b.fillStyle = "#0d5560"; b.fillRect(0, 0, bw, bh);
  // свет приходит из (-0.55, -0.83) в мире; в системе рыбы поперечная составляющая:
  const lx = -0.55 * Math.cos(theta) + -0.83 * Math.sin(theta);
  const s = clamp(Math.abs(lx), 0.3, 1) * (lx < 0 ? -1 : 1);
  const cx = (W / 2 + pad) * k, half = W * 0.5 * k;
  const g = b.createLinearGradient(cx + s * half, 0, cx - s * half, 0);   // от освещённого борта к теневому
  g.addColorStop(0, "rgba(255,248,230,0.16)"); g.addColorStop(0.45, "rgba(255,248,230,0)"); g.addColorStop(1, "rgba(0,22,34,0.30)");
  b.globalAlpha = 1; b.fillStyle = g; b.fillRect(0, 0, bw, bh);
  // мягкий блик вдоль спины: вытянутое пятно света на освещённой стороне тела
  b.save();
  b.translate(cx + s * half * 0.3, bh * 0.36); b.scale(1, 3.4);
  const sheen = b.createRadialGradient(0, 0, 0, 0, 0, half * 0.55);
  sheen.addColorStop(0, "rgba(255,252,240,0.26)"); sheen.addColorStop(1, "rgba(255,252,240,0)");
  b.fillStyle = sheen; b.fillRect(-half, -bh, half * 2, bh * 2);
  b.restore();
  // блики каустики на спине: тот же дрейф, что и на дне, в координатах рыбы
  if (view.cl && view.cl.length) {
    b.setTransform(k, 0, 0, k, (W / 2 + pad) * k, (L / 2) * k);
    b.rotate(-theta); b.translate(-f.x, -f.y);
    for (const c of view.cl) { b.globalAlpha = c.a * 0.38; b.drawImage(c.im, c.x, c.y, c.w, c.h); }
  }
  b.restore();
}

// ---------------------------------------------------------------- декор
function drawItem(c, it, now, pass) {
  const im = imgs[it.asset];
  if (!im) return;
  let s = 1, a = it.todA, rot = (it.rotation || 0) * Math.PI / 180;
  if (it.revealStart) { const e = ease((now - it.revealStart) / VIS.reveal.durationMs); s = lerp(VIS.reveal.fromScale, 1, e); a *= e; }
  const sway = it.sway && !reduceMotion ? swayAngle(it, now) : 0;   // ветер: корень на месте, верхушка гуляет
  if (it.layer === "surface" && !reduceMotion) {      // кувшинки и лотосы чуть покачиваются
    const ph = now / 1000 / it.bobP * Math.PI * 2 + it.bob;
    rot += Math.sin(ph) * VIS.surfaceBob.rotationDeg * Math.PI / 180; s *= 1 + Math.sin(ph * 0.7) * VIS.surfaceBob.scale;
  }
  const swapT = it.swapStart ? clamp((now - it.swapStart) / 1200, 0, 1) : 1;
  const layers = swapT < 1 && imgs[it.prevAsset] ? [[it.prevAsset, it.prevWidth, 1 - swapT], [it.asset, it.width, swapT]] : [[it.asset, it.width, 1]];
  for (const [asset, width, kk] of layers) {
    const img = imgs[asset];
    if (!img) continue;
    const w = width * DW, h = w * img.height / img.width;
    c.save();
    if (pass === "shadow") {
      const cfg = VIS.decorShadows[it.layer];
      if (!cfg) { c.restore(); continue; }
      const sp = shadowSprite(asset, cfg.blur, w), r = w / img.width;
      c.translate(it.x * DW + cfg.offset[0], it.y * DH + cfg.offset[1]); c.rotate(rot); c.scale(s, s);
      if (sway) { c.translate(0, h / 2); c.rotate(sway); c.translate(0, -h / 2); }
      c.globalAlpha = cfg.opacity * a * kk * P.shadowK;
      c.drawImage(sp.canvas, -w / 2 - sp.pad * r, -h / 2 - sp.pad * r, sp.canvas.width * r, sp.canvas.height * r);
    } else {
      c.translate(it.x * DW, it.y * DH); c.rotate(rot); c.scale(s, s); c.globalAlpha = a * kk;
      if (sway) { c.translate(0, h / 2); c.rotate(sway); c.translate(0, -h / 2); }
      if (it.layer === "glow") c.globalCompositeOperation = "lighter";
      c.drawImage(img, -w / 2, -h / 2, w, h);
    }
    c.restore();
  }
}
const isAnimating = (it, now) => (it.revealStart && now - it.revealStart < VIS.reveal.durationMs) || (it.swapStart && now - it.swapStart < 1200);

const SWAY_ASSETS = new Set(["reeds", "fern"]);
// Лёгкий ветер: ровное покачивание плюс медленные порывы; период секунд в 7–8, амплитуда ~2°.
function swayAngle(it, now) {
  const t = now / 1000;
  const gust = fbm(t * 0.12 + it.bob, it.bobP, 7, 2) - 0.5;
  return (Math.sin(t * 0.85 + it.bob) * 0.55 + gust * 2.4) * 0.035;
}

function drawStatic(target, now) {
  for (const layer of ["shore", "overhang"]) {
    const items = [...P.items.values()].filter((i) => i.layer === layer && !i.sway);
    for (const it of items) drawItem(target, it, now, "shadow");
    for (const it of items) drawItem(target, it, now, "main");
  }
}

// ---------------------------------------------------------------- эффекты
function addRipple(x, y, r, now, dur = 1800, strength = 1) { P.ripples.push({ x, y, r, start: now, dur, strength }); }

function drawRipples(c, now) {
  P.ripples = P.ripples.filter((rp) => now - rp.start < rp.dur);
  for (const rp of P.ripples) {
    const t = (now - rp.start) / rp.dur;
    if (t < 0) continue;
    const e = ease(t);
    for (let i = 0; i < 2; i++) {
      c.beginPath(); c.arc(rp.x, rp.y, rp.r * lerp(0.15, 1, e) * (1 - i * 0.22), 0, Math.PI * 2);
      c.strokeStyle = `rgba(235,255,250,${(1 - t) * 0.55 * rp.strength * (1 - i * 0.45)})`;
      c.lineWidth = lerp(4, 1, t); c.stroke();
    }
  }
}

function glowDot(c, x, y, r, color, a) {
  const [R, G, B] = hexRgb(color);
  const g = c.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, `rgba(255,255,255,${a})`); g.addColorStop(0.18, `rgba(${R},${G},${B},${a * 0.9})`); g.addColorStop(1, `rgba(${R},${G},${B},0)`);
  c.fillStyle = g; c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fill();
}

// «След времени»: после прерванной сессии частицы света опускаются в воду.
function timeTrail(base, golden, now) {
  const tt = VIS.timeTrail;
  const n = clamp(Math.round(base / tt.perBaseDrops), base > 0 ? 1 : 0, tt.maxBaseParticles);
  const z = CFG.canvas.swimZone;
  for (let i = 0; i < n + golden; i++) {
    const isG = i >= n;
    const [tx, ty] = randIn({ x1: z.x1 + 0.05, x2: z.x2 - 0.05, y1: 0.3, y2: 0.62 });
    P.particles.push({ x0: DW / 2 + (rnd() - 0.5) * 300, y0: DH * 0.86, cx: lerp(DW / 2, tx, 0.3) + (rnd() - 0.5) * 400,
      cy: DH * 0.45, x1: tx, y1: ty, start: now + i * tt.staggerMs, color: isG ? tt.goldenColor : tt.baseColor,
      size: isG ? 26 : 18, rippled: false });
  }
  return (n + golden) * tt.staggerMs + tt.flightMs + tt.sinkMs;
}

function drawParticles(c, now) {
  const tt = VIS.timeTrail;
  P.particles = P.particles.filter((p) => now - p.start < tt.flightMs + tt.sinkMs);
  for (const p of P.particles) {
    const t = now - p.start;
    if (t < 0) continue;
    if (t < tt.flightMs) {
      const u = ease(t / tt.flightMs);
      const x = (1 - u) ** 2 * p.x0 + 2 * (1 - u) * u * p.cx + u * u * p.x1;
      const y = (1 - u) ** 2 * p.y0 + 2 * (1 - u) * u * p.cy + u * u * p.y1;
      glowDot(c, x, y, p.size * (1 + 0.15 * Math.sin(t / 90)), p.color, 0.95);
    } else {
      if (!p.rippled) { addRipple(p.x1, p.y1, 70, now, 1400, 0.8); p.rippled = true; }
      const u = (t - tt.flightMs) / tt.sinkMs;
      glowDot(c, p.x1, p.y1, p.size * (1 - 0.7 * u), p.color, 0.9 * (1 - u));
    }
  }
}

// «Волна завершения»: после завершённой сессии круги от центра, карпы подплывают к центру.
function completionWave(now) {
  const cw = VIS.completionWave;
  for (let i = 0; i < cw.ringCount; i++) addRipple(DW / 2, DH * 0.45, 520 + i * 90, now + i * 380, cw.durationMs, 1);
  for (const f of P.koi.values()) {
    const a = rnd() * 6.28;
    f.tx = DW / 2 + Math.cos(a) * 150; f.ty = DH * 0.45 + Math.sin(a) * 150; f.attractUntil = now + cw.gatherMs;
  }
  return cw.durationMs;
}

// Светлячки и лепестки.
function syncAmbient(tod) {
  const want = P.ambientList.filter((a) => !a.timeOfDay || a.timeOfDay.includes(tod));
  const key = want.map((a) => a.type).join(",") + (reduceMotion ? "r" : "");
  if (P.ambientKey === key) return;
  P.ambientKey = key; P.ambient = [];
  if (reduceMotion) return;
  for (const a of want) for (let i = 0; i < a.count; i++) {
    P.ambient.push({ type: a.type, asset: a.asset, size: a.size * DW, x: rnd() * DW, y: rnd() * DH,
      t: rnd() * 10, rot: rnd() * 360, i });
  }
}

function drawAmbient(c, dt) {
  for (const p of P.ambient) {
    p.t += dt;
    if (p.type === "fireflies") {
      p.x += Math.sin(p.t * 0.5 + p.i) * 6 * dt; p.y += Math.cos(p.t * 0.4 + p.i * 2) * 8 * dt;
      glowDot(c, p.x, p.y, p.size * 0.5, "#E9FF9E", 0.3 + 0.6 * Math.max(0, Math.sin(p.t * 1.3 + p.i)));
    } else {
      p.x += 12 * dt; p.y += 13 * dt; p.rot += 25 * dt;
      if (p.x > DW + 40 || p.y > DH + 40) { p.x = -30; p.y = rnd() * DH * 0.8; }
      const im = imgs[p.asset];
      if (!im) continue;
      c.save(); c.translate(p.x, p.y); c.rotate(p.rot * Math.PI / 180);
      const w = p.size, h = w * im.height / im.width; c.globalAlpha = 0.9; c.drawImage(im, -w / 2, -h / 2, w, h); c.restore();
    }
  }
}

// ---------------------------------------------------------------- текстуры света (считаются один раз)
// Детерминированный шум: не зависит от rnd(), поэтому картинка одинакова при каждом запуске.
function hash2(x, y, s) {
  let h = (Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(s, 1442695041)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
function vnoise(x, y, s) {
  const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const a = hash2(xi, yi, s), b = hash2(xi + 1, yi, s), c = hash2(xi, yi + 1, s), d = hash2(xi + 1, yi + 1, s);
  return lerp(lerp(a, b, u), lerp(c, d, u), v);
}
function fbm(x, y, s, octaves = 5) {
  let v = 0, amp = 0.5, f = 1;
  for (let i = 0; i < octaves; i++) { v += amp * vnoise(x * f, y * f, s + i); f *= 2.02; amp *= 0.5; }
  return v;
}
// Серая текстура вокруг 128: нейтральна для soft-light/overlay, светлее и темнее — пятна света.
function noiseTexture(w, h, scale, seed, contrast) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const x = c.getContext("2d"), img = x.createImageData(w, h);
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
    const n = (fbm(i / w * scale, j / h * scale * (h / w), seed) - 0.5) * 2.2 * contrast;
    const g = clamp(128 + n * 128, 0, 255), o = (j * w + i) * 4;
    img.data[o] = img.data[o + 1] = img.data[o + 2] = g; img.data[o + 3] = 255;
  }
  x.putImageData(img, 0, 0);
  return c;
}
function grainTexture(size, seed) {
  const c = document.createElement("canvas"); c.width = c.height = size;
  const x = c.getContext("2d"), img = x.createImageData(size, size);
  for (let i = 0; i < size * size; i++) {
    const g = clamp(128 + (hash2(i % size, (i / size) | 0, seed) - 0.5) * 120, 0, 255);
    img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = g; img.data[i * 4 + 3] = 255;
  }
  x.putImageData(img, 0, 0);
  return c;
}
const FX = {};
// Отдельный генератор для зерна: не сдвигает последовательность rnd(), поэтому скриншоты сравнимы.
const frng = SHOT ? (() => { let n = 0; return () => hash2(n++, 7, 3); })() : Math.random;
// Положение и яркость слоёв каустики в этот момент (общее для воды и для света на карпах).
function causticLayers(now) {
  const t = now / 1000, out = [];
  VIS.caustics.layers.forEach((L, i) => {
    const im = FX["soft_" + L.asset.split("/").pop()] || imgs[L.asset.split("/").pop()];
    if (!im) return;
    const per = L.swayPeriodSec, w = DW * L.scale, h = DH * L.scale;
    const dx = L.swayAmplitudePx * Math.sin(t / per * 6.283 + i) + L.driftPxPerSec[0] * per / 4 * Math.sin(t / (per * 3) * 6.283);
    const dy = L.swayAmplitudePx * Math.cos(t / (per * 1.3) * 6.283 + i) + L.driftPxPerSec[1] * per / 4 * Math.sin(t / (per * 2.6) * 6.283);
    out.push({ im, x: (DW - w) / 2 + dx, y: (DH - h) / 2 + dy, w, h, a: L.alpha * 0.9 * view.caus });
  });
  return out;
}
// Размытая копия картинки (один раз при загрузке): мягкие края каустики.
function softCopy(im, blurPx) {
  const c = document.createElement("canvas"); c.width = im.width; c.height = im.height;
  const x = c.getContext("2d"); x.filter = `blur(${blurPx}px)`; x.drawImage(im, 0, 0);
  return c;
}
function buildFx() {
  for (const L of VIS.caustics.layers) {
    const name = L.asset.split("/").pop();
    if (imgs[name]) FX["soft_" + name] = softCopy(imgs[name], 3.6);
  }
  FX.mottle = noiseTexture(200, 320, 4.5, 11, 1.0);    // крупные пятна света и глубины на воде
  FX.haze = noiseTexture(200, 320, 2.6, 23, 1.0);      // дымка над водой
  FX.grain = grainTexture(128, 5);
}

// Пылинки и пыльца в воздухе над водой: очень редкие, медленные, видны только при свете.
function buildMotes() {
  P.motes = Array.from({ length: 26 }, (_, i) => ({
    x: hash2(i, 1, 5) * DW, y: hash2(i, 2, 5) * DH, r: lerp(5, 13, hash2(i, 3, 5)), t: hash2(i, 4, 5) * 10, a: lerp(0.35, 1, hash2(i, 5, 5)), i,
  }));
}
function drawMotes(c, dt) {
  if (reduceMotion || !P.motes) return;
  const light = view.caus;                           // днём заметнее, ночью почти нет
  c.globalCompositeOperation = "lighter";
  for (const m of P.motes) {
    m.t += dt;
    m.x += (fbm(m.y * 0.004, m.t * 0.05, 3, 2) - 0.5) * 18 * dt + 3 * dt;
    m.y += (fbm(m.x * 0.004, m.t * 0.05, 9, 2) - 0.5) * 14 * dt - 1.5 * dt;
    if (m.x > DW + 20) m.x = -20; if (m.x < -20) m.x = DW + 20;
    if (m.y < -20) m.y = DH + 20; if (m.y > DH + 20) m.y = -20;
    glowDot(c, m.x, m.y, m.r, "#EFFFF2", 0.16 * light * m.a * (0.6 + 0.4 * Math.sin(m.t * 0.7 + m.i)));
  }
  c.globalCompositeOperation = "source-over";
}

// Финальная обработка кадра: воздух, свет сверху-слева, спокойные цвета, виньетка, зерно.
function drawFinish(c, now) {
  const k0 = view.caus;                                  // днём сильнее, ночью слабее (то же, что у каустики)
  const drift = reduceMotion ? 0 : Math.sin(now / 1000 / 47 * Math.PI * 2) * 34;
  // дымка
  c.globalCompositeOperation = "screen"; c.globalAlpha = 0.085 * k0;
  c.drawImage(FX.haze, -150 + drift, -200 - drift * 0.5, DW * 1.3, DH * 1.3);
  // единый свет: диагональ от верхнего левого угла
  const lg = c.createLinearGradient(0, 0, DW * 0.75, DH * 0.55);
  lg.addColorStop(0, `rgba(255,246,216,${0.2 * k0})`); lg.addColorStop(0.5, `rgba(255,246,216,${0.05 * k0})`); lg.addColorStop(1, "rgba(255,246,216,0)");
  c.globalAlpha = 1; c.fillStyle = lg; c.fillRect(0, 0, DW, DH);
  // спокойные цвета: немного убираем насыщенность
  c.globalCompositeOperation = "saturation"; c.globalAlpha = 0.2; c.fillStyle = "#808080"; c.fillRect(0, 0, DW, DH);
  // виньетка всегда лёгкая (во время сессии ещё усиливается отдельно)
  c.globalCompositeOperation = "source-over"; c.globalAlpha = 1;
  const vg = c.createRadialGradient(DW / 2, DH * 0.5, DH * 0.3, DW / 2, DH * 0.5, DH * 0.78);
  vg.addColorStop(0, "rgba(2,12,18,0)"); vg.addColorStop(1, "rgba(2,12,18,0.36)");
  c.fillStyle = vg; c.fillRect(0, 0, DW, DH);
  // зерно: едва заметное, сдвигается, чтобы не было «сетки»
  c.globalCompositeOperation = "overlay"; c.globalAlpha = 0.07;
  const gx = (frng() * 128) | 0, gy = (frng() * 128) | 0;
  c.save(); c.scale(3, 3); c.translate(-gx, -gy);
  c.fillStyle = c.createPattern(FX.grain, "repeat"); c.fillRect(gx, gy, DW / 3 + 1, DH / 3 + 1); c.restore();
  c.globalCompositeOperation = "source-over"; c.globalAlpha = 1;
}

// ---------------------------------------------------------------- кадр
function resize() {
  const r = cv.getBoundingClientRect();
  if (r.width < 2) return;
  const dpr = SHOT && Q.has("dpr") ? parseFloat(Q.get("dpr")) : Math.min(devicePixelRatio || 1, VIS.performance.maxDevicePixelRatio);
  cv.width = stat.width = Math.round(r.width * dpr); cv.height = stat.height = Math.round(r.height * dpr);
  k = cv.width / DW; P.staticDirty = true;
}

let last = 0, lastDraw = 0, nextKiss = 0;
const pondVisible = () => $("#tab-pond").classList.contains("active") && !document.hidden && !P.hidden;

function frame(now) {
  // Отрисовка полностью останавливается, если пруд не виден: другая вкладка, свёрнутое окно, «Скрыть пруд».
  if (!pondVisible()) { P.looping = false; return; }
  requestAnimationFrame(frame);
  if (now - lastDraw < 1000 / VIS.performance.targetFps - 2) return;
  const dt = Math.min(0.06, (now - last) / 1000);
  last = now; lastDraw = now;
  render(now, dt);
}

// Один кадр: обновляет мир на dt секунд и рисует его. Отдельно от frame(), чтобы режим скриншота
// мог прокрутить анимацию детерминированными шагами.
function render(now, dt) {
  const tod = todNow();
  if (tod !== view.tod) { view.waterFrom = view.tod; view.waterStart = now; view.tod = tod; P.staticDirty = true; syncAmbient(tod); }
  const ov = PAL.overlay[tod], target = [...hexRgb(ov.color), ov.opacity];
  view.tint = view.tint.map((v, i) => lerp(v, target[i], Math.min(1, dt * 1.5)));
  view.caus = lerp(view.caus, VIS.caustics.todAlpha[tod], Math.min(1, dt * 1.5));
  P.shadowK = lerp(P.shadowK, tod === "night" ? 0.45 : tod === "dusk" ? 0.8 : 1, Math.min(1, dt * 1.5));
  for (const it of P.items.values()) it.todA = lerp(it.todA, !it.timeOfDay || it.timeOfDay.includes(tod) ? 1 : 0, Math.min(1, dt * 1.5));

  const fishes = [...P.koi.values()];
  for (const f of fishes) stepKoi(f, dt, now, fishes);
  if (now > nextKiss && fishes.length && !reduceMotion) {            // рыба касается поверхности — круг у головы
    const f = fishes[Math.floor(rnd() * fishes.length)];
    addRipple(f.x + Math.cos(f.a) * f.len * 0.42, f.y + Math.sin(f.a) * f.len * 0.42, 70, now, 1600, 0.7);
    nextKiss = now + lerp(...MOT.surfaceKissEverySec, rnd()) * 1000;
  }

  ctx.setTransform(k, 0, 0, k, 0, 0);
  // 1. вода (с перетеканием между временами суток)
  const wt = view.waterFrom ? clamp((now - view.waterStart) / 1600, 0, 1) : 1;
  if (wt < 1 && imgs["water_" + view.waterFrom]) { ctx.globalAlpha = 1; ctx.drawImage(imgs["water_" + view.waterFrom], 0, 0, DW, DH); }
  if (imgs["water_" + tod]) { ctx.globalAlpha = wt; ctx.drawImage(imgs["water_" + tod], 0, 0, DW, DH); }
  ctx.globalAlpha = 1;
  // 1б. пятна света и глубины: вода перестаёт быть ровной заливкой
  ctx.globalCompositeOperation = "soft-light"; ctx.globalAlpha = 0.5 + 0.2 * view.caus;
  const md = reduceMotion ? 0 : Math.sin(now / 1000 / 61 * Math.PI * 2) * 40;
  ctx.drawImage(FX.mottle, -140 + md, -180 - md * 0.6, DW * 1.3, DH * 1.3);
  ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = 1;
  // 2. каустика: два слоя дрейфуют навстречу друг другу (мягкие копии: резкая сетка выглядела как трещины)
  view.cl = reduceMotion ? [] : causticLayers(now);
  if (view.cl.length) {
    ctx.globalCompositeOperation = "screen";
    for (const c of view.cl) { ctx.globalAlpha = c.a * (P.running ? 0.8 : 1); ctx.drawImage(c.im, c.x, c.y, c.w, c.h); }
    ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = 1;
  }
  // 3–4. тени карпов на дне и сами карпы
  for (const f of fishes) drawKoi(ctx, f, now, true);
  for (const f of fishes) drawKoi(ctx, f, now, false);
  // 5. кувшинки и лотосы
  const surface = [...P.items.values()].filter((i) => i.layer === "surface");
  for (const it of surface) drawItem(ctx, it, now, "shadow");
  for (const it of surface) drawItem(ctx, it, now, "main");
  // 6. берег и нависающие ветки: из кэша, пока ничего не анимируется
  const staticAnim = [...P.items.values()].some((it) => (it.layer === "shore" || it.layer === "overhang") && isAnimating(it, now));
  if (staticAnim) { drawStatic(ctx, now); P.staticDirty = true; }
  else {
    if (P.staticDirty) {
      sctx.setTransform(1, 0, 0, 1, 0, 0); sctx.clearRect(0, 0, stat.width, stat.height);
      sctx.setTransform(k, 0, 0, k, 0, 0); drawStatic(sctx, now); P.staticDirty = false;
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.drawImage(stat, 0, 0); ctx.setTransform(k, 0, 0, k, 0, 0);
  }
  // 6б. качающиеся от ветра растения рисуем каждый кадр (в кэш берега они не попадают)
  const swaying = [...P.items.values()].filter((i) => i.sway);
  for (const it of swaying) drawItem(ctx, it, now, "shadow");
  for (const it of swaying) drawItem(ctx, it, now, "main");
  // 7. тонировка времени суток
  const [r, g, b, a] = view.tint;
  if (a > 0.005) {
    ctx.globalCompositeOperation = "multiply"; ctx.globalAlpha = a; ctx.fillStyle = `rgb(${r | 0},${g | 0},${b | 0})`;
    ctx.fillRect(0, 0, DW, DH); ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = 1;
  }
  // 8. виньетка во время сессии
  if (P.running) {
    const vg = ctx.createRadialGradient(DW / 2, DH * 0.45, DH * 0.2, DW / 2, DH * 0.45, DH * 0.75);
    vg.addColorStop(0, "rgba(2,14,20,0)"); vg.addColorStop(1, `rgba(2,14,20,${MOT.sessionCalm.vignetteOpacity})`);
    ctx.fillStyle = vg; ctx.fillRect(0, 0, DW, DH);
  }
  // 8б. воздух, свет, цвет, виньетка, зерно
  drawFinish(ctx, now);
  drawMotes(ctx, dt);
  // 9. свечение, атмосфера, круги, частицы
  for (const it of P.items.values()) if (it.layer === "glow") drawItem(ctx, it, now, "main");
  drawAmbient(ctx, dt);
  drawRipples(ctx, now);
  drawParticles(ctx, now);
}

function wake() {
  if (!P.ready || P.looping || !pondVisible()) return;
  P.looping = true; last = performance.now(); resize();
  requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- касание воды
cv.addEventListener("pointerdown", (e) => {
  if (!P.ready || P.running) return;                       // во время сессии отключено
  const r = cv.getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width * DW, y = (e.clientY - r.top) / r.height * DH;
  const now = performance.now();
  addRipple(x, y, 120, now, 1700, 0.9);
  if (!MOT.tapAttraction.enabled) return;
  const near = [...P.koi.values()].sort((a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y)).slice(0, MOT.tapAttraction.maxKoi);
  const z = CFG.canvas.swimZone;
  for (const f of near) { f.tx = clamp(x, z.x1 * DW, z.x2 * DW); f.ty = clamp(y, z.y1 * DH, z.y2 * DH); f.attractUntil = now + MOT.tapAttraction.durationMs; }
  $("#pond-tap").style.opacity = 0;
});

// ---------------------------------------------------------------- интерфейс
let toastTimer;
function pondToast(kicker, text) {
  $("#pond-toastk").textContent = kicker; $("#pond-toastk").style.display = kicker ? "" : "none";
  $("#pond-toastt").textContent = text; $("#pond-toast").classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $("#pond-toast").classList.remove("show"), 2600);
}

function setHidden(h) {
  P.hidden = h;
  $("#pond-sleep").classList.toggle("on", h);
  $("#pond-hide").textContent = h ? STR["session.showPond"] : STR["session.hidePond"];
  if (!h) wake();
}

const sheet = (id, on) => $(id).classList.toggle("show", on);

function setIdleTexts() {
  $("#pond-title").textContent = P.running ? STR["session.running"] : STR["pond.title"];
  $("#pond-subtitle").textContent = P.running ? "" : STR["pond.subtitle"];
  $("#pond-jbtn").hidden = P.running;
}

// Состояние сессии приходит с сервера раз в секунду.
function sync(s) {
  if (!P.ready) return;
  const sess = s.session;
  const was = P.running;
  P.running = !!sess;
  P.phoneOk = !!(s.phone && s.phone.docked);
  $("#pond-idle").hidden = P.running;
  $("#pond-run").hidden = !P.running;
  if (sess) $("#pond-timer").textContent = formatTime(sess.remaining_s);
  $("#pond-start").disabled = !P.phoneOk;
  $("#pond-phone-need").hidden = P.phoneOk;
  if (was !== P.running) {
    setIdleTexts();
    if (!P.running) { setHidden(false); sheet("#pond-reason", false); }
    else sheet("#pond-result", false);
  }
}

async function startSession() {
  try {
    sync(await api("POST", "/api/session/start", { length_min: P.planned }));
  } catch (_) { /* текст ошибки уже показан */ }
}

function askStop() {
  const pw = askStrictPassword("завершить сессию досрочно");   // в строгом режиме нужен пароль
  if (pw === null) return;
  P.endPassword = pw;
  $("#pond-note").hidden = true;
  sheet("#pond-reason", true);
}

async function endSession(code, note) {
  const body = { reason_code: code || null, reason_note: note || null };
  if (P.endPassword) body.password = P.endPassword;
  try {
    await api("POST", "/api/session/end", body);
    sheet("#pond-reason", false);
  } catch (_) { /* неверный пароль и т. п.: шторка остаётся, можно повторить или вернуться */ }
}

// Экран результата показываем по событию «сессия закончилась» (и ручное, и по таймеру).
async function showResult(sessionId) {
  const res = await api("GET", `/api/pond/result?session_id=${sessionId}`).catch(() => null);
  if (!res || !res.status) return;
  P.lastResult = res;
  const minutes = res.minutes;
  const hasReason = res.status === "interrupted_with_reason";
  $("#pond-restitle").textContent = res.completed ? STR["complete.title"] : "Сессия завершена раньше";
  $("#pond-resmsg").textContent = res.status === "too_short" ? STR["interrupt.tooShort"]
    : res.completed ? fmt(STR["complete.saved"], { minutes })
      : hasReason ? fmt(STR["interrupt.savedWithReason"], { minutes }) : fmt(STR["interrupt.saved"], { minutes });
  $("#pond-resclose").textContent = res.completed ? STR["complete.close"] : STR["interrupt.close"];
  sheet("#pond-result", true);
}

function closeResult() {
  sheet("#pond-result", false);
  const res = P.lastResult;
  P.lastResult = null;
  P.wasCompleted = !!(res && res.completed);
  let wait = 600;
  if (res && res.completed) wait = completionWave(performance.now()) * 0.6;
  else if (res && res.base > 0) { wait = timeTrail(res.base, res.golden, performance.now()); pondToast("", STR["trail.saved"]); }
  setTimeout(playReveals, wait);
}

// Новые открытия появляются по одному, только когда сессии нет (во время сессии пруд ничего не показывает).
async function playReveals() {
  if (P.revealing || P.running || !P.ready) return;
  const st = await api("GET", "/api/pond").catch(() => null);
  if (!st) return;
  const fresh = st.unseen.filter((id) => !P.shown.includes(id));
  if (!fresh.length) {
    if (P.wasCompleted) pondToast("", STR["complete.nothingNew"]);
    P.wasCompleted = false;
    return;
  }
  P.wasCompleted = false;
  P.revealing = true;
  fresh.forEach((id, i) => setTimeout(() => {
    const u = CFG.unlocks.find((x) => x.id === id);
    P.shown.push(id);
    applyScene(new Set([id]), performance.now());
    if (u) pondToast(STR["reveal.newTitle"], u.reveal);
    if (i === fresh.length - 1) {
      api("POST", "/api/pond/seen", { ids: st.unseen }).catch(() => {});
      setTimeout(() => { P.revealing = false; }, VIS.reveal.gapMs);
    }
  }, i * VIS.reveal.gapMs));
}

async function openJournal() {
  const st = await api("GET", "/api/pond");
  const total = st.journal.focus_min;
  $("#pond-jtitle").textContent = STR["journal.title"];
  $("#pond-jstats").innerHTML = fmt(STR["journal.total"], { hours: Math.floor(total / 60), minutes: total % 60 }) + "<br>"
    + fmt(STR["journal.days"], { days: st.journal.days });
  const date = (s) => new Date(s + "T12:00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  const span = (text) => Object.assign(document.createElement("span"), { textContent: text });
  const list = $("#pond-jlist");
  list.replaceChildren();
  if (!st.unlocked.length) {
    const li = document.createElement("li");
    li.append(span(""), span(STR["journal.empty"]));
    list.append(li);
  }
  for (const u of st.unlocked) {
    const li = document.createElement("li");
    li.append(span(date(u.date)), span(u.title));
    list.append(li);
  }
  sheet("#pond-journal", true);
}

function bindUi() {
  $("#pond-jbtn").textContent = STR["journal.button"]; $("#pond-jclose").textContent = STR["journal.close"];
  $("#pond-nodistr").textContent = STR["pond.noDistractions"]; $("#pond-start").textContent = STR["pond.start"];
  $("#pond-stop").textContent = STR["session.stop"]; $("#pond-hide").textContent = STR["session.hidePond"];
  $("#pond-sleep").textContent = STR["session.hiddenHint"]; $("#pond-tap").textContent = STR["pond.tapHint"];
  $("#pond-reasonq").textContent = REASONS.question; $("#pond-skip").textContent = REASONS.skipLabel;
  $("#pond-durations").innerHTML = [25, 45, 60].map((m) => `<button class="pond-chip ${m === P.planned ? "on" : ""}" data-m="${m}">${m} мин</button>`).join("");
  $("#pond-durations").onclick = (e) => {
    const b = e.target.closest(".pond-chip");
    if (!b) return;
    P.planned = +b.dataset.m;
    document.querySelectorAll(".pond-chip").forEach((c) => c.classList.toggle("on", c === b));
  };
  $("#pond-reasons").replaceChildren(...REASONS.reasons.map((r) => Object.assign(document.createElement("button"), {
    className: "pond-reason", textContent: `${r.emoji}  ${r.label}`,
    onclick: () => {
      if (r.allowsNote) { $("#pond-note").hidden = false; $("#pond-note-input").focus(); }
      else endSession(r.code);
    },
  })));
  $("#pond-note-ok").onclick = () => endSession("other", $("#pond-note-input").value);
  $("#pond-skip").onclick = () => endSession(null);
  $("#pond-back").onclick = () => sheet("#pond-reason", false);
  $("#pond-start").onclick = startSession;
  $("#pond-stop").onclick = askStop;
  $("#pond-hide").onclick = () => setHidden(!P.hidden);
  $("#pond-resclose").onclick = closeResult;
  $("#pond-jbtn").onclick = openJournal;
  $("#pond-jclose").onclick = () => sheet("#pond-journal", false);
  setIdleTexts();
}

// ---------------------------------------------------------------- скриншот
// Прокручивает мир шагами по 1/30 с до момента t и рисует один кадр. Потом window.__pondShot = true.
function runShot() {
  if (SHOT.all) { P.shown = CFG.unlocks.map((u) => u.id); applyScene(); }
  P.looping = true; resize();
  const step = 1 / 30;
  let now = 0;
  const t0 = performance.now(), n = Math.round(SHOT.t * 30);
  for (let i = 0; i < n; i++) { now += step * 1000; render(now, step); }
  window.__pondMsPerFrame = (performance.now() - t0) / Math.max(1, n);   // замер: сколько мс уходит на кадр
  window.__pondShot = true;
}

// ---------------------------------------------------------------- запуск
async function init() {
  try {
    const cfg = await api("GET", "/api/pond/config");
    CFG = cfg.progression; VIS = cfg.visual; PAL = cfg.palette; STR = cfg.strings; REASONS = cfg.reasons;
    DW = CFG.canvas.width; DH = CFG.canvas.height; MOT = VIS.koi; UND = VIS.koi.undulation;
    await loadAll(assetNames(CFG));
    buildFx(); buildMotes();
    const st = await api("GET", "/api/pond");
    P.shown = st.unlocked.map((u) => u.id).filter((id) => !st.unseen.includes(id));   // непоказанное появится анимацией
    bindUi();
    applyScene();
    $("#pond-loading").remove();
    P.ready = true;
    if (!SHOT) new ResizeObserver(resize).observe($("#pond-stage"));   // в режиме скриншота resize очистил бы кадр
    document.addEventListener("visibilitychange", wake);
    setTimeout(() => { $("#pond-tap").style.opacity = 0; }, 6000);
    nextKiss = performance.now() + 6000;
    if (SHOT) return runShot();
    wake();
    setTimeout(playReveals, 1200);
  } catch (err) {
    const el = $("#pond-loading");
    if (el) el.textContent = "Не удалось загрузить пруд";
    console.error(err);
  }
}

tabLoaders.pond = () => { wake(); playReveals(); };
renderHooks.push(sync);
eventHooks.push((e) => { if (e.type === "session_ended" && e.session_id) showResult(e.session_id); });
init();
