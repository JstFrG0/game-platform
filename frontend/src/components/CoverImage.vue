<script setup>
import { computed, ref, watch } from "vue";
import { displayCover } from "../api.js";
const props = defineProps({ url: String, name: String, eager: Boolean });
const failed = ref(false);
watch(
  () => props.url,
  () => {
    failed.value = false;
  },
);
const src = computed(() => displayCover(props.url));
</script>

<template>
  <div class="cover-art">
    <img
      v-if="src && !failed"
      :src="src"
      :alt="`${name} 封面`"
      :loading="eager ? 'eager' : 'lazy'"
      decoding="async"
      :draggable="false"
      @error="failed = true"
    />
    <div
      v-else
      class="cover-placeholder"
      role="img"
      :aria-label="`${name} 暂无可用封面`"
    >
      <span aria-hidden="true">G＋</span
      ><span class="cover-message">暂无封面</span>
    </div>
  </div>
</template>
