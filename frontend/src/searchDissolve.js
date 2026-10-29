// Decorative snapshot only: the actual input and router clear immediately.
export function dissolveSearchText(input) {
  const noop = () => {};
  if (!input?.value || window.matchMedia("(prefers-reduced-motion: reduce)").matches)
    return noop;
  const host = input.parentElement;
  const style = getComputedStyle(input);
  const width = input.clientWidth, height = input.clientHeight;
  const left = parseFloat(style.paddingLeft) || 0;
  const right = width - (parseFloat(style.paddingRight) || 0);
  if (right <= left || !width || !height) return noop;
  const scale = Math.min(window.devicePixelRatio || 1, 2);
  const lift = 46;
  const source = document.createElement("canvas");
  source.width = Math.ceil(width * scale);
  source.height = Math.ceil(height * scale);
  const ink = source.getContext("2d");
  const canvas = document.createElement("canvas");
  canvas.width = source.width;
  canvas.height = Math.ceil((height + lift) * scale);
  const ctx = canvas.getContext("2d");
  if (!ink || !ctx) return noop;
  ink.scale(scale, scale);
  ink.font = style.font || `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  ink.fillStyle = style.color;
  const metrics = ink.measureText(input.value);
  const baseline = height / 2 + (metrics.actualBoundingBoxAscent - metrics.actualBoundingBoxDescent) / 2;
  const offset = left - input.scrollLeft;
  ink.save();
  ink.beginPath(); ink.rect(left, 0, right - left, height); ink.clip();
  ink.fillText(input.value, offset, baseline);
  ink.restore();
  const letters = typeof Intl.Segmenter === "function"
    ? Array.from(new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(input.value), part => part.segment)
    : Array.from(input.value);
  let prefix = "";
  const visible = [];
  for (const letter of letters) {
    const start = offset + ink.measureText(prefix).width;
    prefix += letter;
    const end = offset + ink.measureText(prefix).width;
    if (end > left && start < right) visible.push({ start: Math.max(left, start), end: Math.min(right, end) });
  }
  const pixels = ink.getImageData(0, 0, source.width, source.height).data;
  const tiles = [];
  const cell = 3;
  visible.forEach((letter, index) => {
    const delay = (visible.length - 1 - index) * Math.min(38, 300 / Math.max(1, visible.length - 1));
    for (let y = 0; y < height; y += cell) {
      for (let x = letter.start; x < letter.end; x += cell) {
        const w = Math.min(cell, letter.end - x), h = Math.min(cell, height - y);
        let painted = false;
        for (let py = Math.floor(y * scale); py < Math.min(source.height, Math.ceil((y + h) * scale)) && !painted; py++) {
          for (let px = Math.floor(x * scale); px < Math.min(source.width, Math.ceil((x + w) * scale)); px++) {
            if (pixels[(py * source.width + px) * 4 + 3]) { painted = true; break; }
          }
        }
        if (painted) tiles.push({ x, y, w, h, delay, dx: 12 + Math.random() * 24, dy: 14 + Math.random() * 23, turn: (Math.random() - .5) * 1.2 });
      }
    }
  });
  if (!tiles.length) return noop;
  canvas.className = "search-dissolve";
  canvas.setAttribute("aria-hidden", "true");
  Object.assign(canvas.style, { position: "absolute", pointerEvents: "none", left: "0", bottom: "0", width: `${width}px`, height: `${height + lift}px`, zIndex: "3" });
  let frame = 0, stopped = false;
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  function stop() {
    if (stopped) return;
    stopped = true;
    cancelAnimationFrame(frame);
    canvas.remove();
    host.classList.remove("is-dissolving");
    window.removeEventListener("resize", stop);
    document.removeEventListener("visibilitychange", visibilityChanged);
    motion.removeEventListener("change", stop);
  }
  function visibilityChanged() { if (document.hidden) stop(); }
  function draw(now) {
    if (stopped) return;
    const elapsed = now - started;
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    ctx.clearRect(0, 0, width, height + lift);
    for (const tile of tiles) {
      const t = Math.max(0, Math.min(1, (elapsed - tile.delay) / 430));
      if (t >= 1) continue;
      const drift = t * t;
      ctx.save();
      ctx.globalAlpha = 1 - t;
      ctx.translate(tile.x + tile.w / 2 + tile.dx * drift, lift + tile.y + tile.h / 2 - tile.dy * t);
      ctx.rotate(tile.turn * t);
      ctx.scale(1 - .65 * t, 1 - .65 * t);
      ctx.drawImage(source, tile.x * scale, tile.y * scale, tile.w * scale, tile.h * scale, -tile.w / 2, -tile.h / 2, tile.w, tile.h);
      ctx.restore();
    }
    if (elapsed < 740) frame = requestAnimationFrame(draw);
    else stop();
  }
  host.append(canvas);
  host.classList.add("is-dissolving");
  window.addEventListener("resize", stop);
  document.addEventListener("visibilitychange", visibilityChanged);
  motion.addEventListener("change", stop);
  const started = performance.now();
  draw(started);
  return stop;
}
