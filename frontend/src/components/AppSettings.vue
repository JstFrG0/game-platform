<script setup>
import { onBeforeUnmount, ref } from 'vue';
import { filterPreferences } from '../filterMotion.js';

const dialog = ref(null), opened = ref(false);
const { simplified } = filterPreferences;
const nativeCommands = 'commandForElement' in HTMLButtonElement.prototype;
function open() {
  opened.value = true;
  if (!nativeCommands) dialog.value.showModal();
}
function close() { if (!nativeCommands) dialog.value.close(); }
function backdrop(event) {
  if (event.target !== dialog.value) return;
  const rect = dialog.value.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.value.close();
}
onBeforeUnmount(() => { if (dialog.value?.open) dialog.value.close(); });
</script>

<template>
  <button class="settings-trigger" type="button" commandfor="app-settings" command="show-modal"
    aria-label="打开设置" aria-haspopup="dialog" aria-controls="app-settings" :aria-expanded="opened" @click="open">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9.5 3-.6 2.3-1.7 1L5 5.7 2.5 10l1.7 1.7v2L2.5 15.4 5 19.7l2.2-.6 1.7 1 .6 2.3h5l.6-2.3 1.7-1 2.2.6 2.5-4.3-1.7-1.7v-2l1.7-1.7L19 5.7l-2.2.6-1.7-1L14.5 3Z" transform="translate(0 -1) scale(1 .96)"/><circle cx="12" cy="11.7" r="3.1"/></svg>
    <span>设置</span>
  </button>
  <Teleport to="body">
    <dialog ref="dialog" id="app-settings" class="settings-dialog" aria-labelledby="settings-title"
      @close="opened = false" @click="backdrop">
      <header class="settings-heading">
        <h2 id="settings-title">设置</h2>
        <button class="settings-close" type="button" commandfor="app-settings" command="close" aria-label="关闭设置" autofocus @click="close">×</button>
      </header>
      <label class="settings-option">
        <span class="settings-option-copy"><span id="settings-filter-motion-title" class="settings-option-title">简化筛选动画</span>
          <span id="filter-motion-description">跳过筛选入场、页面转场和选择特效，更快找到游戏。</span></span>
        <input class="settings-switch" type="checkbox" role="switch" :checked="simplified"
          aria-labelledby="settings-filter-motion-title" aria-describedby="filter-motion-description" @change="filterPreferences.setSimplified($event.target.checked)" />
      </label>
    </dialog>
  </Teleport>
</template>

<style scoped>
.settings-trigger{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:36px;padding:7px 11px;background:transparent;border-color:#38414e;color:#b9c4d4;font-size:.82rem;white-space:nowrap}
.settings-trigger svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.4;stroke-linejoin:round}
.settings-trigger:hover{color:#edf3ff;border-color:#62758f}
.settings-dialog{width:min(440px,calc(100vw - 32px));max-height:calc(100dvh - 48px);padding:24px;border:1px solid #3a4554;border-radius:16px;background:#191e26;color:#edf0f5;box-shadow:0 24px 80px #0008;-webkit-user-select:none;user-select:none}
.settings-dialog::backdrop{background:#06090fb3}
.settings-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:24px}
.settings-heading h2{margin:0;font-size:1.15rem;font-weight:600}
.settings-close{display:flex;align-items:center;justify-content:center;min-width:36px;min-height:36px;padding:0;border-color:transparent;background:transparent;font-size:24px;line-height:1;color:#a5b2c4}
.settings-option{display:flex;align-items:center;gap:24px;padding:18px 16px;border:1px solid #333e4d;border-radius:11px;background:#12171e;cursor:pointer}
.settings-option-copy{display:flex;flex-direction:column;gap:9px;min-width:0;font-size:.8rem;line-height:1.7;color:#99a6ba}
.settings-option-title{font-size:.94rem;font-weight:500;color:#e2eaf7}
.settings-switch{appearance:none;position:relative;flex:none;width:44px;height:26px;min-height:26px;margin:0;padding:0;border:1px solid #515f72;border-radius:999px;background:#313b49;cursor:pointer}
.settings-switch::before{content:"";position:absolute;top:4px;left:4px;width:16px;height:16px;border-radius:50%;background:#c5ceda}
.settings-switch:checked{background:#497aa7;border-color:#88b7e3}
.settings-switch:checked::before{transform:translateX(18px);background:#f3f8ff}
.settings-switch:focus-visible{outline:2px solid #9fcaff;outline-offset:4px}
@media(max-width:520px){.settings-dialog{padding:20px}.settings-option{gap:16px}}
</style>
