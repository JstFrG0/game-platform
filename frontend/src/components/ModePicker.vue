<script setup>
import { filterMotion } from '../filterMotion.js';
import { computed, inject, nextTick, onBeforeUnmount, ref } from 'vue';
import { modeIds } from '../catalog.js';
import { filterSpaceKey } from '../filterSpace.js';
import ModeRelay from './ModeRelay.vue';
import { describeModes, modeCaption } from '../modeRelay.js';

const props = defineProps({ id: { type: String, default: 'mode' }, modelValue: { type: String, default: '' }, modes: { type: Array, default: () => [] } });
const space = inject(filterSpaceKey, null);
const blocked = computed(() => space?.blocked('mode') ?? false);
const isOpen = () => space ? opened.value : dialog.value?.open;
const tree = ref(null);
const emit = defineEmits(['update:modelValue', 'change']);
const dialog = ref(null), trigger = ref(null), summary = ref(null), transfer = ref(null);
const opened = ref(false), closing = ref(false), draft = ref([]), flight = ref(null);
const motion = filterMotion;
let animation = null, sequence = 0, overflow, session = 0;
const options = computed(() => describeModes(props.modes, [...modeIds(props.modelValue), ...draft.value]));
function caption(ids) { return modeCaption(ids, options.value); }
const selectedText = computed(() => caption(modeIds(props.modelValue)));
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
  if (space) return space.enter('mode');
  return begin(true);
}
async function begin(initial) {
  if (isOpen()) return;
  const ticket = ++session, from = bounds(trigger.value);
  draft.value = modeIds(props.modelValue);
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
  const ticket = ++session, ids = apply ? [...draft.value] : modeIds(props.modelValue), text = caption(ids);
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
  if (apply && value !== modeIds(props.modelValue).join(',')) { emit('update:modelValue', value); emit('change', value); }
}
function closed() {
  ++session; stopTransfer(); opened.value = false; closing.value = false;
  if (overflow !== undefined) { document.documentElement.style.overflow = overflow; overflow = undefined; }
}
function resized() { stopTransfer(); }
window.addEventListener('resize', resized);
motion.addEventListener('change', stopTransfer);
const unregister = space?.register('mode', {
  begin, value: () => draft.value.join(','), busy: () => !!animation || closing.value || !!tree.value?.busy?.(),
  freeze: () => { stopTransfer(); tree.value?.freeze(); },
  core: () => tree.value?.core(),
  paint: now => tree.value?.paint?.(now),
  panOffset: () => tree.value?.panOffset(),
  exit: apply => close(apply, true), reset: closed,
  focus: () => tree.value?.focusBase(),
});
onBeforeUnmount(() => { unregister?.(); ++session; stopTransfer(); window.removeEventListener('resize', resized); motion.removeEventListener('change', stopTransfer); if (!space && dialog.value?.open) dialog.value.close(); if (overflow !== undefined) document.documentElement.style.overflow = overflow; });
</script>

<template>
  <button :id="id" class="mode-trigger" type="button" aria-haspopup="dialog" :aria-label="`游玩模式：${selectedText}`" :title="selectedText" :aria-expanded="opened" :aria-controls="space ? 'filter-space-dialog' : `${id}-dialog`" @click="open">
    <span ref="trigger" :class="{ travelling: !!flight }">{{ selectedText }}</span>
    <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
  </button>
  <input type="hidden" name="mode_ids" :value="modelValue" />
  <Teleport :to="space ? '#filter-space-mode' : 'body'" defer>
    <component :is="space ? 'div' : 'dialog'" ref="dialog" :id="`${id}-dialog`" class="mode-dialog" :class="{ 'is-closing': closing, 'in-filter-space': !!space }" :aria-labelledby="`${id}-title`" @close="closed" @cancel.prevent="close(false)">
      <div class="mode-shell">
        <header class="mode-header">
          <h2 :id="`${id}-title`">游玩模式</h2>
          <output :title="draftText" ref="summary" :class="{ travelling: !!flight }" aria-live="polite">{{ draftText }}</output>
          <button class="mode-close" type="button" aria-label="关闭模式选择" :disabled="closing || blocked" @click="close(false)">×</button>
        </header>
        <div class="mode-body">
          <div class="mode-tools">
            <button class="mode-all" type="button" :aria-pressed="!draft.length" :disabled="closing || blocked" @click="all">全部模式</button>

          </div>
          <ModeRelay ref="tree" :initial="space?.state.progress===3" :modes="options" :selected="draft" :active="opened" :disabled="closing || blocked" @choose="choose" />
        </div>
        <footer class="mode-footer"><button class="mode-cancel" type="button" :disabled="closing || blocked" @click="close(false)">取消</button><button class="primary mode-confirm" type="button" :disabled="closing || blocked" @click="close(true)">确认</button></footer>
      </div>
      <div v-if="flight" ref="transfer" class="mode-transfer" :style="flight.style" aria-hidden="true">{{ flight.text }}</div>
    </component>
  </Teleport>
</template>

<style scoped>
.mode-trigger { display:flex;align-items:center;justify-content:space-between;width:100%;min-width:0;max-width:100%;overflow:hidden;min-height:44px;padding:10px 12px;background:#14181e;border-color:#47515f;text-align:left;user-select:none; }
.mode-trigger > span { flex:1;min-width:0;white-space:nowrap;text-overflow:ellipsis;overflow:hidden; }
.mode-trigger svg { flex:none;width:18px;height:18px;fill:none;stroke:#a8b9d0;stroke-width:1.5; }
.travelling { visibility:hidden; }
.mode-dialog { position:fixed;inset:0;width:100%;height:100dvh;max-width:none;max-height:none;margin:0;padding:0;border:0;border-radius:0;color:#dce6f3;background:transparent;overflow:hidden;user-select:none; }
.mode-dialog::backdrop { background:#000;animation:matrix-black-in 540ms ease both; }
.mode-dialog.is-closing::backdrop { animation:matrix-black-out 720ms ease both; }
.mode-shell { height:100%;min-width:0;display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr) auto; }
.mode-header { min-width:0;position:relative;text-align:center;padding:38px 70px 20px; }
.mode-header h2 { font-size:1.6rem;font-weight:400;letter-spacing:.16em;margin:0 0 12px;color:#c6d4e7; }
.mode-header output { display:inline-block;font-size:1.15rem;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom;min-height:28px;color:#8fa7c4; }
.mode-close { position:absolute;right:26px;top:22px;width:44px;height:44px;min-height:44px;padding:0;font-size:1.8rem;background:transparent;border:0;color:#91a4bd; }
.mode-body { display:flex;flex-direction:column;min-height:0;overflow:hidden;padding:8px 32px 12px; }
.mode-tools { display:flex;flex:none;gap:16px;align-items:center;justify-content:space-between;margin-bottom:18px; }
.mode-all { border-radius:24px;padding:10px 24px;background:#0e131c;border-color:#253244;color:#9caec5; }
.mode-all[aria-pressed=true] { border-color:#6c91bd;color:#d0e2fa;background:#172231; }
.mode-footer { display:flex;justify-content:flex-end;gap:20px;padding:22px 32px 26px;background:linear-gradient(transparent,#000 40%); }
.mode-footer button { min-width:110px; }
.mode-cancel { background:transparent;border-color:transparent;color:#a3b2c8; }
.mode-empty { text-align:center;color:#8d9db4;margin:60px 0; }
.mode-transfer { position:fixed;left:0;top:0;z-index:50;white-space:nowrap;max-width:calc(100vw - 32px);overflow:hidden;text-overflow:ellipsis;pointer-events:none;transform-origin:center;color:#d8e7fa; }
.is-closing .mode-shell { animation:matrix-black-out 380ms ease both;pointer-events:none; }
@keyframes matrix-black-in { from { opacity:0; } to { opacity:1; } }
@keyframes matrix-black-out { from { opacity:1; } to { opacity:0; } }

@media(max-width:760px) { .mode-body { padding-inline:24px; }.mode-header { padding-top:30px; }.mode-footer { padding:18px 20px 22px; } }
@media(max-width:420px) { .mode-body { padding-inline:20px; }.mode-header { padding-inline:55px; }.mode-close { right:8px;top:16px; }.mode-tools { gap:10px; }.mode-all { padding-inline:16px; } }
@media(prefers-reduced-motion:reduce) { .mode-dialog::backdrop,.is-closing .mode-shell { animation:none; } }

</style>
