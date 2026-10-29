<script setup>
import { computed, inject, nextTick, onBeforeUnmount, ref } from 'vue';
import { platformIds } from '../catalog.js';
import { filterSpaceKey } from '../filterSpace.js';
import PlatformTree from './PlatformTree.vue';
import { dissolveSearchText } from '../searchDissolve.js';

const props = defineProps({ id: { type: String, default: 'platform' }, modelValue: { type: String, default: '' }, platforms: { type: Array, default: () => [] } });
const space = inject(filterSpaceKey, null);
const blocked = computed(() => space?.blocked('platform') ?? false);
const isOpen = () => space ? opened.value : dialog.value?.open;
const tree = ref(null), names = new Map();
const emit = defineEmits(['update:modelValue', 'change']);
const dialog = ref(null), trigger = ref(null), summary = ref(null), transfer = ref(null), searchInput = ref(null);
const opened = ref(false), closing = ref(false), draft = ref([]), query = ref(''), flight = ref(null);
const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
let stopDissolve = () => {};
let animation = null, sequence = 0, overflow, session = 0;
const families = ['PC', 'PlayStation', 'Xbox', 'Nintendo', '移动设备', '其他'];
function describe(platform) {
  const name = platform.name || `平台 ${platform.id}`;
  let family = '其他';
  if (/windows|linux|macintosh|^mac$|macos|pc \(/i.test(name)) family = 'PC';
  else if (/playstation|^ps[1-5](\b|$)|psp|ps vita/i.test(name)) family = 'PlayStation';
  else if (/xbox/i.test(name)) family = 'Xbox';
  else if (/nintendo|game boy|gamecube|wii|super famicom|^nes$|^snes$/i.test(name)) family = 'Nintendo';
  else if (/android|ios|ipad|iphone/i.test(name)) family = '移动设备';
  const short = name.replace(/^PC \(Microsoft Windows\)$/i, 'Windows').replace(/^PlayStation Portable$/i, 'PSP').replace(/^PlayStation Vita$/i, 'PS Vita').replace(/^PlayStation /i, 'PS').replace(/^Nintendo /i, '');
  return { ...platform, id: Number(platform.id), name, short, family };
}
const options = computed(() => {
  for (const platform of props.platforms) names.set(Number(platform.id), platform);
  const records = new Map(props.platforms.filter(p => Number.isInteger(Number(p.id))).map(p => [Number(p.id), describe(p)]));
  for (const id of [...platformIds(props.modelValue), ...draft.value]) if (!records.has(id)) records.set(id, describe(names.get(id) || { id }));
  return [...records.values()];
});
function caption(ids) {
  if (!ids.length) return '全部平台';
  if (ids.length > 2) return `已选 ${ids.length} 个平台`;
  return ids.map(id => options.value.find(p => p.id === id)?.short || `平台 ${id}`).join('、');
}
const selectedText = computed(() => caption(platformIds(props.modelValue)));
const draftText = computed(() => caption(draft.value));
const groups = computed(() => families.map(family => ({ family, platforms: options.value
  .filter(p => p.family === family)
  .sort((a, b) => a.short.localeCompare(b.short, 'zh-CN')) })).filter(g => g.platforms.length));
function bounds(node) {
  const range = document.createRange(); range.selectNodeContents(node);
  const box = range.getBoundingClientRect(), visible = node.getBoundingClientRect(), style = getComputedStyle(node);
  return { x: visible.x + Math.min(box.width, visible.width) / 2, y: box.y + box.height / 2, font: parseFloat(style.fontSize), width: visible.width };
}
function stopTransfer() {
  ++sequence; animation?.cancel(); animation = null; flight.value = null;
}
async function fly(text, from, to, duration, returning = false) {
  stopTransfer();
  if (motion.matches || !from || !to) return;
  const token = sequence;
  const transform = (point, turn = 0) => `translate(${point.x}px, ${point.y}px) translate(-50%, -50%) scale(${point.font / to.font}) perspective(800px) rotateY(${turn}deg)`;
  flight.value = { text, style: { fontSize: `${to.font}px`, maxWidth: `${from.width || 300}px`, transform: transform(from) } };
  await nextTick();
  if (token !== sequence || !transfer.value) return;
  animation = transfer.value.animate([{ transform: transform(from), maxWidth: `${from.width || 300}px` }, { transform: transform(to, returning ? 360 : 0), maxWidth: `${to.width || 300}px` }], { duration, easing: 'cubic-bezier(.4,0,.2,1)', fill: 'forwards' });
  await animation.finished.catch(() => {});
  if (token === sequence) { animation = null; flight.value = null; }
}
async function open() {
  if (space) return space.enter('platform');
  return begin(true);
}
async function begin(initial) {
  if (isOpen()) return;
  const ticket = ++session, from = bounds(trigger.value);
  draft.value = platformIds(props.modelValue); query.value = '';
  if (!space) { overflow = document.documentElement.style.overflow; document.documentElement.style.overflow = 'hidden'; }
  opened.value = true; closing.value = false; if (!space) dialog.value.showModal();
  await nextTick();
  if (ticket !== session || !isOpen()) return;
  if (initial) await fly(selectedText.value, from, bounds(summary.value), 540);
}
function choose(id, checked) {
  if (blocked.value) return;
  stopTransfer();
  draft.value = checked ? [...new Set([...draft.value, id])].sort((a, b) => a - b) : draft.value.filter(value => value !== id);
}
function all() { if (blocked.value) return; stopTransfer(); draft.value = []; }
async function close(apply, coordinated = false) {
  if (space && !coordinated) return space.close(apply);
  if (closing.value || !isOpen()) return;
  const ticket = ++session, ids = apply ? [...draft.value] : platformIds(props.modelValue), text = caption(ids);
  stopTransfer();
  closing.value = true;
  const from = bounds(summary.value), rect = trigger.value.getBoundingClientRect(), style = getComputedStyle(trigger.value);
  const canvas = document.createElement('canvas'), context = canvas.getContext('2d');
  if (context) context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  const width = Math.min(rect.width, context ? context.measureText(text).width : rect.width);
  await fly(text, from, { x: rect.x + width / 2, y: rect.y + rect.height / 2, font: parseFloat(style.fontSize), width: rect.width }, 720, true);
  if (ticket !== session) return;
  if (space) return;
  dialog.value.close();
  const value = ids.join(',');
  if (apply && value !== platformIds(props.modelValue).join(',')) { emit('update:modelValue', value); emit('change', value); }
}
function clearPlatformSearch() {
  stopDissolve();
  try { stopDissolve = dissolveSearchText(searchInput.value); } catch { stopDissolve = () => {}; }
  query.value = '';
  searchInput.value?.focus({ preventScroll: true });
}
function closed() {
  stopDissolve();
  ++session; stopTransfer(); opened.value = false; closing.value = false;
  if (overflow !== undefined) { document.documentElement.style.overflow = overflow; overflow = undefined; }
}
function resized() { stopTransfer(); }
window.addEventListener('resize', resized);
motion.addEventListener('change', stopTransfer);
const unregister = space?.register('platform', {
  begin, value: () => draft.value.join(','), busy: () => !!animation || closing.value,
  freeze: () => { stopTransfer(); stopDissolve(); tree.value?.freeze(); },
  core: () => tree.value?.core(),
  transit: () => tree.value?.transit?.(),
  panOffset: () => tree.value?.panOffset(),
  exit: apply => close(apply, true), reset: closed,
  focus: () => tree.value?.focusBase(),
});
onBeforeUnmount(() => { unregister?.(); stopDissolve(); ++session; stopTransfer(); window.removeEventListener('resize', resized); motion.removeEventListener('change', stopTransfer); if (!space && dialog.value?.open) dialog.value.close(); if (overflow !== undefined) document.documentElement.style.overflow = overflow; });
</script>

<template>
  <button :id="id" class="platform-trigger" type="button" aria-haspopup="dialog" :aria-label="`游戏平台：${selectedText}`" :title="selectedText" :aria-expanded="opened" :aria-controls="space ? 'filter-space-dialog' : `${id}-dialog`" @click="open">
    <span ref="trigger" :class="{ travelling: !!flight }">{{ selectedText }}</span>
    <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
  </button>
  <input type="hidden" name="platform_ids" :value="modelValue" />
  <Teleport :to="space ? '#filter-space-platform' : 'body'" defer>
    <component :is="space ? 'div' : 'dialog'" ref="dialog" :id="`${id}-dialog`" class="platform-dialog" :class="{ 'is-closing': closing, 'in-filter-space': !!space }" :aria-labelledby="`${id}-title`" @close="closed" @cancel.prevent="close(false)">
      <div class="platform-shell">
        <header class="platform-header">
          <h2 :id="`${id}-title`">游戏平台</h2>
          <output :title="draftText" ref="summary" :class="{ travelling: !!flight }" aria-live="polite">{{ draftText }}</output>
          <button class="platform-close" type="button" aria-label="关闭平台选择" :disabled="closing || blocked" @click="close(false)">×</button>
        </header>
        <div class="platform-body">
          <div class="platform-tools">
            <button class="platform-all" type="button" :aria-pressed="!draft.length" :disabled="closing || blocked" @click="all">全部平台</button>
            <div v-if="options.length > 18" class="platform-search-entry">
              <input ref="searchInput" class="platform-find" type="search" v-model="query" aria-label="查找平台" placeholder="查找平台" :disabled="closing || blocked" @input="stopDissolve()" />
              <button v-if="query" class="platform-search-clear" type="button" aria-label="清除平台搜索内容" :disabled="closing || blocked" @click="clearPlatformSearch"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17" /></svg></button>
            </div>
          </div>
          <PlatformTree ref="tree" :wheel-navigation="!!space" :groups="groups" :selected="draft" :query="query" :active="opened" :disabled="closing || blocked" @choose="choose" />
        </div>
        <footer class="platform-footer"><button class="platform-cancel" type="button" :disabled="closing || blocked" @click="close(false)">取消</button><button class="primary platform-confirm" type="button" :disabled="closing || blocked" @click="close(true)">确认</button></footer>
      </div>
      <div v-if="flight" ref="transfer" class="platform-transfer" :style="flight.style" aria-hidden="true">{{ flight.text }}</div>
    </component>
  </Teleport>
</template>

<style scoped>
.platform-trigger { display:flex;align-items:center;justify-content:space-between;width:100%;min-width:0;max-width:100%;overflow:hidden;min-height:44px;padding:10px 12px;background:#14181e;border-color:#47515f;text-align:left;user-select:none; }
.platform-trigger > span { flex:1;min-width:0;white-space:nowrap;text-overflow:ellipsis;overflow:hidden; }
.platform-trigger svg { flex:none;width:18px;height:18px;fill:none;stroke:#a8b9d0;stroke-width:1.5; }
.travelling { visibility:hidden; }
.platform-dialog { position:fixed;inset:0;width:100%;height:100dvh;max-width:none;max-height:none;margin:0;padding:0;border:0;border-radius:0;color:#dce6f3;background:transparent;overflow:hidden;user-select:none; }
.platform-dialog::backdrop { background:#000;animation:matrix-black-in 540ms ease both; }
.platform-dialog.is-closing::backdrop { animation:matrix-black-out 720ms ease both; }
.platform-shell { height:100%;min-width:0;display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr) auto; }
.platform-header { min-width:0;position:relative;text-align:center;padding:38px 70px 20px; }
.platform-header h2 { font-size:1.6rem;font-weight:400;letter-spacing:.16em;margin:0 0 12px;color:#c6d4e7; }
.platform-header output { display:inline-block;font-size:1.15rem;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom;min-height:28px;color:#8fa7c4; }
.platform-close { position:absolute;right:26px;top:22px;width:44px;height:44px;min-height:44px;padding:0;font-size:1.8rem;background:transparent;border:0;color:#91a4bd; }
.platform-body { display:flex;flex-direction:column;min-height:0;overflow:hidden;padding:8px 32px 12px; }
.platform-tools { display:flex;flex:none;gap:16px;align-items:center;justify-content:space-between;margin-bottom:18px; }
.platform-all { border-radius:24px;padding:10px 24px;background:#0e131c;border-color:#253244;color:#9caec5; }
.platform-all[aria-pressed=true] { border-color:#6c91bd;color:#d0e2fa;background:#172231; }
.platform-search-entry { position:relative;width:min(280px,50%);min-width:0; }
.platform-find { width:100%;min-width:0;padding-right:42px;background:#0d121a;border-color:#273245; }
.platform-find::-webkit-search-cancel-button { -webkit-appearance:none;appearance:none; }
.platform-search-entry.is-dissolving input::placeholder { color:transparent; }
.platform-search-clear { position:absolute;right:0;top:50%;transform:translateY(-50%);display:grid;place-items:center;width:40px;height:44px;min-height:44px;padding:0;border:0;background:transparent;color:#9caec5; }
.platform-search-clear svg { width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.7; }
.platform-search-clear:hover { color:#e1ebf8; }
.platform-footer { display:flex;justify-content:flex-end;gap:20px;padding:22px 32px 26px;background:linear-gradient(transparent,#000 40%); }
.platform-footer button { min-width:110px; }
.platform-cancel { background:transparent;border-color:transparent;color:#a3b2c8; }
.platform-empty { text-align:center;color:#8d9db4;margin:60px 0; }
.platform-transfer { position:fixed;left:0;top:0;z-index:50;white-space:nowrap;max-width:calc(100vw - 32px);overflow:hidden;text-overflow:ellipsis;pointer-events:none;transform-origin:center;color:#d8e7fa; }
.is-closing .platform-shell { animation:matrix-black-out 380ms ease both;pointer-events:none; }
@keyframes matrix-black-in { from { opacity:0; } to { opacity:1; } }
@keyframes matrix-black-out { from { opacity:1; } to { opacity:0; } }

@media(max-width:760px) { .platform-body { padding-inline:24px; }.platform-header { padding-top:30px; }.platform-footer { padding:18px 20px 22px; } }
@media(max-width:420px) { .platform-body { padding-inline:20px; }.platform-header { padding-inline:55px; }.platform-close { right:8px;top:16px; }.platform-tools { gap:10px; }.platform-all { padding-inline:16px; } }
@media(prefers-reduced-motion:reduce) { .platform-dialog::backdrop,.is-closing .platform-shell { animation:none; } }

</style>
