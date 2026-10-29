<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  currentPage: { type: Number, required: true },
  totalPages: { type: Number, required: true },
});
const emit = defineEmits(["jump"]);
const page = ref("");
watch(
  () => [props.currentPage, props.totalPages],
  () => { page.value = ""; },
  { immediate: true },
);
function jump() {
  const target = Number(page.value);
  if (Number.isSafeInteger(target) && target >= 1 && target <= props.totalPages) {
    page.value = "";
    if (target !== props.currentPage) emit("jump", target);
  }
}
</script>

<template>
  <form v-if="totalPages > 1" class="page-jump" method="get" action="#/" aria-label="跳转到指定页" @submit.prevent="jump">
    <label for="jump-page">跳至</label>
    <input
      id="jump-page"
      name="page"
      v-model="page"
      type="number"
      inputmode="numeric"
      enterkeyhint="go"
      min="1"
      :max="totalPages"
      step="1"
      required
      autocomplete="off"
      placeholder="页码"
      aria-label="跳至页码"
      aria-describedby="jump-page-range"
    />
    <span id="jump-page-range" class="sr-only">输入 1 至 {{ totalPages }} 之间的整数页码，按 Enter 跳转。</span>
  </form>
</template>

<style scoped>
.page-jump {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  border-inline-start: 1px solid var(--border);
  padding-inline-start: 16px;
}
.page-jump input {
  width: 5rem;
  height: 40px;
  min-height: 40px;
  padding-inline: 8px;
  text-align: center;
  background: transparent;
}
.page-jump label {
  white-space: nowrap;
}
@media (max-width: 600px) {
  .page-jump {
    border-inline-start: 0;
    padding-inline-start: 0;
  }
}
</style>
