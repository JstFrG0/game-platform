<script setup>
import { computed, inject, nextTick, onBeforeUnmount, ref, shallowRef, useId, watch } from 'vue';
import { drawPlatformStardust, platformDustStrength } from '../platformStardust.js';
import { CORE_CONTACT, descentFrame, landingParticles, smooth } from '../filterDescent.js';
import { clampProgress, filterSpaceKey, wheelStep, sceneKinds, sceneIndex, sceneAt, atEndpoint } from '../filterSpace.js';
import { transitLeg, yearTransitFrame } from '../yearTransit.js';
import { createParallaxSky } from '../platformParallax.js';
import { genreTransitFrame, filterCoreTrail } from '../genreTransit.js';
import { modeTransitFrame } from '../modeTransit.js';
import { platformGenreTail } from '../platformGenreTransit.js';
import { BASE_OUTLINE_PATH,BASE_APERTURE_PATH,platformCoreOcclusion,readPlatformTagLayout } from '../platformOcclusion.js';

const space = inject(filterSpaceKey), state = space.state;
const stardust = ref(null);
let dustTime = 0, dustUnavailable = false;
const dialog = ref(null), ready = ref(false), sceneBusy = ref(false), closingTime = ref(0);
const anchors = ref({ year: { x: 0, y: 0 }, platform: { x: 0, y: 0 }, genre: { x: 0, y: 0 }, mode: { x: 0, y: 0 } });
const viewport = ref({ width: window.innerWidth, height: window.innerHeight });
const trail = ref(0), direction = ref(1);
const baseScale = ref(1);
const platformMounted=ref(false);
const platformOptions=computed(()=>({mounted:platformMounted.value,baseScale:baseScale.value}));
const occlusionId=`platform-core-mask-${useId()}`,tagLayout=shallowRef([]);
let measureTags=true;
let navigation = null;
const stars = shallowRef([]), skyPan = ref({ x: 0, y: 0 });
let skyField = null, skyStarted = 0, previousPan = { x: 0, y: 0 };
const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
let frame = 0, target = 0, previous = 0, startedClosing = 0, closingDuration = 1200, session = 0, overflow;
const descent = computed(() => descentFrame(state.progress, viewport.value.height, anchors.value.year, anchors.value.platform));
const genreTransfer = computed(() => genreTransitFrame(state.progress,viewport.value.height,anchors.value.platform,anchors.value.genre,platformOptions.value));
const modeTransfer = computed(() => modeTransitFrame(state.progress,viewport.value.height,anchors.value.genre,anchors.value.mode));
const yearTransfer = computed(() => yearTransitFrame(Math.min(1,state.progress),state.transitionLeg));
const landing = computed(() => landingParticles(descent.value.contact));
const intermediate = computed(() => !atEndpoint(state.progress));
const fade = computed(() => state.closing ? Math.max(0, 1 - closingTime.value / closingDuration) : 1);
const active = computed(() => sceneAt(state.progress));
const corePoint = computed(() => state.progress>2 ? modeTransfer.value.core : state.progress>1 ? genreTransfer.value.core : descent.value.core);
const coreTail = computed(() => state.progress>1&&state.progress<2?
  platformGenreTail(state.progress,direction.value,trail.value,viewport.value.height,anchors.value.platform,anchors.value.genre,platformOptions.value):
  filterCoreTrail(state.progress,direction.value,trail.value));
const coreStyle = computed(() => ({left:`${corePoint.value.x}px`,top:`${corePoint.value.y}px`,opacity:fade.value}));
const occlusion=computed(()=>platformCoreOcclusion(state.progress,genreTransfer.value,anchors.value.platform,baseScale.value,tagLayout.value));
const coreLayerStyle=computed(()=>occlusion.value.active?{maskImage:`url(#${occlusionId})`,'--core-visible':occlusion.value.visible}:undefined);
function measureTagLayout(){tagLayout.value=readPlatformTagLayout(dialog.value?.querySelector('#filter-space-platform .platform-shell'));measureTags=false;}
const sceneStyle = computed(() => ({
  '--year-shift': `${descent.value.yearY}px`, '--platform-shift': `${descent.value.platformY+genreTransfer.value.platformY}px`,
  '--year-opacity': (ready.value || state.progress===0 ? 1 : 0)*(state.closing ? Math.max(0,1-closingTime.value/480) : 1),
  '--platform-opacity': (ready.value || state.progress===1 ? 1 : 0)*genreTransfer.value.platformOpacity*(state.closing ? Math.max(0,1-closingTime.value/380) : 1),
  '--genre-shift': `${genreTransfer.value.genreY+modeTransfer.value.genreY}px`, '--genre-opacity': genreTransfer.value.genreOpacity*modeTransfer.value.genreOpacity,
  '--mode-shift': `${modeTransfer.value.modeY}px`, '--mode-opacity': modeTransfer.value.modeOpacity,
  '--mode-nebula': modeTransfer.value.nebula,
  '--tree-crown-scale': genreTransfer.value.gather, '--tree-base-opacity': genreTransfer.value.base, '--genre-nebula': genreTransfer.value.nebula*(1-modeTransfer.value.nebula),
  '--sky-pan-x': `${skyPan.value.x}px`, '--sky-pan-y': `${skyPan.value.y}px`,
  '--sky-travel': `${viewport.value.height*.98*yearTransfer.value.sky+genreTransfer.value.sky+modeTransfer.value.sky}px`,
  '--motion-direction': direction.value,
  '--trail-alpha-one': trail.value*.32, '--trail-alpha-two': trail.value*.15,
  '--core-tail-opacity': motion.matches || state.closing ? 0 : coreTail.value.opacity,
  '--core-tail-angle': `${coreTail.value.angle}deg`,
  '--base-flash': motion.matches ? 0 : descent.value.flash,
  '--fade': fade.value, '--atmosphere': descent.value.ambient,
}));
function landingStyle(particle) {
  const scale=baseScale.value;
  return {left:`${descent.value.core.x+particle.x*scale}px`,top:`${descent.value.core.y+particle.y*scale}px`,
    width:`${particle.size*Math.sqrt(scale)}px`,height:`${particle.size*Math.sqrt(scale)}px`,opacity:motion.matches ? 0 : particle.opacity*fade.value};
}
function readPan(){const a=space.scenes.get('platform')?.panOffset?.()||{x:0,y:0},b=space.scenes.get('genre')?.panOffset?.()||{x:0,y:0};return{x:a.x+b.x,y:a.y+b.y};}
function updateStars(now) {
  const pan = readPan();
  const dx = pan.x - previousPan.x, dy = pan.y - previousPan.y; previousPan = pan;
  // Use rendered pan deltas, never raw mouse speed or automatic fit/layout.
  if (!motion.matches && (dx || dy)) skyPan.value = { x: skyPan.value.x + dx, y: skyPan.value.y + dy };
  if (skyField) stars.value = skyField.frame({ width: viewport.value.width, height: viewport.value.height,
    ...skyPan.value, sky: viewport.value.height * .98 * yearTransfer.value.sky + genreTransfer.value.sky + modeTransfer.value.sky, elapsed: now - skyStarted });
}
function makeStars() {
  skyPan.value = { x: 0, y: 0 }; previousPan = readPan();
  skyStarted = performance.now(); skyField = createParallaxSky(Math.floor(Math.random() * 4294967296)); updateStars(skyStarted);
}
function measure(kind) {
  const rect = space.scenes.get(kind)?.core();
  if (!rect) return;
  const point = { x: rect.x+rect.width/2, y: rect.y+rect.height/2 };
  const old = anchors.value[kind];
  if (Math.abs(old.x-point.x)+Math.abs(old.y-point.y)>.1) {anchors.value = { ...anchors.value, [kind]: point };if(kind==='platform')measureTags=true;}
  if (kind==='platform') {
    platformMounted.value=!!space.scenes.get('platform')?.transit?.()?.mounted;
    // Read only scale, not the translated base position. This prevents a
    // one-frame lag while particles follow the shared core after contact.
    const base=dialog.value?.querySelector('#filter-space-platform .tree-base svg');
    if (base) {
      const box=base.getBoundingClientRect(), scale=Math.min(box.width/120,box.height/94);
      if (scale>0 && Math.abs(baseScale.value-scale)>.001) {baseScale.value=scale;measureTags=true;}
    }
    if(measureTags)measureTagLayout();
  }
}
function tick(now) {
  if (!state.opened) return;
  const dt = Math.max(0, Math.min(48, now-previous)); previous = now;
  const oldProgress=state.progress;
  if (state.closing) closingTime.value = now-startedClosing;
  else if (navigation) {
    navigation.elapsed += document.hidden ? 0 : dt;
    const t=Math.min(1,navigation.elapsed/navigation.duration);
    state.progress=navigation.from+(navigation.to-navigation.from)*smooth(t);
    if(t===1) { state.progress=navigation.to; navigation=null; }
  } else {
    const next = state.progress+(target-state.progress)*(1-Math.exp(-dt/85));
    state.progress = Math.abs(next-target)<.0001 ? target : next;
  }
  const delta=state.progress-oldProgress;
  if(Math.abs(delta)>.00001) direction.value=delta>0 ? 1 : -1;
  const strength=motion.matches || state.closing ? 0 : Math.min(1,Math.abs(delta)/Math.max(1,dt)*900);
  const nextTrail=trail.value+(strength-trail.value)*(1-Math.exp(-dt/(strength>trail.value ? 65 : 140)));
  trail.value=nextTrail<.001 ? 0 : nextTrail;
  sceneBusy.value = !state.closing && !!space.scenes.get(active.value)?.busy();
  if (ready.value) {
    sceneKinds.forEach(measure);
    space.scenes.get('year')?.paint?.(); space.scenes.get('genre')?.paint?.(now);
    space.scenes.get('mode')?.paint?.(now);
  }
  updateStars(now);
  if (!document.hidden) dustTime += dt;
  if (!dustUnavailable) {
    try {
      const frame=descent.value;
      drawPlatformStardust(stardust.value,{width:window.innerWidth,height:window.innerHeight,
        x:corePoint.value.x,y:corePoint.value.y,progress:frame.ambient*genreTransfer.value.dust,time:dustTime,
        ratio:window.devicePixelRatio || 1,reduced:motion.matches});
    } catch { dustUnavailable = true; }
  }
  frame = requestAnimationFrame(tick);
}
async function open(kind) {
  if (state.opened || !sceneKinds.every(key=>space.scenes.has(key))) return;
  const token = ++session;
  state.initializing = true; state.closing = false; state.opened = true;
  target = sceneIndex(kind); state.progress = target;
  state.transitionLeg = kind==='year' ? 'depart' : 'return';
  ready.value = false; closingTime.value = 0; navigation=null; trail.value=0;
  viewport.value={width:window.innerWidth,height:window.innerHeight};
  overflow = document.documentElement.style.overflow; document.documentElement.style.overflow = 'hidden';
  dustTime = 0; dustUnavailable = false;
  makeStars(); dialog.value.showModal();
  previous = performance.now(); frame = requestAnimationFrame(tick);
  await nextTick();
  if (token!==session || state.closing || !state.opened) return;
  await Promise.all([...space.scenes].map(([key, api]) => api.begin(key===kind)));
  if (token!==session || state.closing || !state.opened) return;
  state.year = space.scenes.get('year').value();
  await nextTick(); sceneKinds.forEach(measure); ready.value = true;
  state.initializing = false;
  await nextTick(); space.scenes.get(kind)?.focus();
}
function prepare() {
  for (const api of space.scenes.values()) api.freeze();
  measure('platform');
  measureTagLayout();
  const element = document.activeElement;
  if (element?.closest('.space-page')) {
    dialog.value.querySelector('.space-navigation button')?.focus({ preventScroll: true });
  }
}
function navigate(value, direct = false) {
  if (!state.opened || state.closing || state.initializing || sceneBusy.value) return;
  const next = clampProgress(value);
  if (next===target && !navigation) return;
  state.transitionLeg=transitLeg(state.transitionLeg,Math.min(1,state.progress),Math.min(1,next));
  if (!intermediate.value) prepare();
  target = next;
  navigation=direct && !motion.matches ? {from:state.progress,to:next,elapsed:0,duration:Math.max(650,3400*Math.abs(next-state.progress))} : null;
  if (motion.matches) { state.progress=target; trail.value=0; }
}
function wheel(event) {
  if (event.ctrlKey || event.metaKey || Math.abs(event.deltaX)>Math.abs(event.deltaY)) return;
  // The palette keeps its native scrolling, including at its boundaries.
  const scrollable = event.target.closest('.tree-palette,.mode-options');
  if (scrollable && scrollable.scrollHeight>scrollable.clientHeight+1) return;
  event.preventDefault();
  if (event.buttons || !event.deltaY) return;
  if (motion.matches) navigate(Math.round(state.progress)+(event.deltaY>0 ? 1 : -1));
  else navigate((navigation ? state.progress : target)+wheelStep(event, window.innerHeight));
}
async function retry() {
  await space.retry?.(); await nextTick();
  if (state.opened && !intermediate.value) space.scenes.get(active.value)?.focus();
}
function shortcuts(event) {
  if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.metaKey || event.altKey || event.target.closest('input:not([type="checkbox"]):not([type="radio"]),textarea,select,[contenteditable]:not([contenteditable="false"])')) return;
  const key=event.key.length===1 ? event.key.toLowerCase() : event.key;
  const position=intermediate.value ? (navigation?.to ?? target) : state.progress;
  const pages={w:Math.ceil(position)-1,ArrowUp:Math.ceil(position)-1,PageUp:Math.ceil(position)-1,s:Math.floor(position)+1,ArrowDown:Math.floor(position)+1,PageDown:Math.floor(position)+1};
  if (Object.hasOwn(pages,key)) {
    event.preventDefault(); event.stopPropagation();
    if (!event.repeat) navigate(pages[key],true);
  } else if (state.progress===0 && ['a','d','ArrowLeft','ArrowRight'].includes(key) &&
      !event.target.closest('#filter-space-year,[role="slider"]')) {
    space.scenes.get('year')?.key?.(event);
    if (event.defaultPrevented) event.stopPropagation();
  }
}
watch(() => state.progress, value => {
  if (!state.opened || state.closing || state.initializing || !ready.value || !atEndpoint(value)) return;
  const token=session;
  nextTick(() => {
    if (token!==session || !state.opened || state.closing || state.progress!==value) return;
    space.scenes.get(sceneAt(value))?.focus();
  });
}, {flush:'post'});
function sliderKey(event) {
  const change = { ArrowDown: .1, ArrowRight: .1, ArrowUp: -.1, ArrowLeft: -.1 };
  if (Object.hasOwn(change,event.key)) { event.preventDefault(); event.stopPropagation(); navigate(target+change[event.key]); }
  else if (event.key==='Home' || event.key==='End') { event.preventDefault(); navigate(event.key==='Home' ? 0 : sceneKinds.length-1,true); }
}
function cleanup() {
  ++session; cancelAnimationFrame(frame); frame = 0; navigation=null; trail.value=0;
  state.opened = false; state.closing = false; state.initializing = false;
  for (const api of space.scenes.values()) api.reset();
  ready.value = false; stars.value = []; skyField = null; skyPan.value = { x: 0, y: 0 };
  if (overflow!==undefined) { document.documentElement.style.overflow = overflow; overflow = undefined; }
}
async function close(apply) {
  if (!state.opened || state.closing || (apply && (intermediate.value || state.initializing ||
      (state.progress>0 && (state.loading || state.error))))) return;
  const token = session, kind = sceneAt(state.progress);
  const result = { year: space.scenes.get('year').value(), platforms: space.scenes.get('platform').value(), genres: space.scenes.get('genre').value(), modes: space.scenes.get('mode').value() };
  navigation=null; target=state.progress;
  state.closing = true; startedClosing = performance.now(); closingTime.value = 0;
  closingDuration = motion.matches ? 1 : kind==='year' ? 1200 : 720;
  try { await space.scenes.get(kind).exit(apply); }
  finally {
    if (token===session) {
      dialog.value.close(); cleanup();
      if (apply) space.commit(result);
      document.getElementById(kind)?.focus({ preventScroll: true });
    }
  }
}
function resized() {
  measureTags=true;
  viewport.value={width:window.innerWidth,height:window.innerHeight};
  if (ready.value) nextTick(() => sceneKinds.forEach(measure));
}
function changedMotion() { if (motion.matches && intermediate.value) { target = Math.round(state.progress); state.progress = target; navigation=null; trail.value=0; } }
space.host = { open, close };
window.addEventListener('resize',resized); motion.addEventListener('change',changedMotion);
onBeforeUnmount(() => { cleanup(); space.host = null; window.removeEventListener('resize',resized); motion.removeEventListener('change',changedMotion); if (dialog.value?.open) dialog.value.close(); });
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" id="filter-space-dialog" class="filter-space" aria-label="筛选条件" :class="{ 'is-ready': ready && !sceneBusy, 'is-closing': state.closing, 'is-initializing': !ready, 'year-in-motion': trail > .005 && state.progress > .32 && state.progress < .44, 'platform-in-motion': trail > .005 && state.progress > .50, 'genre-in-motion': state.progress>1 && state.progress<3 && intermediate, 'mode-in-motion':state.progress>2 && state.progress<3, 'base-is-flashing': descent.flash > .001 && !motion.matches }" :style="sceneStyle"
      :data-stage="descent.stage" :data-year-phase="yearTransfer.stage" :data-leg="state.transitionLeg" :data-contact="descent.contact.toFixed(4)" :data-progress="state.progress.toFixed(4)" :data-page="intermediate ? 'transition' : active" :data-genre-reveal="(genreTransfer.reveal*modeTransfer.gather).toFixed(4)" :data-mode-reveal="modeTransfer.reveal.toFixed(4)" :data-platform-exit="genreTransfer.stage" :data-platform-mounted="platformMounted" :data-aperture="genreTransfer.aperture.toFixed(4)" @wheel="wheel" @keydown.capture="shortcuts" @cancel.prevent="close(false)" @close="state.opened && cleanup()">
      <div v-if="state.opened" class="space-universe" aria-hidden="true">
        <div class="space-nebula"></div><div class="genre-nebula"></div><div class="mode-nebula"></div>
        <canvas ref="stardust" class="platform-stardust" :data-strength="platformDustStrength(descent.ambient*genreTransfer.dust).toFixed(4)" aria-hidden="true"></canvas>
        <div class="space-starfield"><div v-for="layer in stars" :key="layer.id" class="space-star-layer" :data-depth="layer.depth" :style="{ '--star-depth': layer.depth }"><span v-for="star in layer.stars" :key="star.id" :data-star="star.id" class="space-star" :style="star.style"></span></div></div>
      </div>
      <div id="filter-space-year" class="space-page" :inert="space.blocked('year')" :aria-hidden="space.blocked('year')"></div>
      <div id="filter-space-platform" class="space-page" :inert="space.blocked('platform')" :aria-hidden="space.blocked('platform')"></div>
      <div id="filter-space-genre" class="space-page" :inert="space.blocked('genre')" :aria-hidden="space.blocked('genre')"></div>
      <div id="filter-space-mode" class="space-page" :inert="space.blocked('mode')" :aria-hidden="space.blocked('mode')"></div>
      <span v-for="(particle,i) in landing" :key="`landing-${i}`" class="landing-particle" :style="landingStyle(particle)" aria-hidden="true"></span>
      <svg v-if="occlusion.active" class="core-occlusion-defs" width="0" height="0" aria-hidden="true"><defs>
        <clipPath v-for="(group,i) in occlusion.groups" :key="`clip-${i}`" :id="`${occlusionId}-clip-${i}`" clipPathUnits="userSpaceOnUse"><rect v-if="group.clip" :x="group.clip.x" :y="group.clip.y" :width="group.clip.width" :height="group.clip.height"/></clipPath>
        <mask :id="occlusionId" maskUnits="userSpaceOnUse" maskContentUnits="userSpaceOnUse" x="0" y="0" :width="viewport.width" :height="viewport.height" style="mask-type:luminance">
          <rect x="0" y="0" :width="viewport.width" :height="viewport.height" fill="white"/>
          <g :transform="`translate(${occlusion.base.x} ${occlusion.base.y}) scale(${occlusion.scale})`"><path :d="BASE_OUTLINE_PATH" transform="translate(-60 -39)" fill="black" :fill-opacity="occlusion.opacity"/><path :d="BASE_APERTURE_PATH" :transform="`scale(${occlusion.aperture})`" fill="white"/></g>
          <g v-for="(group,i) in occlusion.groups" :key="i" :clip-path="group.clip?`url(#${occlusionId}-clip-${i})`:undefined"><rect v-for="(tag,j) in group.tags" :key="j" :x="tag.x" :y="tag.y" :width="tag.width" :height="tag.height" :rx="tag.radius" fill="black" :fill-opacity="occlusion.opacity"/></g>
        </mask>
      </defs></svg>
      <div class="core-depth-layer" :class="{'has-foreground':occlusion.active}" :style="coreLayerStyle" :data-core-depth="occlusion.phase" :data-core-visible="occlusion.visible.toFixed(4)">
        <div v-if="ready && !sceneBusy" class="space-core" :style="coreStyle" aria-hidden="true"><span></span><i class="core-motion-trail"></i></div>
      </div>
      <button class="space-close" type="button" aria-label="关闭筛选选择" :disabled="state.closing" @click="close(false)">×</button>
      <div v-if="state.progress>0 && state.error" class="space-error" role="alert">{{ state.error }}<button type="button" @click="retry">重试</button></div>
      <nav class="space-navigation" aria-label="筛选页切换" :inert="state.closing">
        <button type="button" :class="{ selected: state.progress===0 }" :aria-current="state.progress===0 ? 'page' : undefined" :disabled="state.initializing || sceneBusy" @click="navigate(0,true)">发售年份</button>
        <div class="space-track" role="slider" tabindex="0" aria-label="筛选页切换进度" aria-valuemin="0" :aria-valuemax="(sceneKinds.length-1)*100" :aria-valuenow="Math.round(state.progress*100)" :aria-valuetext="intermediate ? '筛选页之间，左右键微调，W或上键向前，S或下键向后' : {year:'发售年份',platform:'游戏平台',genre:'玩法类型',mode:'游玩模式'}[active]" @keydown="sliderKey"><i :style="{ left: `${state.progress/(sceneKinds.length-1)*100}%` }"></i></div>
        <button type="button" :class="{ selected: state.progress===1 }" :aria-current="state.progress===1 ? 'page' : undefined" :disabled="state.initializing || sceneBusy" @click="navigate(1,true)">游戏平台</button>
        <button type="button" :class="{ selected: state.progress===2 }" :aria-current="state.progress===2 ? 'page' : undefined" :disabled="state.initializing || sceneBusy" @click="navigate(2,true)">玩法类型</button>
        <button type="button" :class="{ selected: state.progress===3 }" :aria-current="state.progress===3 ? 'page' : undefined" :disabled="state.initializing || sceneBusy" @click="navigate(3,true)">游玩模式</button>
      </nav>
      <footer class="space-actions"><button class="space-cancel" type="button" :disabled="state.closing" @click="close(false)">取消</button><button class="primary space-confirm" type="button" :disabled="state.closing || intermediate || state.initializing || (state.progress>0 && (state.loading || !!state.error))" @click="close(true)">{{ state.progress>0 && state.loading ? '载入中' : '确认' }}</button></footer>
    </dialog>
  </Teleport>
</template>

<style scoped>
.filter-space { position:fixed;inset:0;width:100%;height:100dvh;max-width:none;max-height:none;margin:0;padding:0;border:0;border-radius:0;overflow:hidden;background:transparent;color:#dce6f3;user-select:none;--fade:1; }
.filter-space::backdrop { background:#000;animation:space-enter 650ms ease both; }
.filter-space.is-closing::backdrop { animation:none;opacity:var(--fade); }
.space-universe { position:absolute;inset:0;overflow:hidden;pointer-events:none;background:#000;opacity:var(--fade);animation:space-enter 650ms ease both; }
.is-closing .space-universe { animation:none; }
.space-nebula { position:absolute;inset:0;opacity:calc(.18 * (1 - var(--atmosphere)));background:radial-gradient(ellipse at 67% 55%,#17365750,transparent 52%),radial-gradient(ellipse at 25% 70%,#161d3529,transparent 48%); }
.platform-stardust { position:absolute;inset:0;width:100%;height:100%;pointer-events:none; }
.space-starfield { position:absolute;inset:0;overflow:hidden;pointer-events:none;mask-image:linear-gradient(90deg,transparent,#000 3%,#000 97%,transparent),linear-gradient(transparent,#000 5%,#000 95%,transparent);mask-composite:intersect; }
.space-star-layer { position:absolute;inset:0;transform:translate3d(calc(var(--sky-pan-x,0px) * var(--star-depth)),calc(var(--sky-pan-y,0px) * var(--star-depth) - var(--sky-travel)),0); }
.space-star { position:absolute;width:var(--size);height:var(--size);border-radius:50%;background:#c0d6ec;opacity:0;box-shadow:0 0 5px #93bced30;animation:space-star-life var(--life) ease-in-out var(--delay) infinite both; }
.space-page { position:absolute;inset:0;pointer-events:none; }
.space-page:not([inert]) { pointer-events:auto; }
.space-page :deep(.year-dialog),.space-page :deep(.platform-dialog),.space-page :deep(.genre-dialog),.space-page :deep(.mode-dialog) { background:transparent;overflow:hidden; }
.space-page :deep(.mode-close),.space-page :deep(.mode-footer){visibility:hidden;pointer-events:none;}
.space-page :deep(.genre-close),.space-page :deep(.genre-footer),.space-page :deep(.year-close),.space-page :deep(.platform-close),.space-page :deep(.year-footer),.space-page :deep(.platform-footer) { visibility:hidden;pointer-events:none; }
#filter-space-year :deep(.year-scene) { transform:translate3d(0,var(--year-shift),0);opacity:var(--year-opacity)!important; }
#filter-space-platform :deep(.platform-shell) { transform:translate3d(0,var(--platform-shift),0);opacity:var(--platform-opacity)!important; }
.year-in-motion #filter-space-year :deep(.year-header h2),.year-in-motion #filter-space-year :deep(.year-current) { text-shadow:0 calc(var(--motion-direction) * .16em) .05em rgb(136 178 228 / var(--trail-alpha-one)),0 calc(var(--motion-direction) * .38em) .10em rgb(136 178 228 / var(--trail-alpha-two)); }
.year-in-motion #filter-space-year :deep(.year-stage) { filter:drop-shadow(0 calc(var(--motion-direction) * clamp(10px, var(--sphere-size) * .024, 22px)) 3px rgb(136 178 228 / var(--trail-alpha-one))); }
.platform-in-motion #filter-space-platform :deep(.platform-header h2),.platform-in-motion #filter-space-platform :deep(.platform-header output),.platform-in-motion #filter-space-platform :deep(.platform-tools),.platform-in-motion #filter-space-platform :deep(.tree-palette) { text-shadow:0 calc(var(--motion-direction) * .16em) .05em rgb(136 178 228 / var(--trail-alpha-one)),0 calc(var(--motion-direction) * .36em) .10em rgb(136 178 228 / var(--trail-alpha-two)); }
.platform-in-motion #filter-space-platform :deep(.tree-viewport) { filter:drop-shadow(0 calc(var(--motion-direction) * 11px) 2.5px rgb(136 178 228 / var(--trail-alpha-one))); }
.is-initializing #filter-space-year :deep(.year-scene),.is-initializing #filter-space-platform :deep(.platform-shell) { transform:none; }
.is-ready :deep(.genre-center),.is-ready :deep(.sphere-center),.is-ready :deep(.base-core),.is-ready :deep(.mode-center) { visibility:hidden; }
.base-is-flashing #filter-space-platform :deep(.tree-base svg) { filter:drop-shadow(0 0 7px rgb(135 192 255 / calc(var(--base-flash) * .75))); }
.base-is-flashing #filter-space-platform :deep(.base-top) { fill:rgb(calc(23 + var(--base-flash) * 92) calc(34 + var(--base-flash) * 125) calc(48 + var(--base-flash) * 151));stroke:rgb(calc(61 + var(--base-flash) * 118) calc(83 + var(--base-flash) * 135) calc(110 + var(--base-flash) * 145)); }
.base-is-flashing #filter-space-platform :deep(.base-side) { fill:rgb(calc(16 + var(--base-flash) * 58) calc(25 + var(--base-flash) * 89) calc(35 + var(--base-flash) * 117));stroke:rgb(calc(38 + var(--base-flash) * 122) calc(54 + var(--base-flash) * 145) calc(74 + var(--base-flash) * 161)); }
.base-is-flashing #filter-space-platform :deep(.base-ring) { stroke:rgb(calc(107 + var(--base-flash) * 110) calc(146 + var(--base-flash) * 88) calc(191 + var(--base-flash) * 64));opacity:calc(.45 + var(--base-flash) * .55); }
.landing-particle { position:fixed;z-index:20;border-radius:50%;pointer-events:none;background:#c9e4ff;box-shadow:0 0 5px #91c6ff99;transform:translate(-50%,-50%); }
.space-core { position:fixed;z-index:15;width:10px;height:10px;transform:translate(-50%,-50%);border-radius:50%;pointer-events:none;background:#d4e7ff;box-shadow:0 0 8px #abd3ffbb,0 0 28px #75a8e955,0 0 70px #6598e229; }
.space-core span { position:absolute;inset:-10px;border-radius:50%;background:radial-gradient(circle,#9bc4ff40,transparent 70%);animation:core-breathe 7s ease-in-out infinite; }
.core-depth-layer{position:fixed;inset:0;pointer-events:none;z-index:15}
.core-occlusion-defs{position:absolute;pointer-events:none}
.has-foreground .space-core{box-shadow:0 0 8px rgb(171 211 255 / calc(.73 * var(--core-visible))),0 0 28px rgb(117 168 233 / calc(.33 * var(--core-visible))),0 0 70px rgb(101 152 226 / calc(.16 * var(--core-visible)))}
.has-foreground .space-core span{visibility:hidden}
.has-foreground .core-motion-trail{opacity:calc(var(--core-tail-opacity) * var(--core-visible))}
.core-motion-trail { position:absolute;left:0;bottom:5px;width:10px;height:36px;pointer-events:none;transform-origin:50% 100%;transform:rotate(var(--core-tail-angle));opacity:var(--core-tail-opacity);background:linear-gradient(to top,#b7d8ffbb,transparent 95%);border-radius:60%;filter:blur(2.5px); }
.space-close { position:fixed;right:24px;top:20px;z-index:30;width:44px;min-height:44px;padding:0;border:0;background:transparent;color:#a2b3ca;font-size:1.8rem; }
.space-navigation { position:fixed;left:50%;bottom:30px;transform:translateX(-50%);display:flex;align-items:center;gap:20px;z-index:30; }
.space-navigation button { min-height:44px;padding:8px 6px;background:transparent;border:0;color:#7d8fa9;white-space:nowrap;font-size:.9rem; }
.space-navigation button.selected { color:#d0e1f7; }
.space-track { position:relative;width:100px;height:24px;outline-offset:5px; }
.space-track::before { content:'';position:absolute;left:0;right:0;top:11px;height:1px;background:#344760; }
.space-track i { position:absolute;top:8px;width:7px;height:7px;border-radius:50%;transform:translateX(-50%);background:#aecdf6;box-shadow:0 0 12px #84baff60; }
.space-actions { position:fixed;right:32px;bottom:26px;display:flex;gap:20px;z-index:30; }
.space-actions button { min-width:110px; }
.space-cancel { border-color:transparent;background:transparent;color:#a3b2c8; }
.space-error { position:fixed;left:50%;top:14px;transform:translateX(-50%);z-index:35;padding:6px 12px;border-radius:6px;background:#341e23;color:#e4b4b4;font-size:.85rem; }
.space-error button { padding:3px 8px;margin-left:8px; }
.is-closing .space-navigation,.is-closing .space-actions,.is-closing .space-close { opacity:var(--fade);pointer-events:none; }
.genre-nebula { position:absolute;inset:0;pointer-events:none;opacity:calc(var(--genre-nebula) * .75);background:radial-gradient(ellipse at 45% 56%,#29335b38,transparent 57%),radial-gradient(ellipse at 73% 40%,#4b315329,transparent 50%); }
#filter-space-genre :deep(.genre-shell) {transform:translate3d(0,var(--genre-shift),0);opacity:var(--genre-opacity);}
.mode-nebula{position:absolute;inset:0;pointer-events:none;opacity:var(--mode-nebula);background:radial-gradient(ellipse at 50% 54%,#12305548,transparent 50%),radial-gradient(ellipse at 23% 75%,#14233a30,transparent 48%)}
#filter-space-mode :deep(.mode-shell){transform:translate3d(0,var(--mode-shift),0);opacity:var(--mode-opacity)}
.genre-in-motion #filter-space-genre :deep(.genre-header),.mode-in-motion #filter-space-mode :deep(.mode-header),.mode-in-motion #filter-space-mode :deep(.mode-tools),.mode-in-motion #filter-space-mode :deep(.mode-options){text-shadow:0 calc(var(--motion-direction) * .16em) .05em rgb(136 178 228 / var(--trail-alpha-one)),0 calc(var(--motion-direction) * .36em) .10em rgb(136 178 228 / var(--trail-alpha-two))}
.mode-in-motion #filter-space-mode :deep(.mode-array){filter:drop-shadow(0 calc(var(--motion-direction) * 11px) 3px rgb(136 178 228 / var(--trail-alpha-one)))}
@keyframes space-enter { from { opacity:0; } to { opacity:1; } }
@keyframes space-star-life { 0%,100% { opacity:0; } 35%,55% { opacity:var(--peak); } }
@keyframes core-breathe { 0%,100% { opacity:.4;transform:scale(.8); } 50% { opacity:.8;transform:scale(1.15); } }
@media(max-width:1000px) { .space-page :deep(.platform-body) { padding-bottom:60px; }.space-navigation { bottom:82px;gap:16px; }.space-actions { bottom:20px;right:20px; }.space-track { width:80px; } }
@media(max-width:600px) { .space-navigation { bottom:80px;gap:9px; }.space-navigation button {font-size:.77rem;}.space-track{width:55px;}.space-close { right:8px;top:16px; }.space-actions button { min-width:100px; } }
@media(prefers-reduced-motion:reduce) { .filter-space::backdrop,.space-universe,.space-star,.space-core span { animation:none; }.space-star { opacity:calc(var(--peak) * .5); }.core-motion-trail,.landing-particle { display:none; } }
</style>
