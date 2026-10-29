<script setup>
import { filterMotion } from '../filterMotion.js';
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { filterSpaceKey, layoutPoint } from "../filterSpace.js";
import { playSphereBurst } from "../sphereBurst.js";
import { yearTransitFrame } from '../yearTransit.js';
import { drawSpherePowder } from '../spherePowder.js';

const props = defineProps({
  id: { type: String, default: "year" },
  modelValue: { type: [String, Number], required: true },
  years: { type: Array, required: true },
});
const space = inject(filterSpaceKey, null);
const transfer = computed(() => yearTransitFrame(space?.state.opened ? space.state.progress : 0,space?.state.transitionLeg));
const powderCanvas = ref(null), powderAvailable = ref(false);
const isOpen = () => space ? opened.value : dialog.value?.open;
const blocked = computed(() => space?.blocked("year") ?? false);
let exitResolve;
const emit = defineEmits(["update:modelValue", "change"]);
const dialog = ref(null), orbit = ref(null), scene = ref(null), triggerText = ref(null);
const exploded = ref(false), spread = ref(0), burstBounds = ref(null);
const rebuilding = ref(false), rebuildReveal = ref(false), lineReturn = ref(null);
let stopBurstCanvas = () => {}, spreadFrame = 0;
const opened = ref(false), dragging = ref(false), position = ref(0);
const years = computed(() => [...new Set([...props.years, Number(props.modelValue)])]
  .map(Number).filter(Number.isInteger).sort((a, b) => a - b));
const wrap = (value, count) => count ? ((value % count) + count) % count : 0;
const index = computed(() => wrap(Math.round(position.value), years.value.length));
const draft = computed(() => years.value[index.value]);
let drag = null, suppressClickUntil = 0, rotationFrame = 0;
const visualPosition = ref(0);
const motion = filterMotion;
const entering = ref(false), introTime = ref(2480), introFlight = ref(null);
const exiting = ref(false), exitTime = ref(0), exitFlight = ref(null);
const stars = ref([]), starMask = ref('none');
const returnDuration = 1200;
const busy = computed(() => entering.value || rebuilding.value || exiting.value || blocked.value);
let exitFrame = 0, pendingExit = null;
const exitProgress = computed(() => progress(exitTime.value, 0, returnDuration));
const exitEase = computed(() => exitProgress.value ** 2 * (3 - 2 * exitProgress.value));
const exitStyle = computed(() => {
  const flight = exitFlight.value;
  if (!flight) return {};
  const t = exitEase.value;
  return {
    width: `${flight.width}px`, height: `${flight.height}px`, fontSize: `${flight.font}px`,
    fontWeight: flight.weight + (flight.targetWeight - flight.weight) * t,
    opacity: flight.opacity + (1 - flight.opacity) * t,
    transform: `translate(${flight.x + (flight.targetX - flight.x) * t}px, ${flight.y + (flight.targetY - flight.y) * t}px) translate(-50%, -50%) scale(${flight.scale + (flight.targetScale - flight.scale) * t}) perspective(800px) rotateY(${360 * t}deg)`,
    textShadow: `0 0 16px rgb(125 180 251 / ${.22 * (1 - t)})`,
  };
});
const exitSurface = computed(() => {
  if (!exitFlight.value) return {};
  const t = exitEase.value;
  const [z, x, y, latitude] = exitFlight.value.angles.map(angle => angle * (1 - t));
  return { transform: `rotateZ(${z}rad) rotateX(${x}rad) rotateY(${y}rad) rotateX(${latitude}rad)` };
});
let introFrame = 0, openCycle = 0;
const progress = (time, start, duration) => Math.max(0, Math.min(1, (time - start) / duration));
const introMesh = computed(() => entering.value ? progress(introTime.value, 2000, 480) : 1);
const introChrome = computed(() => entering.value ? progress(introTime.value, 2000, 300) : 1);
const introCore = computed(() => entering.value ? progress(introTime.value, 1020, 180) : 1);
const introPhase = computed(() => !entering.value ? 'ready' : introTime.value < 650 ? 'flight'
  : introTime.value < 1020 ? 'inward' : introTime.value < 1200 ? 'core'
  : introTime.value < 2000 ? 'outward' : 'mesh');
function updateStarMask() {
  if (!isOpen() || !orbit.value) return;
  const box = orbit.value.getBoundingClientRect();
  starMask.value = `radial-gradient(ellipse ${box.width * .55}px ${box.height * .55}px at ${box.x + box.width / 2}px ${box.y + box.height / 2}px, transparent 66%, #000 100%)`;
}
function createStars() {
  const width = dialog.value.clientWidth, height = dialog.value.clientHeight;
  const count = Math.max(32, Math.min(160, Math.round(width * height / 15000)));
  const columns = Math.max(1, Math.round(Math.sqrt(count * width / height)));
  const rows = Math.ceil(count / columns);
  // One star per jittered cell prevents clusters while avoiding a visible grid.
  stars.value = Array.from({ length: columns * rows }, (_, i) => ({
    left: `${(i % columns + .2 + Math.random() * .6) / columns * 100}%`,
    top: `${(Math.floor(i / columns) + .2 + Math.random() * .6) / rows * 100}%`,
    '--star-size': `${.8 + Math.random() * 1.1}px`,
    '--star-peak': .2 + Math.random() * .42,
    '--star-duration': `${14 + Math.random() * 10}s`,
    '--star-delay': `${Math.random() * 6}s`,
  }));
  updateStarMask();
}
function finishIntro() {
  cancelAnimationFrame(introFrame); introFrame = 0;
  entering.value = false; introTime.value = 2480; introFlight.value = null;
}
function startIntro(source) {
  const box = orbit.value.getBoundingClientRect();
  const label = orbit.value.querySelector('.year-cell.selected');
  introFlight.value = {
    x: source.x - box.x - box.width / 2,
    y: source.y - box.y - box.height / 2,
    scale: source.font / parseFloat(getComputedStyle(label).fontSize),
    originX: source.x, originY: source.y, originFont: source.font,
  };
  let previous = performance.now();
  function tick(now) {
    // A background tab or a long task must not skip entire construction stages.
    const elapsed = document.hidden ? 0 : Math.max(0, Math.min(48, now - previous));
    previous = now;
    introTime.value += elapsed;
    if (introTime.value < 2480) introFrame = requestAnimationFrame(tick);
    else finishIntro();
  }
  introFrame = requestAnimationFrame(tick);
}
function stopRotation() { cancelAnimationFrame(rotationFrame); rotationFrame = 0; }
function settleRotation() { stopRotation(); visualPosition.value = position.value; }
watch(position, target => {
  stopRotation();
  if (!opened.value || dragging.value || motion.matches) return settleRotation();
  const start = visualPosition.value, started = performance.now();
  function animate(now) {
    const t = Math.min(1, (now - started) / 280);
    visualPosition.value = start + (target - start) * (1 - (1 - t) ** 3);
    if (t < 1) rotationFrame = requestAnimationFrame(animate);
    else rotationFrame = 0;
  }
  rotationFrame = requestAnimationFrame(animate);
}, { flush: "sync" });
function animateSpread(target) {
  cancelAnimationFrame(spreadFrame);
  if (motion.matches) { spread.value = target; return; }
  const start = spread.value, started = performance.now();
  function tick(now) {
    const t = Math.min(1, (now - started) / 600);
    spread.value = start + (target - start) * (1 - (1 - t) ** 3);
    if (t < 1) spreadFrame = requestAnimationFrame(tick);
  }
  spreadFrame = requestAnimationFrame(tick);
}
function finishRestore() {
  cancelAnimationFrame(spreadFrame);
  exploded.value = false; rebuilding.value = false; rebuildReveal.value = false;
  spread.value = 0; lineReturn.value = null;
}
function returnLines() {
  cancelAnimationFrame(spreadFrame);
  const start = spread.value, order = [...years.value], started = performance.now();
  const interval = Math.min(130, 1450 / Math.max(1, order.length - 1));
  function tick(now) {
    let active = false;
    lineReturn.value = Object.fromEntries(order.map((year, i) => {
      const t = Math.max(0, Math.min(1, (now - started - i * interval) / 650));
      if (t < 1) active = true;
      return [year, start * (1 - t) ** 3];
    }));
    if (active) spreadFrame = requestAnimationFrame(tick);
  }
  tick(started);
}
function resetBurst() {
  stopBurstCanvas(); cancelAnimationFrame(spreadFrame);
  finishRestore();
}
function burstMotionChanged() {
  if (exiting.value) { finishExit(); return; }
  if (motion.matches) finishIntro();
  settleRotation(); stopBurstCanvas(); cancelAnimationFrame(spreadFrame);
  if (rebuilding.value) finishRestore();
  else spread.value = exploded.value ? 1 : 0;
}
function toggleBurst() {
  if (busy.value || performance.now() < suppressClickUntil) return;
  scene.value.getAnimations().forEach(animation => animation.finish());
  if (exploded.value) {
    const from = stopBurstCanvas.elapsed?.() ?? 3900;
    stopBurstCanvas();
    if (motion.matches) { finishRestore(); return; }
    settleRotation(); rebuilding.value = true; rebuildReveal.value = false;
    returnLines();
    try {
      stopBurstCanvas = playSphereBurst(scene.value, orbit.value, sphereMesh.value, surfaceRadius, {
        reverse: true, from,
        onReveal: () => { rebuildReveal.value = true; },
        onComplete: finishRestore,
      });
    } catch { finishRestore(); }
    return;
  }
  const stage = orbit.value.parentElement, size = orbit.value.clientWidth;
  const header = scene.value.querySelector('.year-header');
  const footer = scene.value.querySelector('.year-footer');
  burstBounds.value = { cx: stage.offsetLeft + size / 2, cy: stage.offsetTop + size / 2,
    radius: size * surfaceRadius, left: 48, right: scene.value.clientWidth - 48,
    top: header.offsetTop + header.offsetHeight + 20, bottom: footer.offsetTop - 24 };
  try {
    if (!motion.matches) stopBurstCanvas = playSphereBurst(scene.value, orbit.value, sphereMesh.value, surfaceRadius);
  } catch {
    // Selection and the simplified exploded state remain usable without canvas.
    stopBurstCanvas();
  }
  exploded.value = true; animateSpread(1);
}
function orbitClicked(event) {
  if (event.target.closest('.year-cell')) return;
  toggleBurst();
}
motion.addEventListener("change", burstMotionChanged);
function resized() {
  if (exiting.value) finishExit();
  else {
    resetBurst();
    if (isOpen()) nextTick(() => {
      if (!isOpen() || !orbit.value) return;
      if (entering.value && introFlight.value) {
        const box = orbit.value.getBoundingClientRect(), flight = introFlight.value;
        const label = orbit.value.querySelector('.year-cell.selected');
        introFlight.value = { ...flight,
          x: flight.originX - box.x - box.width / 2,
          y: flight.originY - box.y - box.height / 2,
          scale: flight.originFont / parseFloat(getComputedStyle(label).fontSize),
        };
      }
      updateStarMask();
    });
  }
}
window.addEventListener("resize", resized);

async function open() {
  if (space) return space.enter("year");
  return begin(true);
}
async function begin(initial) {
  if (isOpen() || !years.value.length) return;
  const cycle = ++openCycle;
  // Measure only the digits, so the flying year starts at the text rather than the field centre.
  const range = document.createRange();
  const text = triggerText.value.firstChild;
  range.setStart(text, 0); range.setEnd(text, String(props.modelValue).length);
  const rect = range.getBoundingClientRect();
  const source = { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2,
    font: parseFloat(getComputedStyle(triggerText.value).fontSize) };
  finishIntro(); resetBurst();
  position.value = Math.max(0, years.value.indexOf(Number(props.modelValue)));
  settleRotation();
  opened.value = true;
  entering.value = initial && !motion.matches;
  introTime.value = entering.value ? 0 : 2480;
  if (!space) dialog.value.showModal();
  await nextTick();
  if (cycle !== openCycle || !isOpen()) return;
  if (!space) createStars();
  if (entering.value) startIntro(source);
  if (initial) orbit.value?.focus({ preventScroll: true });
}
function cancelDrag() {
  const current = drag;
  drag = null;
  dragging.value = false;
  position.value = Math.round(position.value);
  if (current && orbit.value?.hasPointerCapture(current.id)) orbit.value.releasePointerCapture(current.id);
}
function closed() {
  powderAvailable.value = false;
  try { powderCanvas.value?.getContext('2d')?.clearRect(0,0,powderCanvas.value.width,powderCanvas.value.height); } catch {}
  ++openCycle;
  cancelAnimationFrame(exitFrame); exitFrame = 0;
  exiting.value = false; exitFlight.value = null; pendingExit = null;
  stars.value = [];
  finishIntro(); resetBurst();
  cancelDrag();
  opened.value = false;
  settleRotation();
}
function finishExit() {
  const result = pendingExit;
  pendingExit = null;
  cancelAnimationFrame(exitFrame); exitFrame = 0;
  exiting.value = false; exitFlight.value = null;
  finishIntro(); resetBurst();
  if (space) { const resolve = exitResolve; exitResolve = null; resolve?.(); return; }
  dialog.value.close();
  if (result?.apply && String(result.year) !== String(props.modelValue)) {
    emit("update:modelValue", String(result.year));
    emit("change", String(result.year));
  }
}
function requestExit(apply, coordinated = false) {
  if (space && !coordinated) return space.close(apply);
  if (exiting.value || !isOpen()) return;
  const year = apply ? draft.value : Number(props.modelValue);
  if (!years.value.includes(year)) return;
  pendingExit = { year, apply };
  const node = orbit.value.querySelector(`[id="${props.id}-option-${year}"]`);
  const point = yearPoints.value.find(point => point.year === year);
  const range = document.createRange(), text = triggerText.value.firstChild;
  range.setStart(text, 0); range.setEnd(text, String(props.modelValue).length);
  const target = range.getBoundingClientRect();
  if (motion.matches || !node || !target.width || !target.height) { finishExit(); return; }
  const box = node.getBoundingClientRect(), style = getComputedStyle(node);
  const targetStyle = getComputedStyle(triggerText.value);
  exitFlight.value = {
    year, x: box.x + box.width / 2, y: box.y + box.height / 2,
    width: node.offsetWidth, height: node.offsetHeight, font: parseFloat(style.fontSize),
    scale: box.width / node.offsetWidth, opacity: Number(style.opacity),
    weight: parseFloat(style.fontWeight), targetWeight: parseFloat(targetStyle.fontWeight),
    targetX: target.x + target.width / 2, targetY: target.y + target.height / 2,
    targetScale: parseFloat(targetStyle.fontSize) / parseFloat(style.fontSize),
    // Full turns are visually equivalent: retain only the current orientation.
    angles: point.surfaceAngles.map(angle => Math.atan2(Math.sin(angle), Math.cos(angle))),
    backdropOpacity: space ? 1 : Number(getComputedStyle(dialog.value, '::backdrop').opacity),
    starOpacity: space ? 1 : Number(getComputedStyle(dialog.value.querySelector('.year-stars')).opacity),
  };
  // Freeze the exact visible year before stopping any opening, rotation or burst animation.
  cancelAnimationFrame(introFrame); introFrame = 0;
  cancelAnimationFrame(spreadFrame); stopRotation(); stopBurstCanvas();
  cancelDrag(); stopRotation();
  exiting.value = true; exitTime.value = 0;
  const started = performance.now();
  function tick(now) {
    exitTime.value = now - started;
    if (exitTime.value < returnDuration) exitFrame = requestAnimationFrame(tick);
    else finishExit();
  }
  exitFrame = requestAnimationFrame(tick);
}
function accept() { requestExit(true); }
function dismiss() { requestExit(false); }
function selectYear(year) {
  if (busy.value) return;
  const selected = years.value.indexOf(year);
  if (selected < 0) return;
  let distance = wrap(selected - index.value, years.value.length);
  if (distance > years.value.length / 2) distance -= years.value.length;
  position.value = Math.round(position.value) + distance;
  orbit.value?.focus({ preventScroll: true });
}
function step(amount) { if (busy.value) return; position.value = Math.round(position.value) + amount; }
function keydown(event) {
  if (blocked.value) return;
  if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.altKey || event.metaKey) return;
  if (event.target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) return;
  const key = /^[ad]$/i.test(event.key) ? event.key.toLowerCase() : event.key;
  const actions = { ArrowLeft: -1, ArrowRight: 1, a: -1, d: 1 };
  if (busy.value && (Object.hasOwn(actions, key) || key === "Home" || key === "End")) {
    event.preventDefault(); return;
  }
  if (Object.hasOwn(actions, key)) { event.preventDefault(); step(actions[key]); }
  else if (event.key === "Home") { event.preventDefault(); selectYear(years.value[0]); }
  else if (event.key === "End") { event.preventDefault(); selectYear(years.value.at(-1)); }
  else if ((event.key === "Enter" || event.key === " ") && orbit.value?.contains(event.target)) { event.preventDefault(); accept(); }
}
function pointerDown(event) {
  if (busy.value || !event.isPrimary || event.button !== 0) return;
  drag = { id: event.pointerId, x: event.clientX, position: position.value,
    step: Math.max(54, orbit.value.clientWidth * .19) };
}
function pointerMove(event) {
  if (!drag || drag.id !== event.pointerId) return;
  const distance = event.clientX - drag.x;
  if (!dragging.value && Math.abs(distance) < 6) return;
  if (!dragging.value) {
    dragging.value = true;
    orbit.value.setPointerCapture(event.pointerId);
    orbit.value.focus({ preventScroll: true });
  }
  position.value = drag.position - distance / drag.step;
}
function pointerUp(event) {
  if (!drag || drag.id !== event.pointerId) return;
  if (dragging.value) suppressClickUntil = performance.now() + 250;
  cancelDrag();
}
function lostCapture(event) {
  // Touch buttons have implicit capture; handing it to the orbit is not a cancellation.
  if (event.target === orbit.value) cancelDrag();
}
function clickCapture(event) {
  if (event.detail && performance.now() < suppressClickUntil) {
    event.preventDefault(); event.stopPropagation();
  }
}
// The mesh, attached labels and spokes share one rigid rotation and projection.
const surfaceRadius = .46;
const tiltX = -.24, tiltZ = -.14;
const latitudes = [-.7, .2, .75, -.35, -.9, .4, -.1, .95, -.55, .05, .55];
const sphereRotation = computed(() => -visualPosition.value * Math.PI * 2 / Math.max(1, years.value.length));
function project(latitude, longitude) {
  const x = Math.cos(latitude) * Math.sin(longitude);
  const y = -Math.sin(latitude);
  const z = Math.cos(latitude) * Math.cos(longitude);
  const tiltedY = y * Math.cos(tiltX) - z * Math.sin(tiltX);
  const depth = y * Math.sin(tiltX) + z * Math.cos(tiltX);
  return {
    x: x * Math.cos(tiltZ) - tiltedY * Math.sin(tiltZ),
    y: x * Math.sin(tiltZ) + tiltedY * Math.cos(tiltZ),
    depth,
  };
}
function svgPoint(point) {
  return { x: 200 + 400 * surfaceRadius * point.x, y: 200 + 400 * surfaceRadius * point.y };
}
const yearPoints = computed(() => years.value.map((year, i) => {
  const longitude = i * Math.PI * 2 / Math.max(1, years.value.length) + sphereRotation.value;
  const latitude = latitudes[i % latitudes.length];
  const point = project(latitude, longitude);
  const front = (point.depth + 1) / 2;
  let extension = 1;
  const bounds = burstBounds.value;
  const amount = lineReturn.value?.[year] ?? spread.value;
  if (bounds && amount > 0) {
    const dx = point.x * bounds.radius, dy = point.y * bounds.radius;
    const maxX = Math.abs(dx) < .01 ? Infinity : (dx > 0 ? bounds.right - bounds.cx : bounds.left - bounds.cx) / dx;
    const maxY = Math.abs(dy) < .01 ? Infinity : (dy > 0 ? bounds.bottom - bounds.cy : bounds.top - bounds.cy) / dy;
    const desired = 1.22 + ((year * .61803398875) % 1) * .55;
    extension += amount * (Math.max(.6, Math.min(desired, maxX, maxY)) - 1);
  }
  const anchor = { x: point.x * extension * transfer.value.radius, y: point.y * extension * transfer.value.radius };
  const selected = i === index.value, target = svgPoint(anchor);
  const order = wrap(i - index.value - 1, years.value.length);
  const rayStart = 1200 + order * 240 / Math.max(1, years.value.length - 2);
  const ray = entering.value ? progress(introTime.value, selected ? 650 : rayStart, selected ? 370 : 400) : 1;
  const labelReveal = !entering.value || selected ? 1 : progress(introTime.value, rayStart + 400, 160);
  const fly = entering.value ? 1 - (1 - progress(introTime.value, 0, 650)) ** 3 : 1;
  const flight = introFlight.value;
  const scale = (.72 + front * .28) * (.35 + transfer.value.radius*.65);
  const transform = entering.value && selected && flight
    ? `translate(-50%, -50%) translate(calc(${flight.x * (1 - fly)}px + var(--sphere-radius) * ${anchor.x * fly}), calc(${flight.y * (1 - fly)}px + var(--sphere-radius) * ${anchor.y * fly})) scale(${flight.scale * (1 - fly) + scale * fly})`
    : `translate(-50%, -50%) translate(calc(var(--sphere-radius) * ${anchor.x}), calc(var(--sphere-radius) * ${anchor.y})) scale(${scale})`;
  const turn = entering.value && selected ? fly : 1;
  return {
    year, selected, back: point.depth < 0,
    ...target,
    lineX1: entering.value && selected ? target.x : 200,
    lineY1: entering.value && selected ? target.y : 200,
    lineX2: entering.value && selected ? target.x + (200 - target.x) * ray : 200 + (target.x - 200) * ray,
    lineY2: entering.value && selected ? target.y + (200 - target.y) * ray : 200 + (target.y - 200) * ray,
    lineOpacity: (selected ? .52 : .07 + front * .18) * (ray > 0 && transfer.value.radius>0 ? 1 : 0),
    endpointOpacity: !entering.value ? 1 : selected ? (introTime.value >= 650 ? 1 : 0) : labelReveal,
    style: {
      transform,
      opacity: entering.value && !flight ? 0 : (selected ? 1 : .24 + front * .66) * labelReveal * transfer.value.labelOpacity,
      zIndex: 2 + Math.round(front * 10),
    },
    surfaceStyle: { transform: `rotateZ(${tiltZ * turn}rad) rotateX(${tiltX * turn}rad) rotateY(${longitude * turn}rad) rotateX(${latitude * turn}rad)` },
    surfaceAngles: [tiltZ * turn, tiltX * turn, longitude * turn, latitude * turn],
  };
}));
function curvePaths(sample, key) {
  const paths = [];
  let run = [], previous, back;
  function append() {
    if (run.length < 2) return;
    paths.push({ key: `${key}-${paths.length}`, back, axis: key === "meridian-0",
      d: run.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(3)},${p.y.toFixed(3)}`).join(' ') });
  }
  for (let i = 0; i <= 72; i++) {
    const point = sample(i * Math.PI * 2 / 72);
    const projected = svgPoint(point), nextBack = point.depth < 0;
    if (run.length && nextBack !== back) {
      run.push(projected); append(); run = [previous];
    }
    back = nextBack; run.push(projected); previous = projected;
  }
  append();
  return paths;
}
const sphereMesh = computed(() => {
  const paths = [];
  // Great circles turn with the sphere; latitude rings use the same axis.
  for (let i = 0; i < 6; i++) paths.push(...curvePaths(
    angle => project(angle, i * Math.PI / 6 + sphereRotation.value), `meridian-${i}`));
  for (let i = -2; i <= 2; i++) paths.push(...curvePaths(
    angle => project(i * Math.PI / 6, angle + sphereRotation.value), `latitude-${i}`));
  return paths;
});
function paintPowder() {
  try {
    powderAvailable.value=drawSpherePowder(powderCanvas.value,{paths:sphereMesh.value,
      amount:transfer.value.powder,returning:transfer.value.returning,
      size:orbit.value?.clientWidth || 400,ratio:window.devicePixelRatio || 1,reduced:motion.matches});
  } catch { powderAvailable.value=false; }
}
watch(years, (available, previous) => {
  if (!opened.value) return;
  if (available.length === previous.length && available.every((year, i) => year === previous[i])) return;
  if (exiting.value) return;
  const selected = previous[wrap(Math.round(position.value), previous.length)];
  cancelDrag();
  const next = available.indexOf(selected);
  position.value = next >= 0 ? next : wrap(position.value, available.length);
  settleRotation();
});
const unregister = space?.register('year', {
  begin,
  value: () => String(draft.value),
  busy: () => entering.value || rebuilding.value || exiting.value,
  freeze: () => { cancelDrag(); finishIntro(); resetBurst(); stopRotation(); },
  core: () => layoutPoint(orbit.value),
  exit: apply => !isOpen() ? Promise.resolve() : new Promise(resolve => { exitResolve = resolve; requestExit(apply, true); }),
  reset: closed,
  focus: () => orbit.value?.focus({ preventScroll: true }),
  key: keydown,
  paint: paintPowder,
});
watch(draft, value => { if (space && opened.value && !exiting.value) space.state.year = String(value); });
watch(blocked, value => { if (value) { cancelDrag(); stopRotation(); } });
onBeforeUnmount(() => {
  unregister?.(); exitResolve?.();
  ++openCycle;
  cancelAnimationFrame(exitFrame); pendingExit = null;
  cancelDrag();
  stopRotation();
  finishIntro(); resetBurst();
  motion.removeEventListener("change", burstMotionChanged);
  window.removeEventListener("resize", resized);
  if (!space && isOpen()) dialog.value.close();
});
</script>

<template>
  <button :id="id" class="year-trigger" type="button" aria-haspopup="dialog"
    :aria-expanded="opened" :aria-controls="space ? 'filter-space-dialog' : `${id}-dialog`" :aria-label="`发售年份：${modelValue} 年`"
    :data-year="modelValue" @click="open">
    <span ref="triggerText" :class="{ 'is-travelling': entering || exiting }">{{ modelValue }} 年</span>
    <svg aria-hidden="true" viewBox="0 0 20 20"><path d="m6 8 4 4 4-4" /></svg>
  </button>
  <input type="hidden" name="year" :value="modelValue" />
  <Teleport :to="space ? '#filter-space-year' : 'body'" defer>
    <component :is="space ? 'div' : 'dialog'" ref="dialog" :id="`${id}-dialog`" class="year-dialog" :class="{ 'is-returning': exiting, 'in-filter-space': !!space }"
      :style="{ '--return-fade': (exitFlight?.backdropOpacity ?? 1) * (1 - exitEase) }"
      :aria-labelledby="`${id}-title`" @close="closed" @cancel.prevent="dismiss" @keydown="keydown">
      <div v-if="opened && !space" class="year-stars" :class="{ 'is-fading-out': exiting }" aria-hidden="true"
        :style="{ maskImage: starMask, WebkitMaskImage: starMask, opacity: exiting ? (exitFlight?.starOpacity ?? 1) * (1 - exitEase) : 1 }">
        <span v-for="(style, i) in stars" :key="i" class="year-star" :style="style"></span>
      </div>
      <div ref="scene" class="year-scene" :class="{ 'is-entering': entering }" :data-intro-phase="introPhase"
        :style="{ '--surface-radius': surfaceRadius, opacity: exiting ? 1 - progress(exitTime, 0, 480) : 1 }">
        <button class="year-close" type="button" aria-label="关闭年份选择" :disabled="exiting" @click="dismiss">×</button>
        <header class="year-header" :style="{ opacity: introChrome }">
          <h2 :id="`${id}-title`">发售年份</h2>
          <output class="year-current" aria-live="polite" aria-atomic="true">{{ draft }}</output>
        </header>
        <div class="year-stage">
          <div ref="orbit" class="year-orbit" :class="{ dragging, 'is-exploded': exploded && !rebuildReveal, 'is-rebuilding': rebuilding }" :aria-busy="busy" role="listbox" tabindex="0"
            aria-label="发售年份" :aria-activedescendant="`${id}-option-${draft}`"
            :aria-describedby="`${id}-instructions`"
            @pointerdown="pointerDown" @pointermove="pointerMove" @pointerup="pointerUp"
            @pointercancel="cancelDrag" @lostpointercapture="lostCapture" @click.capture="clickCapture" @click="orbitClicked">
            <span :id="`${id}-instructions`" class="sr-only">左右拖动球体，或使用左右方向键、A/D 预览年份。W和上方向键切到上一个筛选页，S和下方向键切到下一个筛选页。点击年份选中，确认按钮或球体聚焦时回车提交，Escape 取消。点击球体空白处可爆裂或复原。</span>
            <svg class="sphere-grid" :style="{ opacity: introMesh * transfer.meshVisible, visibility: powderAvailable ? 'hidden' : undefined }" viewBox="0 0 400 400" aria-hidden="true">
              <path v-for="curve in sphereMesh" :key="curve.key" :d="curve.d"
                class="sphere-curve" :class="{ 'is-back': curve.back, 'is-axis': curve.axis }" />
            </svg>
            <canvas ref="powderCanvas" class="sphere-powder" :style="{ visibility: powderAvailable ? 'visible' : 'hidden' }" :data-amount="transfer.powder.toFixed(4)" aria-hidden="true"></canvas>
            <svg class="sphere-spokes" viewBox="0 0 400 400" aria-hidden="true">
              <g v-for="point in yearPoints" :key="point.year" :data-spoke-year="point.year"
                :class="{ selected: point.selected }" :opacity="point.lineOpacity">
                <line :x1="point.lineX1" :y1="point.lineY1" :x2="point.lineX2" :y2="point.lineY2" />
                <circle :cx="point.x" :cy="point.y" :r="point.selected ? 1.9 : 1.1" :opacity="point.endpointOpacity" />
              </g>
              <circle class="sphere-center" cx="200" cy="200" :r="2 * introCore" :style="{ opacity: .65 * introCore }" />
            </svg>
            <button v-for="point in yearPoints" :id="`${id}-option-${point.year}`" :key="point.year"
              class="year-cell" :class="{ selected: point.selected, 'is-return-source': exiting && point.year === exitFlight?.year }" :style="point.style"
              role="option" :aria-selected="point.selected" :aria-label="`${point.year} 年`" tabindex="-1"
              type="button" :disabled="busy" @click="selectYear(point.year)">
              <span class="year-surface" :style="point.surfaceStyle">
                <span class="year-text" :class="{ 'back-face': point.back }">{{ point.year }}</span>
              </span>
            </button>
          </div>
          <button v-if="exploded" class="sphere-restore" type="button" aria-label="还原球体"
            title="还原球体" :disabled="rebuilding" @click.stop="toggleBurst"><span aria-hidden="true"></span></button>
        </div>
        <footer class="year-footer">
          <button class="year-cancel" type="button" :disabled="exiting" @click="dismiss">取消</button>
          <button class="primary year-confirm" type="button" :disabled="exiting" @click="accept()">确认</button>
        </footer>
      </div>
      <div v-if="exiting && exitFlight" class="year-return" :style="exitStyle" aria-hidden="true" :data-year="exitFlight.year">
        <span class="year-return-surface" :style="exitSurface">{{ exitFlight.year }}</span>
      </div>
    </component>
  </Teleport>
</template>

<style scoped>
.year-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 44px;
  padding: 10px 12px;
  border-color: #47515f;
  background: #14181e;
  color: #edf0f5;
  font-size: 1rem;
  -webkit-user-select: none;
  user-select: none;
}
.year-trigger svg { width: 18px; height: 18px; fill: none; stroke: #a8b9d0; stroke-width: 1.5; }
.year-trigger .is-travelling { visibility: hidden; }
.year-dialog {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  height: 100dvh;
  max-width: none;
  max-height: none;
  margin: 0;
  padding: 0;
  overflow: auto;
  overscroll-behavior: contain;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: #edf0f5;
  -webkit-user-select: none;
  user-select: none;
}
.year-dialog::backdrop {
  background: #000;
  overflow: hidden;
  overscroll-behavior: contain;
}
.year-stars {
  position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none;
  animation: year-stars-enter 2400ms ease-out both;
}
.year-stars.is-fading-out { animation: none; }
.year-star {
  position: absolute; width: var(--star-size); height: var(--star-size);
  border-radius: 50%; background: #d0dbea; opacity: 0;
  box-shadow: 0 0 4px rgb(180 204 235 / 24%);
  animation: year-star-life var(--star-duration) ease-in-out var(--star-delay) infinite both;
}
.year-scene {
  --sphere-gutter: 64px;
  --sphere-size: min(calc(100dvh - 200px), 820px, calc(100vw - var(--sphere-gutter)));
  --sphere-radius: calc(var(--sphere-size) * var(--surface-radius));
  position: relative;
  z-index: 1;
  height: 100%;
  min-height: 100%;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  grid-template-columns: minmax(0, 1fr);
  place-items: center;
  padding: 148px 32px 88px;
  transform-origin: 50% 50%;
}
.year-dialog[open]::backdrop { animation: year-backdrop 650ms ease-in-out both; }
.year-dialog.is-returning::backdrop { animation: none; opacity: var(--return-fade); }
.year-return {
  position: fixed; top: 0; left: 0; z-index: 50;
  pointer-events: none; color: #edf0f5;
  font-variant-numeric: tabular-nums; line-height: normal;
  transform-origin: center;
}
.year-return-surface {
  position: absolute; inset: 0; display: grid; place-items: center;
  transform-origin: center; transform-style: preserve-3d;
}
.year-cell.is-return-source { visibility: hidden; }
.year-header {
  z-index: 20;
  position: absolute; top: 28px; left: 50%; transform: translateX(-50%);
  text-align: center;
}
.year-header h2 { margin-bottom: 8px; font-size: 1.25rem; font-weight: 400; letter-spacing: .12em; color: #b0c2d9; }
.year-current {
  display: block;
  font-size: clamp(2.75rem, 4.5vw, 3.5rem);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  letter-spacing: .06em;
  line-height: 1.12;
  color: #d8e9ff;
  text-shadow: 0 0 35px rgb(121 172 238 / 14%);
}
.year-close {
  position: absolute; top: 24px; right: 32px; z-index: 20;
  min-height: 44px; width: 44px; padding: 0;
  font-size: 1.8rem; border: 0; border-radius: 50%;
  background: transparent; color: #a8b9d0;
}
.year-close:hover:not(:disabled) { background: rgb(127 164 209 / 10%); }
.year-stage { position: relative; z-index: 2; width: var(--sphere-size); height: var(--sphere-size); flex-shrink: 0; }
.year-orbit {
  position: relative;
  width: 100%; height: 100%;
  border-radius: 50%;
  overflow: visible;
  touch-action: pan-y;
  cursor: grab;
  outline: none;
  background: transparent;
}
.year-orbit:focus-visible .year-cell.selected .year-text::after {
  height: 3px;
  background: #d6e7ff;
}
.year-orbit.dragging { cursor: grabbing; }
.is-entering .year-orbit { cursor: default; }
.is-entering .year-cell.selected .year-text::after { opacity: 0; }
.is-entering .year-cell { transition: none; }
.sphere-grid {
  position: absolute; inset: 0; width: 100%; height: 100%;
  fill: none; stroke: #99bae3; stroke-width: .65;
  pointer-events: none;
}
.sphere-curve { opacity: .2; }
.sphere-curve.is-back { opacity: .055; }
.sphere-curve.is-axis { opacity: .36; stroke: #aecdf4; }
.sphere-curve.is-axis.is-back { opacity: .1; }
.sphere-spokes {
  overflow: visible;
  position: absolute; inset: 0; width: 100%; height: 100%;
  pointer-events: none; stroke: #9dbfe9; fill: #9dbfe9;
}
.sphere-powder { position:absolute;inset:0;width:100%;height:100%;pointer-events:none; }
.sphere-spokes line { stroke-width: .8; vector-effect: non-scaling-stroke; }
.sphere-spokes .selected line { stroke-width: 1; }
.sphere-center { stroke: none; fill: #b2d3ff; opacity: .65; }
.year-cell {
  position: absolute; top: 50%; left: 50%;
  width: 88px; height: 44px; padding: 0;
  border: 0; border-radius: 8px;
  background: transparent; color: #bac8db;
  font-size: clamp(1rem, 2.4vw, 1.6rem);
  font-weight: 400; font-variant-numeric: tabular-nums;
  transition: color 200ms ease;
}
.year-cell:hover:not(:disabled) { background: transparent; color: #f0f6ff; }
.year-cell.selected { color: #d5e7ff; font-weight: 600; text-shadow: 0 0 16px rgb(125 180 251 / 22%); }
.year-cell.selected .year-text::after {
  content: ""; position: absolute; bottom: 3px; left: calc(50% - 9px);
  width: 18px; height: 2px; border-radius: 2px;
  background: #91bcf3; box-shadow: 0 0 9px rgb(126 181 251 / 30%);
}
.year-surface, .year-text {
  position: absolute; inset: 0; display: grid; place-items: center;
  transform-origin: center; pointer-events: none;
}
.year-surface { transform-style: preserve-3d; }
.year-text { backface-visibility: visible; }
.dragging .year-cell { transition: none; cursor: grabbing; }
.year-orbit.is-exploded .sphere-grid { visibility: hidden; }
.sphere-restore {
  position: absolute; z-index: 15; left: 50%; top: 50%;
  transform: translate(-50%, -50%); width: 44px; height: 44px;
  min-height: 44px; padding: 0; border: 0; border-radius: 50%; background: transparent;
  display: grid; place-items: center;
}
.sphere-restore span { width: 7px; height: 7px; border-radius: 50%; background: #b5d4fc; box-shadow: 0 0 16px rgb(139 187 249 / 45%); }
.sphere-restore:hover:not(:disabled) { background: rgb(127 164 209 / 9%); }
.year-footer {
  z-index: 20;
  position: absolute; right: 32px; bottom: 24px;
  display: flex; align-items: center; justify-content: flex-end; gap: 20px;
}
.year-cancel { background: transparent; border-color: transparent; color: #a8b9d0; min-width: 96px; }
.year-confirm { min-width: 112px; }
@keyframes year-backdrop { from { opacity: 0; } to { opacity: 1; } }
@keyframes year-stars-enter { from { opacity: 0; } to { opacity: 1; } }
@keyframes year-star-life {
  0%, 100% { opacity: 0; }
  18%, 42% { opacity: var(--star-peak); }
  76% { opacity: 0; }
}
@media (max-width: 480px) {
  .year-scene { --sphere-gutter: 48px; padding-inline: 12px; }
  .year-close { top: 12px; right: 12px; }
  .year-footer { right: 16px; bottom: 20px; gap: 12px; }
  .year-cell { width: 72px; font-size: 1.1rem; }
}
@media (max-height: 520px) {
  .year-scene { --sphere-size: min(calc(100dvh - 144px), 820px, calc(100vw - var(--sphere-gutter))); padding-block: 88px 64px; }
  .year-header { top: 12px; }
  .year-current { font-size: 2rem; }
  .year-header h2 { font-size: 1rem; margin-bottom: 4px; }
  .year-footer { right: 16px; bottom: 12px; }
  .year-cell { font-size: 1rem; width: 64px; }
}
@media (prefers-reduced-motion: reduce) {
  .year-dialog[open] .year-scene, .year-dialog[open]::backdrop { animation: none; }
  .year-stars { animation: none; }
  .year-star { animation: none; opacity: calc(var(--star-peak) * .35); }
  .year-cell { transition: none; }
}
</style>
