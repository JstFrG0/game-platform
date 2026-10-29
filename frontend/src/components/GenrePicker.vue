<script setup>
import { computed, inject, nextTick, onBeforeUnmount, ref } from 'vue';
import { genreIds } from '../catalog.js';
import { filterSpaceKey } from '../filterSpace.js';
import ConstellationMap from './ConstellationMap.vue';
import { genreLabel } from '../genreConstellations.js';
import { dissolveSearchText } from '../searchDissolve.js';

const props = defineProps({ id: { type: String, default: 'genre' }, modelValue: { type: String, default: '' }, genres: { type: Array, default: () => [] } });
const space = inject(filterSpaceKey, null);
const blocked = computed(() => space?.blocked('genre') ?? false);
const isOpen = () => space ? opened.value : dialog.value?.open;
const tree = ref(null), names = new Map();
const emit = defineEmits(['update:modelValue', 'change']);
const dialog = ref(null), trigger = ref(null), summary = ref(null), transfer = ref(null), searchInput = ref(null);
const opened = ref(false), closing = ref(false), draft = ref([]), query = ref(''), flight = ref(null);
const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
let stopDissolve = () => {};
let animation = null, sequence = 0, overflow, session = 0;
function describe(genre){return {...genre,id:Number(genre.id),name:genre.name||`类型 ${genre.id}`,short:genreLabel(genre)};}
const options = computed(() => {
  for (const genre of props.genres) names.set(Number(genre.id), genre);
  const records = new Map(props.genres.filter(p => Number.isInteger(Number(p.id))).map(p => [Number(p.id), describe(p)]));
  for (const id of [...genreIds(props.modelValue), ...draft.value]) if (!records.has(id)) records.set(id, describe(names.get(id) || { id }));
  return [...records.values()];
});
function caption(ids) {
  if (!ids.length) return '全部类型';
  if (ids.length > 2) return `已选 ${ids.length} 种类型`;
  return ids.map(id => options.value.find(p => p.id === id)?.short || `类型 ${id}`).join('、');
}
const selectedText = computed(() => caption(genreIds(props.modelValue)));
const draftText = computed(() => caption(draft.value));
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
  if (space) return space.enter('genre');
  return begin(true);
}
async function begin(initial) {
  if (isOpen()) return;
  const ticket = ++session, from = bounds(trigger.value);
  draft.value = genreIds(props.modelValue); query.value = '';
  if (!space) { overflow = document.documentElement.style.overflow; document.documentElement.style.overflow = 'hidden'; }
  opened.value = true; closing.value = false; if (!space) dialog.value.showModal();
  await nextTick();
  if (ticket !== session || !isOpen()) return;
  if (initial) await fly(selectedText.value, from, bounds(summary.value), 540);
}
function choose(id, checked) {
  if (blocked.value || (checked && draft.value.length>=100)) return;
  stopTransfer();
  draft.value = checked ? [...new Set([...draft.value, id])].sort((a, b) => a - b) : draft.value.filter(value => value !== id);
}
function all() { if (blocked.value) return; stopTransfer(); draft.value = []; }
async function close(apply, coordinated = false) {
  if (space && !coordinated) return space.close(apply);
  if (closing.value || !isOpen()) return;
  const ticket = ++session, ids = apply ? [...draft.value] : genreIds(props.modelValue), text = caption(ids);
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
  if (apply && value !== genreIds(props.modelValue).join(',')) { emit('update:modelValue', value); emit('change', value); }
}
function clearGenreSearch() {
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
const unregister = space?.register('genre', {
  begin, value: () => draft.value.join(','), busy: () => !!animation || closing.value || !!tree.value?.busy?.(),
  freeze: () => { stopTransfer(); stopDissolve(); tree.value?.freeze(); },
  core: () => tree.value?.core(),
  paint: now => tree.value?.paint?.(now),
  panOffset: () => tree.value?.panOffset(),
  exit: apply => close(apply, true), reset: closed,
  focus: () => tree.value?.focusBase(),
});
onBeforeUnmount(() => { unregister?.(); stopDissolve(); ++session; stopTransfer(); window.removeEventListener('resize', resized); motion.removeEventListener('change', stopTransfer); if (!space && dialog.value?.open) dialog.value.close(); if (overflow !== undefined) document.documentElement.style.overflow = overflow; });
</script>

<template>
  <button :id="id" class="genre-trigger" type="button" aria-haspopup="dialog" :aria-label="`玩法类型：${selectedText}`" :title="selectedText" :aria-expanded="opened" :aria-controls="space ? 'filter-space-dialog' : `${id}-dialog`" @click="open">
    <span ref="trigger" :class="{ travelling: !!flight }">{{ selectedText }}</span>
    <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
  </button>
  <input type="hidden" name="genre_ids" :value="modelValue" />
  <Teleport :to="space ? '#filter-space-genre' : 'body'" defer>
    <component :is="space ? 'div' : 'dialog'" ref="dialog" :id="`${id}-dialog`" class="genre-dialog" :class="{ 'is-closing': closing, 'in-filter-space': !!space }" :aria-labelledby="`${id}-title`" @close="closed" @cancel.prevent="close(false)">
      <div class="genre-shell">
        <header class="genre-header">
          <h2 :id="`${id}-title`">玩法类型</h2>
          <output :title="draftText" ref="summary" :class="{ travelling: !!flight }" aria-live="polite">{{ draftText }}</output>
          <button class="genre-close" type="button" aria-label="关闭类型选择" :disabled="closing || blocked" @click="close(false)">×</button>
        </header>
        <div class="genre-body">
          <div class="genre-tools">
            <button class="genre-all" type="button" :aria-pressed="!draft.length" :disabled="closing || blocked" @click="all">全部类型</button>
            <div v-if="options.length > 0" class="genre-search-entry">
              <input ref="searchInput" class="genre-find" type="search" v-model="query" aria-label="查找类型" placeholder="查找类型" :disabled="closing || blocked" @input="stopDissolve()" />
              <button v-if="query" class="genre-search-clear" type="button" aria-label="清除类型搜索内容" :disabled="closing || blocked" @click="clearGenreSearch"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17" /></svg></button>
            </div>
          </div>
          <ConstellationMap ref="tree" :initial="space?.state.progress===2" :genres="options" :selected="draft" :query="query" :active="opened" :disabled="closing || blocked" @choose="choose" />
        </div>
        <footer class="genre-footer"><button class="genre-cancel" type="button" :disabled="closing || blocked" @click="close(false)">取消</button><button class="primary genre-confirm" type="button" :disabled="closing || blocked" @click="close(true)">确认</button></footer>
      </div>
      <div v-if="flight" ref="transfer" class="genre-transfer" :style="flight.style" aria-hidden="true">{{ flight.text }}</div>
    </component>
  </Teleport>
</template>

<style scoped>
.genre-trigger { display:flex;align-items:center;justify-content:space-between;width:100%;min-width:0;max-width:100%;overflow:hidden;min-height:44px;padding:10px 12px;background:#14181e;border-color:#47515f;text-align:left;user-select:none; }
.genre-trigger > span { flex:1;min-width:0;white-space:nowrap;text-overflow:ellipsis;overflow:hidden; }
.genre-trigger svg { flex:none;width:18px;height:18px;fill:none;stroke:#a8b9d0;stroke-width:1.5; }
.travelling { visibility:hidden; }
.genre-dialog { position:fixed;inset:0;width:100%;height:100dvh;max-width:none;max-height:none;margin:0;padding:0;border:0;border-radius:0;color:#dce6f3;background:transparent;overflow:hidden;user-select:none; }
.genre-dialog::backdrop { background:#000;animation:matrix-black-in 540ms ease both; }
.genre-dialog.is-closing::backdrop { animation:matrix-black-out 720ms ease both; }
.genre-shell { height:100%;min-width:0;display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr) auto; }
.genre-header { min-width:0;position:relative;text-align:center;padding:38px 70px 20px; }
.genre-header h2 { font-size:1.6rem;font-weight:400;letter-spacing:.16em;margin:0 0 12px;color:#c6d4e7; }
.genre-header output { display:inline-block;font-size:1.15rem;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom;min-height:28px;color:#8fa7c4; }
.genre-close { position:absolute;right:26px;top:22px;width:44px;height:44px;min-height:44px;padding:0;font-size:1.8rem;background:transparent;border:0;color:#91a4bd; }
.genre-body { display:flex;flex-direction:column;min-height:0;overflow:hidden;padding:8px 32px 12px; }
.genre-tools { display:flex;flex:none;gap:16px;align-items:center;justify-content:space-between;margin-bottom:18px; }
.genre-all { border-radius:24px;padding:10px 24px;background:#0e131c;border-color:#253244;color:#9caec5; }
.genre-all[aria-pressed=true] { border-color:#6c91bd;color:#d0e2fa;background:#172231; }
.genre-search-entry { position:relative;width:min(280px,50%);min-width:0; }
.genre-find { width:100%;min-width:0;padding-right:42px;background:#0d121a;border-color:#273245; }
.genre-find::-webkit-search-cancel-button { -webkit-appearance:none;appearance:none; }
.genre-search-entry.is-dissolving input::placeholder { color:transparent; }
.genre-search-clear { position:absolute;right:0;top:50%;transform:translateY(-50%);display:grid;place-items:center;width:40px;height:44px;min-height:44px;padding:0;border:0;background:transparent;color:#9caec5; }
.genre-search-clear svg { width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.7; }
.genre-search-clear:hover { color:#e1ebf8; }
.genre-footer { display:flex;justify-content:flex-end;gap:20px;padding:22px 32px 26px;background:linear-gradient(transparent,#000 40%); }
.genre-footer button { min-width:110px; }
.genre-cancel { background:transparent;border-color:transparent;color:#a3b2c8; }
.genre-empty { text-align:center;color:#8d9db4;margin:60px 0; }
.genre-transfer { position:fixed;left:0;top:0;z-index:50;white-space:nowrap;max-width:calc(100vw - 32px);overflow:hidden;text-overflow:ellipsis;pointer-events:none;transform-origin:center;color:#d8e7fa; }
.is-closing .genre-shell { animation:matrix-black-out 380ms ease both;pointer-events:none; }
@keyframes matrix-black-in { from { opacity:0; } to { opacity:1; } }
@keyframes matrix-black-out { from { opacity:1; } to { opacity:0; } }

@media(max-width:760px) { .genre-body { padding-inline:24px; }.genre-header { padding-top:30px; }.genre-footer { padding:18px 20px 22px; } }
@media(max-width:420px) { .genre-body { padding-inline:20px; }.genre-header { padding-inline:55px; }.genre-close { right:8px;top:16px; }.genre-tools { gap:10px; }.genre-all { padding-inline:16px; } }
@media(prefers-reduced-motion:reduce) { .genre-dialog::backdrop,.is-closing .genre-shell { animation:none; } }

</style>
