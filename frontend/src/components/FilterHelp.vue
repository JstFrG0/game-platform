<script setup>
import { onBeforeUnmount, ref } from "vue";
import { filterHelpSections } from "../content/filterHelp.js";

const dialog = ref(null);
let previousOverflow;
function restoreScroll() {
  if (previousOverflow !== undefined) {
    document.documentElement.style.overflow = previousOverflow;
    previousOverflow = undefined;
  }
}
function openHelp() {
  if (dialog.value.open) return;
  previousOverflow = document.documentElement.style.overflow;
  document.documentElement.style.overflow = "hidden";
  dialog.value.showModal();
}
onBeforeUnmount(restoreScroll);
</script>

<template>
  <button
    class="filter-help-trigger"
    type="button"
    aria-haspopup="dialog"
    @click="openHelp"
  >帮助</button>
  <Teleport to="body">
    <dialog
      ref="dialog"
      class="filter-help-dialog"
      aria-labelledby="filter-help-title"
      @close="restoreScroll"
    >
      <header class="filter-help-heading">
        <h2 id="filter-help-title">筛选帮助</h2>
        <button type="button" autofocus @click="dialog.close()">关闭</button>
      </header>
      <div class="filter-help-body" tabindex="0" aria-label="筛选帮助内容">
        <p class="filter-help-intro">筛选只改变显示结果，不会删除游戏记录。</p>
        <details
          v-for="(section, index) in filterHelpSections"
          :key="section.title"
          :open="index === 0"
        >
          <summary>{{ section.title }}</summary>
          <div class="filter-help-section">
            <p v-if="section.intro">{{ section.intro }}</p>
            <dl>
              <div v-for="[label, description] in section.entries" :key="label">
                <dt>{{ label }}</dt>
                <dd>{{ description }}</dd>
              </div>
            </dl>
            <p v-if="section.note">{{ section.note }}</p>
          </div>
        </details>
      </div>
    </dialog>
  </Teleport>
</template>

<style scoped>
.filter-help-trigger {
  padding: 4px 6px;
  border-color: transparent;
  background: transparent;
  color: var(--blue);
  font-size: 1rem;
  white-space: nowrap;
}
.filter-help-dialog {
  margin: auto;
  padding: 0;
  width: min(800px, calc(100% - 32px));
  max-width: none;
  max-height: 85vh;
  max-height: 85dvh;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #181c23;
  color: #edf0f5;
  overflow: hidden;
}
.filter-help-dialog[open] {
  display: flex;
  flex-direction: column;
}
.filter-help-dialog::backdrop {
  background: rgb(0 0 0 / 65%);
}
.filter-help-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.filter-help-heading h2 {
  font-size: 1.25rem;
  font-weight: 600;
}
.filter-help-body {
  padding: 24px;
  overflow-y: auto;
  min-height: 0;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  font-size: 1rem;
  line-height: 1.8;
}
.filter-help-intro {
  margin-bottom: 20px;
}
.filter-help-body details {
  border-top: 1px solid var(--border);
}
.filter-help-body summary {
  padding-block: 14px;
  cursor: pointer;
  color: var(--blue);
  font-weight: 600;
}
.filter-help-section {
  padding-bottom: 20px;
}
.filter-help-section dl > div {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
  gap: 12px 24px;
  padding-block: 12px;
}
.filter-help-section dt {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.filter-help-section dd {
  color: #c2cbd8;
  overflow-wrap: anywhere;
}
.filter-help-section dl + p {
  margin-top: 12px;
}
@media (max-width: 600px) {
  .filter-help-heading,
  .filter-help-body {
    padding: 16px;
  }
  .filter-help-section dl > div {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
  }
}
</style>
