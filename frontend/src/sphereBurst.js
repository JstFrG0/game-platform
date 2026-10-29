// A short-lived canvas snapshot; years and selection remain real HTML controls.
export function playSphereBurst(host, orbit, curves, radius, options = {}) {
  const reverse = Boolean(options.reverse);
  const from = Math.max(0, Math.min(3900, options.from ?? 3900));
  const width = host.clientWidth, height = host.clientHeight;
  const stage = orbit.parentElement;
  const size = orbit.clientWidth;
  const center = { x: stage.offsetLeft + size / 2, y: stage.offsetTop + size / 2 };
  const ratio = Math.min(window.devicePixelRatio || 1, 1.5, 1800 / width, 1200 / height);
  const canvas = document.createElement("canvas");
  canvas.className = "sphere-burst-canvas";
  canvas.dataset.mode = reverse ? "rebuild" : "explode";
  canvas.setAttribute("aria-hidden", "true");
  canvas.width = Math.ceil(width * ratio); canvas.height = Math.ceil(height * ratio);
  Object.assign(canvas.style, { position: "absolute", inset: "0", width: `${width}px`, height: `${height}px`, pointerEvents: "none", zIndex: "1" });
  const ctx = canvas.getContext("2d");
  const source = document.createElement("canvas");
  source.width = Math.ceil(size * ratio); source.height = Math.ceil(size * ratio);
  const ink = source.getContext("2d");
  if (!ctx || !ink) throw new Error("Canvas unavailable");
  const meshScale = size / 400;
  ink.scale(ratio * meshScale, ratio * meshScale);
  for (const curve of curves) {
    ink.strokeStyle = curve.axis ? "#aecdf4" : "#99bae3";
    ink.globalAlpha = curve.axis ? (curve.back ? .1 : .36) : (curve.back ? .055 : .2);
    ink.lineWidth = .65;
    ink.stroke(new Path2D(curve.d));
  }
  ink.globalAlpha = 1;
  let seed = 76471;
  function random() { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }
  const r = size * radius;
  const rings = [0, .34, .69, 1], count = 12;
  function point(ring, sector) {
    const angle = sector * Math.PI * 2 / count;
    return { x: Math.cos(angle) * r * rings[ring], y: Math.sin(angle) * r * rings[ring] };
  }
  const fragments = [];
  function fragment(points) {
    const x = points.reduce((sum, p) => sum + p.x, 0) / 3;
    const y = points.reduce((sum, p) => sum + p.y, 0) / 3;
    const minX = Math.floor(Math.min(...points.map(p => p.x))), minY = Math.floor(Math.min(...points.map(p => p.y)));
    const w = Math.ceil(Math.max(...points.map(p => p.x)) - minX) + 2;
    const h = Math.ceil(Math.max(...points.map(p => p.y)) - minY) + 2;
    const tile = document.createElement("canvas");
    tile.width = Math.ceil(w * ratio); tile.height = Math.ceil(h * ratio);
    const paint = tile.getContext("2d");
    paint.scale(ratio, ratio);
    paint.beginPath();
    points.forEach((p, i) => i ? paint.lineTo(p.x - minX, p.y - minY) : paint.moveTo(p.x - minX, p.y - minY));
    paint.closePath(); paint.clip();
    paint.fillStyle = "rgb(139 182 235 / 6%)"; paint.fillRect(0, 0, w, h);
    paint.drawImage(source, 0, 0, source.width, source.height, -minX - size / 2, -minY - size / 2, size, size);
    paint.strokeStyle = "rgb(151 192 241 / 22%)"; paint.lineWidth = .65; paint.stroke();
    const angle = Math.atan2(y, x) + (random() - .5) * .7;
    const distance = Math.hypot(x, y) + 80 + random() * Math.max(width, height) * .32;
    const marginX = Math.min(80, width * .15), marginY = Math.min(120, height * .2);
    const tx = Math.max(marginX, Math.min(width - marginX, center.x + Math.cos(angle) * distance));
    const ty = Math.max(marginY, Math.min(height - 70, center.y + Math.sin(angle) * distance));
    const turn = (random() - .5) * 2.8;
    const dustAngle = random() * Math.PI * 2;
    const dust = Array.from({ length: 16 }, () => {
      const a = Math.sqrt(random()), b = random();
      const px = points[0].x * (1 - a) + points[1].x * a * (1 - b) + points[2].x * a * b - x;
      const py = points[0].y * (1 - a) + points[1].y * a * (1 - b) + points[2].y * a * b - y;
      const direction = dustAngle + (random() - .5) * 1.8;
      const speed = 24 + random() * 86;
      return { x: px * Math.cos(turn) - py * Math.sin(turn), y: px * Math.sin(turn) + py * Math.cos(turn),
        dx: Math.cos(direction) * speed, dy: Math.sin(direction) * speed, size: .7 + random() * 1.7, opacity: .16 + random() * .3 };
    });
    fragments.push({ x, y, minX, minY, w, h, tile, tx, ty, turn, dust, start: 1500 + random() * 500, duration: 1200 + random() * 600 });
  }
  for (let sector = 0; sector < count; sector++) {
    fragment([{ x: 0, y: 0 }, point(1, sector), point(1, sector + 1)]);
    for (let ring = 1; ring < 3; ring++) {
      const a = point(ring, sector), b = point(ring, sector + 1), c = point(ring + 1, sector), d = point(ring + 1, sector + 1);
      fragment([a, c, d]); fragment([a, d, b]);
    }
  }
  host.append(canvas);
  fragments.forEach((f, i) => { f.returnDelay = Math.floor(i / 5) * 90 + (i % 5) * 18; });
  const returnDuration = fragments.at(-1).returnDelay + 1130;
  let revealed = false;
  let frame = 0, stopped = false;
  function stop() {
    if (stopped) return;
    stopped = true; cancelAnimationFrame(frame); canvas.remove();
    fragments.forEach(f => { f.tile.width = 1; f.tile.height = 1; });
    fragments.length = 0; source.width = 1; source.height = 1; canvas.width = 1; canvas.height = 1;
  }
  const started = performance.now();
  function draw(now) {
    if (stopped) return;
    const elapsed = now - started;
    canvas.dataset.phase = reverse
      ? elapsed < 400 ? "reappear" : elapsed < returnDuration - 180 ? "reassemble" : "complete"
      : elapsed < 650 ? "scatter" : elapsed < 1500 ? "hold" : "dust";
    if (reverse && !revealed && elapsed >= returnDuration - 180) {
      revealed = true; options.onReveal?.();
    }
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
    let assembled = 0, pending = 0, returning = 0;
    for (const f of fragments) {
      let ease, dust, alpha;
      if (reverse) {
        const appear = Math.max(0, Math.min(1, (elapsed - f.returnDelay) / 170));
        // Appearance and return start together for each shard, with overlapping batches.
        const fly = Math.max(0, Math.min(1, (elapsed - f.returnDelay) / 950));
        const previousDust = Math.max(0, Math.min(1, (from - f.start) / f.duration));
        const previousAlpha = Math.max(0, 1 - previousDust * 2.1);
        ease = (1 - (1 - Math.min(1, from / 650)) ** 3) * (1 - fly) ** 3;
        dust = previousDust * (1 - appear);
        alpha = (previousAlpha + (1 - previousAlpha) * appear)
          * (1 - Math.max(0, Math.min(1, (elapsed - returnDuration + 180) / 180)));
        if (fly === 1) assembled++;
        else if (fly > 0) returning++;
        if (appear === 0) pending++;
      } else {
        const travel = Math.min(1, elapsed / 650);
        ease = 1 - (1 - travel) ** 3;
        dust = Math.max(0, Math.min(1, (elapsed - f.start) / f.duration));
        alpha = Math.max(0, 1 - dust * 2.1);
      }
      const x = center.x + f.x + (f.tx - center.x - f.x) * ease;
      const y = center.y + f.y + (f.ty - center.y - f.y) * ease;
      if (!reverse && dust >= 1) continue;
      ctx.save(); ctx.translate(x, y); ctx.rotate(f.turn * ease);
      ctx.globalAlpha = alpha;
      ctx.drawImage(f.tile, f.minX - f.x, f.minY - f.y, f.w, f.h); ctx.restore();
      if (dust > 0) {
        ctx.fillStyle = "#9bbfe9";
        for (const p of f.dust) {
          ctx.globalAlpha = Math.min(1, dust * 8) * (1 - dust) * p.opacity;
          ctx.fillRect(f.tx + p.x + p.dx * dust, f.ty + p.y + p.dy * dust, p.size * (1 - dust * .6), p.size * (1 - dust * .6));
        }
      }
    }
    if (reverse) {
      canvas.dataset.assembled = String(assembled);
      canvas.dataset.pending = String(pending);
      canvas.dataset.returning = String(returning);
    }
    ctx.globalAlpha = 1;
    if (elapsed < (reverse ? returnDuration : 3900)) frame = requestAnimationFrame(draw);
    else { stop(); if (reverse) options.onComplete?.(); }
  }
  draw(started);
  stop.elapsed = () => Math.min(3900, performance.now() - started);
  return stop;
}
