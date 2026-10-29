<script setup>
import { computed } from "vue";

const props = defineProps({ score: { type: Number, default: null } });
const hasScore = computed(
  () => Number.isFinite(props.score) && props.score >= 0 && props.score <= 10,
);
const displayScore = computed(() => String(props.score));
</script>

<template>
  <span
    v-if="hasScore"
    class="ign-score-badge"
    role="img"
    :aria-label="`IGN 评分 ${displayScore} / 10`"
  >
    <svg viewBox="0 0 88 100" aria-hidden="true" focusable="false">
      <polygon points="44,2 86,26 86,74 44,98 2,74 2,26" fill="#d3222a" />
      <text
        x="44"
        y="61"
        text-anchor="middle"
        fill="#fff"
        :font-size="displayScore.length > 2 ? 34 : 46"
        font-weight="800"
      >{{ displayScore }}</text>
      <text
        x="44"
        y="80"
        text-anchor="middle"
        fill="#fff"
        font-size="13"
        font-weight="800"
        letter-spacing="1"
      >IGN</text>
    </svg>
  </span>
  <span v-else class="ign-score-missing">暂无评分</span>
</template>

<style scoped>
.ign-score-badge {
  display: inline-flex;
  width: 72px;
  height: 82px;
  flex-shrink: 0;
  vertical-align: middle;
}
.ign-score-badge svg {
  display: block;
  width: 100%;
  height: 100%;
  overflow: visible;
  stroke: none;
  font-family: Arial, Helvetica, sans-serif;
}
.ign-score-missing {
  color: var(--muted);
  font-size: 1rem;
  white-space: nowrap;
}
</style>
