<script setup>
import { computed, inject, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue';
import { filterSpaceKey, layoutPoint } from '../filterSpace.js';
import PlatformMark from './PlatformMark.vue';
import { createBranch, treeBounds, branchRects, trunkPath, twigPath, HUB, LEAF, ROOT } from '../platformTreeLayout.js';
import { otherCategories, createOtherCluster, clusterPath, OTHER_PAGE_SIZE } from '../platformOtherGroups.js';
import { platformExitPhases } from '../platformGenreTransit.js';
import { platformEnergyRoutes, platformEnergyFrame } from '../platformEnergy.js';
import {BASE_APERTURE_PATH,wireApertureMaskBounds,wireApertureTransform} from '../platformOcclusion.js';

const props = defineProps({ groups: Array, selected: Array, query: String, active: Boolean, disabled: Boolean, wheelNavigation: Boolean });
const emit = defineEmits(['choose']);
const viewport = ref(null), branches = ref([]), growing = ref(new Set()), drag = ref(null);
const view = ref({ x: 400, y: 300, zoom: 1 }), preview = ref(null), announce = ref('');
const otherOpen = ref(''), otherPage = ref(0), panning = ref(false);
const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
const space=inject(filterSpaceKey,null),reduced=ref(motion.matches),apertureId=`platform-aperture-${useId()}`;
const exitFrame=computed(()=>platformExitPhases(space?.state.progress??1,branches.value.length>0));
const energyRoutes=computed(()=>platformEnergyRoutes(branches.value,otherCluster.value,otherAnchor.value));
let previousProgress=1;const energyDirection=ref(1);
watch(()=>space?.state.progress,value=>{if(value>previousProgress)energyDirection.value=1;else if(value<previousProgress)energyDirection.value=-1;previousProgress=value??1;});
const energy=computed(()=>!props.active||reduced.value||exitFrame.value.flow<=0||exitFrame.value.flow>=1?[]:
 energyRoutes.value.map((route,i)=>platformEnergyFrame(route,exitFrame.value.flow,i,energyDirection.value)).filter(p=>p.opacity>.002));
const wireMaskId=`${apertureId}-wires`;
const wireMaskBounds=computed(()=>wireApertureMaskBounds(treeBounds(branches.value,otherCluster.value?.rects||[])));
const defaults = { PC: -150, PlayStation: -30, Xbox: 150, Nintendo: 30, 移动设备: -90, 其他: 90 };
const accents = { PC: '#9db3ce', PlayStation: '#81a7ec', Xbox: '#88b6a1', Nintendo: '#bc858d', 移动设备: '#b1a2d0', 其他: '#9eaebf' };
const remembered = new Map(), timers = new Map();
let viewFrame = 0, viewTime = 0, viewTarget = null, viewEase = 48, cameraMotion = false;
const skyOffset = { x: 0, y: 0 };
let gesture = null, suppressedUntil = 0, suppressedFamily = null, version = 0, observer;
const groupMap = computed(() => new Map((props.groups || []).map(group => [group.family, group])));
const nodeMap = computed(() => new Map((props.groups || []).flatMap(group => group.platforms.map(platform => [platform.id, platform]))));
const otherGroups = computed(() => otherCategories(groupMap.value.get('其他')?.platforms || []));
const categoryMap = computed(() => new Map(otherGroups.value.map(group => [group.id, group])));
const branchPlatforms = family => family === '其他' ? otherGroups.value : groupMap.value.get(family)?.platforms || [];
const selectedCategory = id => categoryMap.value.get(id)?.platforms.some(platform => props.selected.includes(platform.id)) || false;
const leafSelected = leaf => categoryMap.value.has(leaf.id) ? selectedCategory(leaf.id) : props.selected.includes(leaf.id);
const openCategory = computed(() => otherGroups.value.find(group => group.key === otherOpen.value));
const otherPageCount = computed(() => Math.ceil((openCategory.value?.platforms.length || 0) / OTHER_PAGE_SIZE));
const currentOtherPage = computed(() => Math.max(0, Math.min(otherPage.value, otherPageCount.value - 1)));
const otherBranch = computed(() => branches.value.find(branch => branch.family === '其他'));
const otherAnchor = computed(() => otherBranch.value?.leaves.find(leaf => leaf.id === openCategory.value?.id));
const otherCluster = computed(() => {
  if (!otherAnchor.value || !openCategory.value) return null;
  const platforms = openCategory.value.platforms.slice(currentOtherPage.value * OTHER_PAGE_SIZE, (currentOtherPage.value+1)*OTHER_PAGE_SIZE);
  return createOtherCluster(otherAnchor.value, platforms, otherBranch.value.angle, [ROOT, ...branches.value.flatMap(branchRects)]);
});
const attached = family => branches.value.some(branch => branch.family === family);
const selectedIn = family => (groupMap.value.get(family)?.platforms || []).some(p => props.selected.includes(p.id));
const matches = platform => !props.query?.trim() || `${platform.name} ${platform.short} ${platform.family}`.toLocaleLowerCase().includes(props.query.trim().toLocaleLowerCase());
const palette = computed(() => (props.groups || []).filter(group => !props.query?.trim() || group.platforms.some(matches)));
const worldStyle = computed(() => ({ transform: `translate(${view.value.x}px,${view.value.y}px) scale(${view.value.zoom})` }));
const nodeStyle = (node, size) => ({ width: `${size.width}px`, height: `${size.height}px`, transform: `translate(${node.x}px,${node.y}px) translate(-50%,-50%)` });
// Rendered coordinates remain the shared orb's anchor throughout a drag.
// A short frame-rate-independent follow avoids both event jitter and long inertia.
function applyView(next) {
  if (cameraMotion) { skyOffset.x += next.x - view.value.x; skyOffset.y += next.y - view.value.y; }
  view.value = next;
}
function stopViewMotion() {
  cancelAnimationFrame(viewFrame); viewFrame = 0; viewTarget = null; cameraMotion = false;
}
function paintView(now) {
  viewFrame = 0;
  if (!viewTarget) return;
  const dt = Math.max(0, Math.min(48, now - viewTime)); viewTime = now;
  const amount = 1 - Math.exp(-dt / viewEase), current = view.value;
  const next = Object.fromEntries(['x', 'y', 'zoom'].map(key => [key, current[key] + (viewTarget[key] - current[key]) * amount]));
  if (Math.hypot(next.x - viewTarget.x, next.y - viewTarget.y) < .12 && Math.abs(next.zoom - viewTarget.zoom) < .0001) {
    applyView(viewTarget); viewTarget = null; cameraMotion = false; return;
  }
  applyView(next); viewFrame = requestAnimationFrame(paintView);
}
function moveView(next, animate = false, ease = 65, pan = false) {
  if (!animate || motion.matches) { stopViewMotion(); cameraMotion = pan; applyView(next); cameraMotion = false; return; }
  cameraMotion = pan; viewTarget = next; viewEase = ease;
  if (!viewFrame) { viewTime = performance.now(); viewFrame = requestAnimationFrame(paintView); }
}
function reducedMotionChanged() {
  reduced.value=motion.matches;
  if (motion.matches && viewTarget) { const final = viewTarget; applyView(final); stopViewMotion(); }
}
motion.addEventListener('change', reducedMotionChanged);
function fitBase(event) {
  if (event?.detail > 0 && suppressedFamily === '__base__' && performance.now() < suppressedUntil) return;
  fit(branches.value, true);
}
function clearGrowth(family) {
  clearTimeout(timers.get(family)); timers.delete(family);
  const next = new Set(growing.value); next.delete(family); growing.value = next;
}
function fit(list = branches.value, animate = false) {
  if (!viewport.value || !props.active) return;
  const width = viewport.value.clientWidth, height = viewport.value.clientHeight, bounds = treeBounds(list, list.some(branch => branch.family==='其他') ? otherCluster.value?.rects || [] : []);
  const zoom = Math.max(.35, Math.min(1, (width - 70) / (bounds.right - bounds.left + 64), (height - 70) / (bounds.bottom - bounds.top + 64)));
  const marginX = Math.min(150, width * .32), marginY = Math.min(150, height * .32);
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  moveView({ zoom,
    x: clamp(width/2 - (bounds.left+bounds.right)/2*zoom, marginX, width-marginX),
    y: clamp(height/2 - (bounds.top+bounds.bottom)/2*zoom, marginY, height-marginY) }, animate);
}
function focus(family) {
  const branch = branches.value.find(branch => branch.family === family);
  if (!branch || !viewport.value) return;
  const rects = [...branchRects(branch), ...(family==='其他' ? otherCluster.value?.rects || [] : [])], left = Math.min(...rects.map(r => r.x-r.width/2)), right = Math.max(...rects.map(r => r.x+r.width/2));
  const top = Math.min(...rects.map(r => r.y-r.height/2)), bottom = Math.max(...rects.map(r => r.y+r.height/2));
  const width = viewport.value.clientWidth, height = viewport.value.clientHeight;
  const zoom = Math.max(.65, Math.min(1.1, (width-60)/(right-left+40), (height-60)/(bottom-top+40)));
  moveView({ zoom, x: width/2-(left+right)/2*zoom, y: height/2-(top+bottom)/2*zoom }, true);
}
function attach(family, preferred = remembered.get(family) ?? defaults[family] ?? 0, animate = props.active) {
  const group = groupMap.value.get(family);
  if (!group || (props.disabled && animate)) return;
  const others = branches.value.filter(branch => branch.family !== family);
  const branch = { ...createBranch(family, branchPlatforms(family), preferred, others), version: ++version };
  branches.value = [...others, branch]; remembered.set(family, branch.angle);
  clearGrowth(family);
  if (animate && !motion.matches) {
    growing.value = new Set([...growing.value, family]);
    timers.set(family, setTimeout(() => clearGrowth(family), 1500 + Math.min(500, branch.leaves.length * 90)));
  }
  announce.value = `${family}已展开，${branch.leaves.length}${family==='其他'?'个分组':'个平台'}`;
  nextTick(() => fit(branches.value, animate));
}
function collapse(family) {
  if (props.disabled) return;
  branches.value = branches.value.filter(branch => branch.family !== family); clearGrowth(family);
  announce.value = `${family}已收起，已选平台保留`;
  nextTick(() => { fit(); viewport.value?.parentElement.querySelector(`.brand-module[data-family="${family}"]`)?.focus({ preventScroll: true }); });
}
function activate(family, event) {
  if ((event?.detail > 0 && family === suppressedFamily && performance.now() < suppressedUntil) || props.disabled) return;
  if (attached(family)) focus(family); else attach(family);
}
function rotate(family, event) {
  const actions = { ArrowLeft: -15, ArrowRight: 15, ArrowUp: -15, ArrowDown: 15 };
  if (!Object.hasOwn(actions, event.key) || props.disabled) return;
  event.preventDefault(); attach(family, (remembered.get(family) ?? defaults[family]) + actions[event.key]);
  nextTick(() => viewport.value?.querySelector(`.tree-hub[data-family="${family}"] .hub-handle`)?.focus({ preventScroll: true }));
}
function point(event) {
  const box = viewport.value.getBoundingClientRect();
  return { x: (event.clientX - box.x - view.value.x) / view.value.zoom, y: (event.clientY - box.y - view.value.y) / view.value.zoom,
    inside: event.clientX > box.x + 8 && event.clientX < box.right - 8 && event.clientY > box.y + 8 && event.clientY < box.bottom - 8 };
}
function begin(family, event, source = 'palette') {
  if (props.disabled || event.button !== 0 || gesture) return;
  stopViewMotion();
  event.stopPropagation();
  if (source === 'palette' && (view.value.x < 40 || view.value.y < 40 || view.value.x > viewport.value.clientWidth-40 || view.value.y > viewport.value.clientHeight-40)) fit();
  gesture = { family, source, pointer: event.pointerId, element: event.currentTarget, startX: event.clientX, startY: event.clientY, active: false };
  event.currentTarget.setPointerCapture(event.pointerId);
}
function moving(event) {
  if (!gesture || gesture.pointer !== event.pointerId) return;
  if (!gesture.active && Math.hypot(event.clientX - gesture.startX, event.clientY - gesture.startY) < 7) return;
  event.preventDefault();
  if (!gesture.active) { gesture.active = true; gesture.element.setPointerCapture(event.pointerId); }
  const location = point(event), family = gesture.family;
  const nearRoot = Math.hypot(location.x, location.y) <= 280;
  const nearBranch = branches.value.some(branch => Math.hypot(location.x - branch.hub.x, location.y - branch.hub.y) < 110);
  const valid = location.inside && (gesture.source === 'hub' || nearRoot || nearBranch);
  const preferred = Math.hypot(location.x, location.y) < 24 ? (remembered.get(family) ?? defaults[family]) : Math.atan2(location.y, location.x) * 180 / Math.PI;
  drag.value = { family, x: event.clientX, y: event.clientY, valid };
  preview.value = valid ? createBranch(family, branchPlatforms(family), preferred, branches.value.filter(branch => branch.family !== family)) : null;
}
function cancelGesture() {
  const previous = gesture; gesture = null; drag.value = null; preview.value = null; panning.value = false;
  if (previous?.active) { suppressedUntil = performance.now() + 300; suppressedFamily = previous.source === 'pan' ? '__base__' : previous.family; }
  if (previous?.element.hasPointerCapture(previous.pointer)) previous.element.releasePointerCapture(previous.pointer);
}
function dropped(event) {
  if (!gesture || gesture.pointer !== event.pointerId) return;
  const family = gesture.family, result = preview.value, moved = gesture.active;
  if (moved) suppressedUntil = performance.now() + 300;
  cancelGesture();
  if (moved && result) attach(family, result.angle);
}
function panStart(event) {
  if (props.disabled || event.button !== 0 || gesture || event.target.closest('input,label') || (event.target.closest('button') && !event.target.closest('.tree-base'))) return;
  stopViewMotion();
  gesture = { source: 'pan', pointer: event.pointerId, element: event.target.closest('.tree-base') || event.currentTarget, startX: event.clientX, startY: event.clientY, x: view.value.x, y: view.value.y, active: false };
  // Capture on the base itself to preserve its click while retaining outside releases.
  gesture.element.setPointerCapture(event.pointerId);
}
function panMove(event) {
  if (gesture?.source !== 'pan' || gesture.pointer !== event.pointerId) return;
  if (!gesture.active && Math.hypot(event.clientX - gesture.startX, event.clientY - gesture.startY) < 5) return;
  event.preventDefault();
  if (!gesture.active) { gesture.active = true; panning.value = true; gesture.element.setPointerCapture(event.pointerId); }
  moveView({ ...view.value, x: gesture.x + event.clientX - gesture.startX, y: gesture.y + event.clientY - gesture.startY }, true, 38, true);
}
function panEnd(event) {
  if (gesture?.source !== 'pan' || gesture.pointer !== event.pointerId) return;
  panMove(event); cancelGesture();
}
function abortGesture() { cancelGesture(); stopViewMotion(); }
function zoomAt(factor, clientX, clientY) {
  if (props.disabled || !viewport.value) return;
  const box = viewport.value.getBoundingClientRect(), x = clientX ?? box.x + box.width / 2, y = clientY ?? box.y + box.height / 2;
  const current = viewTarget || view.value;
  const zoom = Math.max(.35, Math.min(1.8, current.zoom * factor)), ratio = zoom / current.zoom;
  moveView({ zoom, x: x - box.x - (x - box.x - current.x) * ratio, y: y - box.y - (y - box.y - current.y) * ratio }, true);
}
function wheel(event) {
  if (props.wheelNavigation || event.ctrlKey || event.metaKey) return;
  event.preventDefault(); zoomAt(Math.exp(-event.deltaY * .001), event.clientX, event.clientY);
}
function selectedFamilies() {
  for (const group of props.groups || []) if (group.platforms.some(p => props.selected.includes(p.id)) && !attached(group.family)) attach(group.family, undefined, false);
}
function focusOther() {
  if (!otherCluster.value || !viewport.value) return;
  const {box} = otherCluster.value, width = viewport.value.clientWidth, height = viewport.value.clientHeight;
  const zoom = Math.max(.65, Math.min(1.1, (width-44)/(box.width+28), (height-44)/(box.height+28)));
  moveView({ zoom, x: width/2-box.x*zoom, y: height/2-box.y*zoom }, true);
}
function showOther(key, page = 0, toggle = false) {
  if (props.disabled) return;
  if (toggle && otherOpen.value===key) {
    otherOpen.value=''; clearGrowth('other-detail'); announce.value='分组已收起，已选平台保留'; nextTick(()=>focus('其他')); return;
  }
  otherOpen.value=key; otherPage.value=page; clearGrowth('other-detail');
  if (!motion.matches && props.active) { growing.value=new Set([...growing.value,'other-detail']); timers.set('other-detail',setTimeout(()=>clearGrowth('other-detail'),1800)); }
  announce.value=`${otherGroups.value.find(group=>group.key===key)?.name || '分组'}已展开`;
  nextTick(focusOther);
}
watch(() => props.active, async active => {
  cancelGesture();
  if (!active) { stopViewMotion(); for (const family of [...timers.keys()]) clearGrowth(family); return; }
  selectedFamilies(); await nextTick(); fit();
  if (!otherOpen.value) {
    const group=otherGroups.value.find(category=>category.platforms.some(platform=>props.selected.includes(platform.id)));
    if (group) { otherOpen.value=group.key; otherPage.value=Math.floor(group.platforms.findIndex(platform=>props.selected.includes(platform.id))/OTHER_PAGE_SIZE); await nextTick(); fit(); }
  }
  if (viewport.value?.clientWidth < 600 && branches.value.length) {
    if (otherCluster.value) focusOther();
    else focus(branches.value.find(branch => selectedIn(branch.family))?.family ?? branches.value[0].family);
  }
}, { immediate: true });
watch(() => (props.groups || []).map(g => `${g.family}:${g.platforms.map(p => p.id).join(',')}`).join('|') + '|other:' + otherGroups.value.map(group=>`${group.key}:${group.platforms.map(p=>p.id).join(',')}`).join('|'), () => {
  cancelGesture();
  for (const branch of [...branches.value]) {
    const group = groupMap.value.get(branch.family);
    if (!group) collapse(branch.family);
    else if (branch.leaves.map(p => p.id).join(',') !== branchPlatforms(branch.family).map(p => p.id).join(',')) attach(branch.family, branch.angle, false);
  }
  selectedFamilies();
  if (otherOpen.value && !otherGroups.value.some(group=>group.key===otherOpen.value)) {
    otherOpen.value=otherGroups.value.find(group=>group.platforms.some(platform=>props.selected.includes(platform.id)))?.key || ''; otherPage.value=0;
  }
}, { immediate: true });
watch(() => props.query, () => {
  if (props.query?.trim()) for (const group of palette.value) if (!attached(group.family)) attach(group.family);
  if (props.query?.trim()) {
    const category=otherGroups.value.find(group=>group.platforms.some(matches));
    if (category) showOther(category.key,Math.floor(category.platforms.findIndex(matches)/OTHER_PAGE_SIZE));
  }
});
watch(() => props.disabled, value => { if (value) abortGesture(); });
nextTick(() => { if (viewport.value) { observer = new ResizeObserver(() => { cancelGesture(); if (otherCluster.value && (props.query?.trim() || viewport.value.clientWidth < 600)) focusOther(); else fit(); }); observer.observe(viewport.value); } });
defineExpose({
  freeze() { abortGesture(); for (const key of [...timers.keys()]) clearGrowth(key); },
  panOffset: () => ({ ...skyOffset }),
  transit: () => ({ mounted: branches.value.length>0 }),
  core: () => layoutPoint(viewport.value,view.value.x,view.value.y+.25),
  focusBase: () => viewport.value?.querySelector('.tree-base')?.focus({ preventScroll: true }),
});
onBeforeUnmount(() => { abortGesture(); motion.removeEventListener('change', reducedMotionChanged); observer?.disconnect(); for (const timer of timers.values()) clearTimeout(timer); });
</script>

<template>
  <div class="platform-tree">
    <nav class="tree-palette" aria-label="平台品牌">
      <p class="palette-guide">点击展开 · 拖向基座</p>
      <button v-for="group in palette" :key="group.family" type="button" class="brand-module"
        :class="{ attached: attached(group.family), 'has-selection': selectedIn(group.family) }" :data-family="group.family"
        :aria-expanded="attached(group.family)" :aria-label="`${group.family}，点击展开或拖动挂载`" :disabled="disabled"
        :title="attached(group.family) ? '点击聚焦，或拖动调整方向' : '点击展开，或拖向基座选择方向'"
        @pointerdown="begin(group.family, $event)" @pointermove="moving" @pointerup="dropped" @pointercancel="cancelGesture" @lostpointercapture="cancelGesture" @click="activate(group.family,$event)">
        <PlatformMark :family="group.family" /><span>{{ group.family }}</span><i aria-hidden="true"></i>
      </button>
    </nav>
    <div ref="viewport" class="tree-viewport" :class="{ 'is-dragging': !!drag, 'is-panning': panning }" aria-label="平台树画布，可拖动基座或空白处平移" @pointerdown="panStart" @pointermove="panMove" @pointerup="panEnd" @pointercancel="abortGesture" @lostpointercapture="gesture && abortGesture()" @wheel="wheel">
      <div class="tree-world" :style="worldStyle">
        <svg class="tree-wires" width="1" height="1" aria-hidden="true">
          <defs><mask :id="wireMaskId" maskUnits="userSpaceOnUse" maskContentUnits="userSpaceOnUse" :x="wireMaskBounds.x" :y="wireMaskBounds.y" :width="wireMaskBounds.width" :height="wireMaskBounds.height" style="mask-type:luminance"><rect v-bind="wireMaskBounds" fill="white"/><path :d="BASE_APERTURE_PATH" :transform="wireApertureTransform(exitFrame.aperture)" fill="black" stroke="none"/></mask></defs>
          <g :mask="exitFrame.aperture>0?`url(#${wireMaskId})`:undefined">
          <circle v-if="drag" class="drop-zone" cx="0" cy="0" r="280" />
          <g v-for="branch in branches" :key="`${branch.family}:${branch.version}`" class="branch-wires" :class="{ growing: growing.has(branch.family), selected: selectedIn(branch.family) }" :style="{ '--branch': accents[branch.family] }">
            <path class="trunk" :d="trunkPath(branch)" pathLength="1" />
            <path v-for="(leaf,i) in branch.leaves" :key="leaf.id" class="twig" :class="{ selected: leafSelected(leaf) }" :d="twigPath(branch,leaf)" pathLength="1" :style="{ '--delay': `${400 + Math.min(i * 90, 500)}ms` }" />
          </g>
          <g v-if="otherCluster" class="branch-wires other-detail-wires" :class="{ growing: growing.has('other-detail') }" style="--branch:#9eaebf">
            <path class="trunk" :d="clusterPath(otherAnchor,otherCluster.header)" pathLength="1" />
            <path v-for="(leaf,i) in otherCluster.leaves" :key="leaf.id" class="twig" :class="{ selected: selected.includes(leaf.id) }" :d="clusterPath(otherCluster.header,leaf)" pathLength="1" :style="{ '--delay': `${400+i*90}ms` }" />
          </g>
          <g v-if="preview" class="branch-preview"><path :d="trunkPath(preview)" /><path v-for="leaf in preview.leaves" :key="leaf.id" :d="twigPath(preview,leaf)" /></g>
          <g v-if="energy.length" class="tree-transit-energy"><g v-for="pulse in energy" :key="pulse.key" :opacity="pulse.opacity"><path :d="pulse.path"/><circle :cx="pulse.head.x" :cy="pulse.head.y" r="2.2"/></g></g>
          </g>
        </svg>
        <button class="tree-base" type="button" aria-label="基座，拖动平移，点击适应整棵平台树" :class="{ receptive: !!preview }" :disabled="disabled" @click="fitBase">
          <svg viewBox="0 0 120 94" aria-hidden="true">
            <defs><mask :id="apertureId" maskUnits="userSpaceOnUse" maskContentUnits="userSpaceOnUse" x="-40" y="-40" width="200" height="200" style="mask-type:luminance"><rect x="-40" y="-40" width="200" height="200" fill="white"/><path d="M0 -9 17 0 0 9 -17 0Z" :transform="`translate(60 39) scale(${exitFrame.aperture})`" fill="black"/></mask></defs>
            <g :mask="exitFrame.aperture>0?`url(#${apertureId})`:undefined"><path class="base-shadow" d="m60 12 48 26v17L60 82 12 55V38z" /><path class="base-side" d="m12 38 48 26 48-26v17L60 82 12 55z" /><path class="base-top" d="m60 12 48 26-48 26-48-26z" /><path class="base-ring" d="m60 24 27 15-27 15-27-15z" /><ellipse class="base-core" cx="60" cy="39" rx="5" ry="3.5" /></g>
            <path v-if="exitFrame.aperture>0" class="base-transit-opening" d="M0 -9 17 0 0 9 -17 0Z" :transform="`translate(60 39) scale(${exitFrame.aperture})`" :opacity="exitFrame.aperture*.6"/>
          </svg>
        </button>
        <div v-for="branch in branches" :key="`${branch.family}:${branch.version}`" class="branch-nodes" :class="{ growing: growing.has(branch.family) }" :style="{ '--branch': accents[branch.family] }">
          <div class="tree-hub" :style="nodeStyle(branch.hub,HUB)" :data-family="branch.family">
            <button class="hub-handle" type="button" :aria-label="`${branch.family}，拖动或方向键调整方向`" :disabled="disabled"
              @pointerdown="begin(branch.family,$event,'hub')" @pointermove="moving" @pointerup="dropped" @pointercancel="cancelGesture" @lostpointercapture="cancelGesture" @click="activate(branch.family,$event)" @keydown="rotate(branch.family,$event)"><PlatformMark :family="branch.family" /><span>{{ branch.family }}</span></button>
            <button class="hub-collapse" type="button" :aria-label="`收起${branch.family}，保留已选平台`" :disabled="disabled" @click="collapse(branch.family)">−</button>
          </div>
          <template v-for="(leaf,i) in branch.leaves" :key="leaf.id">
          <button v-if="categoryMap.has(leaf.id)" class="tree-subgroup" type="button" :class="{ selected: selectedCategory(leaf.id) }"
            :style="{ ...nodeStyle(leaf,LEAF), '--delay': `${900+Math.min(i*90,500)}ms` }" :data-subgroup="categoryMap.get(leaf.id).key"
            :aria-expanded="otherOpen===categoryMap.get(leaf.id).key" aria-controls="other-platform-detail" :disabled="disabled"
            :aria-label="`${categoryMap.get(leaf.id).name}，展开平台${selectedCategory(leaf.id)?'，包含已选平台':''}`" @click="showOther(categoryMap.get(leaf.id).key,0,true)">
            <span class="leaf-face"><span>{{ categoryMap.get(leaf.id).name }}</span><i v-if="selectedCategory(leaf.id)" aria-hidden="true">✓</i><i aria-hidden="true">{{ otherOpen===categoryMap.get(leaf.id).key?'−':'+' }}</i></span>
          </button>
          <label v-else class="tree-leaf" :class="{ selected: selected.includes(leaf.id), dimmed: nodeMap.get(leaf.id) && !matches(nodeMap.get(leaf.id)) }"
            :style="{ ...nodeStyle(leaf,LEAF), '--delay': `${900 + Math.min(i * 90, 500)}ms` }" :title="nodeMap.get(leaf.id)?.name" :data-platform="leaf.id">
            <input type="checkbox" :aria-label="nodeMap.get(leaf.id)?.name || `平台${leaf.id}`" :checked="selected.includes(leaf.id)" :disabled="disabled || (!selected.includes(leaf.id) && selected.length >= 100)" @change.stop="emit('choose',leaf.id,$event.target.checked)" />
            <span class="leaf-face"><PlatformMark :family="branch.family" :name="nodeMap.get(leaf.id)?.name" /><span>{{ nodeMap.get(leaf.id)?.short || `平台${leaf.id}` }}</span><i v-if="selected.includes(leaf.id)" aria-hidden="true">✓</i></span>
          </label>
          </template>
        </div>
        <div v-if="otherCluster" id="other-platform-detail" class="other-detail" :class="{ growing: growing.has('other-detail') }" style="--branch:#9eaebf">
          <div class="other-detail-header" :style="nodeStyle(otherCluster.header,otherCluster.header)">
            <span>{{ openCategory.name }}</span>
            <span class="other-page">{{ currentOtherPage+1 }}/{{ otherPageCount }}</span>
            <button type="button" aria-label="上一页平台" :disabled="disabled || currentOtherPage===0" @click="showOther(otherOpen,currentOtherPage-1)">‹</button>
            <button type="button" aria-label="下一页平台" :disabled="disabled || currentOtherPage+1>=otherPageCount" @click="showOther(otherOpen,currentOtherPage+1)">›</button>
            <button type="button" :aria-label="`收起${openCategory.name}，保留已选平台`" :disabled="disabled" @click="showOther(otherOpen,0,true)">−</button>
          </div>
          <label v-for="(leaf,i) in otherCluster.leaves" :key="`${openCategory.key}:${currentOtherPage}:${leaf.id}`" class="tree-leaf" :class="{ selected: selected.includes(leaf.id), dimmed: nodeMap.get(leaf.id) && !matches(nodeMap.get(leaf.id)) }"
            :style="{ ...nodeStyle(leaf,LEAF), '--delay': `${900+i*90}ms` }" :title="nodeMap.get(leaf.id)?.name" :data-platform="leaf.id">
            <input type="checkbox" :aria-label="nodeMap.get(leaf.id)?.name || `平台${leaf.id}`" :checked="selected.includes(leaf.id)" :disabled="disabled || (!selected.includes(leaf.id) && selected.length>=100)" @change.stop="emit('choose',leaf.id,$event.target.checked)" />
            <span class="leaf-face"><PlatformMark family="其他" /><span>{{ nodeMap.get(leaf.id)?.short || `平台${leaf.id}` }}</span><i v-if="selected.includes(leaf.id)" aria-hidden="true">✓</i></span>
          </label>
        </div>
      </div>
      <div class="tree-controls" aria-label="画布视图"><button type="button" aria-label="缩小平台树" :disabled="disabled" @click="zoomAt(.8)">−</button><button type="button" aria-label="放大平台树" :disabled="disabled" @click="zoomAt(1.25)">+</button><button type="button" :disabled="disabled" @click="fit(branches,true)">适应</button></div>
    </div>
    <div v-if="drag" class="brand-ghost" :class="{ valid: drag.valid }" :style="{ transform: `translate(${drag.x}px,${drag.y}px) translate(-50%,-50%)` }" aria-hidden="true"><PlatformMark :family="drag.family" /><span>{{ drag.family }}</span></div>
    <span class="sr-only" role="status" aria-live="polite">{{ announce }}</span>
  </div>
</template>

<style scoped>
.platform-tree { flex:1;min-height:0;display:grid;grid-template-columns:160px minmax(0,1fr);gap:24px; }
.tree-palette { display:flex;flex-direction:column;gap:12px;overflow-y:auto;padding:8px 4px 16px;scrollbar-width:thin; }
.palette-guide { flex:none;margin:0 0 2px;color:#8c9fb9;font-size:12px;line-height:1.5;text-align:center;user-select:none; }
.brand-module { position:relative;flex:none;display:flex;align-items:center;gap:10px;min-height:64px;padding:12px;background:linear-gradient(145deg,#17202b,#0b1018);border:1px solid #2b3747;color:#a3b3c9;text-align:left;border-radius:12px;cursor:grab;touch-action:none;user-select:none; }
.brand-module :deep(.platform-mark) { width:26px;height:26px; }
.brand-module span { font-size:.9rem; }
.brand-module i { position:absolute;right:8px;top:8px;width:4px;height:4px;border-radius:50%;background:transparent; }
.brand-module.attached i { background:#7796bc; }
.brand-module.has-selection { border-color:#6e8fb8;color:#d5e5fa; }
.tree-viewport { position:relative;min-width:0;min-height:0;overflow:hidden;border-radius:18px;background:radial-gradient(ellipse at 50% 55%,#0c142080,transparent 65%);touch-action:none;cursor:grab; }
.tree-viewport.is-panning,.tree-viewport.is-panning .tree-base { cursor:grabbing; }
.tree-world { position:absolute;left:0;top:0;transform-origin:0 0; }
.tree-wires { position:absolute;overflow:visible;pointer-events:none;fill:none;stroke:#526782;stroke-width:1.4; }
.tree-wires path,.drop-zone { vector-effect:non-scaling-stroke; }
.tree-transit-energy{pointer-events:none;fill:#d8eaff;stroke:none}
.tree-transit-energy path{fill:none;stroke:#bedbff;stroke-width:1.8;stroke-linecap:round;vector-effect:non-scaling-stroke}
.base-transit-opening{fill:none;stroke:#99bde6;stroke-width:.8;vector-effect:non-scaling-stroke;pointer-events:none}
.trunk { stroke:var(--branch);opacity:.45;stroke-width:1.8; }
.twig { stroke:var(--branch);opacity:.25; }
.branch-wires.selected .trunk,.twig.selected { opacity:.85;filter:drop-shadow(0 0 4px #8fb7ed30); }
.drop-zone { stroke:#5079aa;stroke-dasharray:4 10;stroke-width:1;opacity:.35; }
.branch-preview { stroke:#aacdf6;stroke-dasharray:5 6;opacity:.55; }
.tree-base { position:absolute;left:0;top:0;transform:translate(-50%,calc(-50% + 8px));width:116px;height:94px;padding:0;border:0;background:transparent!important;z-index:3;cursor:grab;touch-action:none;user-select:none; }
/* Focus is rendered by focusFeedback.css using the base geometry. */
.tree-base:focus-visible { outline:none;box-shadow:none; }
.tree-base { opacity:var(--tree-base-opacity,1); }
.tree-wires,.branch-nodes,.other-detail { transform:scale(var(--tree-crown-scale,1));transform-origin:0 0;opacity:var(--tree-crown-scale,1); }
.tree-base svg { width:100%;height:100%;overflow:visible; }
.base-shadow { fill:#0a0e15;filter:drop-shadow(0 12px 12px #000); }
.base-side { fill:#101923;stroke:#26364a;stroke-width:1; }
.base-top { fill:#172230;stroke:#3d536e;stroke-width:1; }
.base-ring { fill:none;stroke:#6b92bf;opacity:.45; }
.base-core { fill:#b1d6ff;filter:drop-shadow(0 0 7px #80baff);animation:core-breathe 5s ease-in-out infinite; }
.receptive .base-ring { stroke:#c5e1ff;opacity:1;filter:drop-shadow(0 0 6px #80baff); }
.tree-hub { position:absolute;left:0;top:0;display:flex;align-items:center;border:1px solid #41546b;border-radius:12px;background:#15202df5;box-shadow:0 8px 20px #0008;z-index:4; }
.hub-handle { display:flex;align-items:center;gap:8px;flex:1;min-width:0;height:100%;padding:8px 10px;border:0;background:transparent;color:#c9dbef;cursor:grab;touch-action:none; }
.hub-handle :deep(.platform-mark) { width:24px;height:24px; }
.hub-handle span { font-size:13px;white-space:nowrap; }
.hub-collapse { width:38px;height:100%;padding:0;border:0;border-left:1px solid #2c3b4e;border-radius:0 12px 12px 0;background:transparent;color:#839ab6;font-size:20px; }
.tree-leaf { position:absolute;left:0;top:0;display:block;z-index:5;cursor:pointer; }
.tree-leaf input { position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;z-index:2;cursor:pointer; }
.leaf-face { display:flex;align-items:center;gap:8px;width:100%;height:100%;padding:8px 12px;border:1px solid #2c3c50;border-radius:10px;background:linear-gradient(140deg,#162131,#0c121c);color:#9fb0c8;box-shadow:0 6px 18px #0007; }
.leaf-face :deep(.platform-mark) { width:22px;height:22px; }
.leaf-face > span { flex:1;font-size:13px;line-height:1.25;overflow-wrap:anywhere; }
.leaf-face i { font-size:12px;color:#b9d6fb;font-style:normal; }
.tree-leaf.selected .leaf-face { border-color:var(--branch);color:#e0edff;box-shadow:0 0 16px #8cb7ed19; }
.tree-leaf.dimmed:not(.selected) { opacity:.2; }
.tree-subgroup { position:absolute;left:0;top:0;z-index:5;padding:0;border:0;background:transparent!important; }
.tree-subgroup[aria-expanded=true] .leaf-face,.tree-subgroup.selected .leaf-face { border-color:#8eafd5;color:#dcecff; }
.tree-subgroup:focus-visible { outline:2px solid #c9e2ff;outline-offset:4px; }
.other-detail-header { position:absolute;left:0;top:0;z-index:6;display:flex;align-items:center;gap:4px;padding-left:12px;border:1px solid #42576f;border-radius:10px;background:#152131; }
.other-detail-header > span:first-child { flex:1;font-size:13px; }
.other-page { color:#93a9c5;font-size:12px; }
.other-detail-header button { width:44px;height:42px;min-height:42px;padding:0;border:0;background:transparent;color:#b4c9e3;font-size:20px; }
.tree-leaf input:focus-visible + .leaf-face { outline:2px solid #d0e5ff;outline-offset:3px; }
.tree-controls { position:absolute;right:12px;bottom:12px;display:flex;gap:6px;z-index:10; }
.tree-controls button { min-width:44px;height:44px;padding:0 12px;background:#101824e8;border-color:#2a3a50;color:#aec3df; }
.brand-ghost { position:fixed;left:0;top:0;z-index:60;pointer-events:none;display:flex;align-items:center;gap:10px;padding:12px 18px;border:1px solid #4a5d75;border-radius:12px;background:#152234eb;color:#d3e4f9;box-shadow:0 12px 30px #0009;opacity:.8; }
.brand-ghost.valid { border-color:#a7cffd;opacity:1;box-shadow:0 0 24px #87baff25; }
.brand-ghost :deep(.platform-mark) { width:26px;height:26px; }
.growing .trunk { stroke-dasharray:1;animation:branch-draw 600ms ease-out both; }
.growing .twig { stroke-dasharray:1;animation:branch-draw 500ms ease-out var(--delay) both; }
.growing .tree-leaf,.growing .tree-subgroup { animation:leaf-arrive 300ms ease-out var(--delay) both; }
@keyframes branch-draw { from { stroke-dashoffset:1; } to { stroke-dashoffset:0; } }
@keyframes leaf-arrive { from { opacity:0;visibility:hidden; } to { opacity:1;visibility:visible; } }
@keyframes core-breathe { 0%,100% { opacity:.5; } 50% { opacity:1; } }
@media(max-width:760px) { .platform-tree { grid-template-columns:1fr;grid-template-rows:auto minmax(0,1fr);gap:10px; }.tree-palette { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;overflow:visible;padding:0 2px; }.brand-module { min-height:54px;padding:8px;gap:6px; }.brand-module :deep(.platform-mark) { width:20px;height:20px; }.brand-module span { font-size:.75rem; }.palette-guide { grid-column:1/-1;margin:0;font-size:12px; }.tree-controls { right:4px;bottom:4px; } }
@media(prefers-reduced-motion:reduce) { .base-core,.growing .trunk,.growing .twig,.growing .tree-leaf,.growing .tree-subgroup { animation:none; } }
@media(forced-colors:active) { .tree-base:focus-visible { outline:2px solid Highlight;outline-offset:4px; }.tree-base:focus-visible .base-top,.tree-base:focus-visible .base-side { stroke:Highlight; } .tree-leaf.selected .leaf-face { border:2px solid Highlight; }.tree-wires { stroke:CanvasText; } }
</style>
