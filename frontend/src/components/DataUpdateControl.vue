<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { catalogDataVersion } from "../dataVersion.js";
import { busyUpdateStates, shouldRefreshCatalog, updateStatusLabel, updateStatusText, updateStatusTone } from "../dataUpdateStatus.js";
import { loadFilterOptions } from "../filterOptions.js";

const state = ref({ status: "loading", enabled: false });
const pending = ref(false);
const connectionError = ref("");
const busy = computed(() => pending.value || busyUpdateStates.has(state.value.status));
const message = computed(() => pending.value ? updateStatusText({ status: "checking" })
  : connectionError.value || state.value.error || updateStatusText(state.value));
const presentation = computed(() => ({
  status: pending.value ? "checking" : connectionError.value ? "failed" : state.value.status,
}));
const label = computed(() => updateStatusLabel(presentation.value));
const tone = computed(() => updateStatusTone(presentation.value));
const description = computed(() => {
  const version = state.value.version;
  const date = version ? new Date(version) : null;
  const minutes = Math.round((state.value.interval_seconds || 21600) / 60);
  const interval = minutes % 60 === 0 ? `${minutes / 60}小时` : `${minutes}分钟`;
  return date && Number.isFinite(date.valueOf())
    ? `数据版本：${date.toLocaleString("zh-CN")}。启动时自动检查，此后每${interval}检查。`
    : "启动时自动检查游戏资料更新。";
});
let controller, timer, stopped = false;

async function poll(manual = false) {
  clearTimeout(timer);
  controller?.abort();
  const current = (controller = new AbortController());
  const timeout = setTimeout(() => current.abort(), 15000);
  pending.value = manual;
  try {
    const response = await fetch(`/api/v1/data-updates${manual ? "/check" : ""}`, {
      method: manual ? "POST" : "GET",
      signal: current.signal,
      cache: "no-store",
      priority: manual ? "auto" : "low",
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value.detail?.message || "暂时无法检查更新。");
    if (stopped || controller !== current) return;
    state.value = value;
    connectionError.value = "";
    if (Object.hasOwn(value, "version")) {
      if (shouldRefreshCatalog(catalogDataVersion.value, value.version)) loadFilterOptions.invalidate();
      catalogDataVersion.value = value.version;
    }
  } catch (error) {
    if (!stopped && controller === current) {
      connectionError.value = error.name === "AbortError"
        ? "更新状态请求超时，请稍后重试。"
        : error.message === "Failed to fetch"
          ? "暂时无法连接更新服务。"
          : error.message;
    }
  } finally {
    clearTimeout(timeout);
    if (!stopped && controller === current) {
      pending.value = false;
      const interval = document.hidden ? 60000 : busyUpdateStates.has(state.value.status) ? 1500 : 30000;
      timer = setTimeout(() => poll(), interval);
    }
  }
}

function resume() {
  if (!document.hidden && !pending.value) poll();
}
onMounted(() => {
  poll();
  document.addEventListener("visibilitychange", resume);
});
onBeforeUnmount(() => {
  stopped = true;
  clearTimeout(timer);
  controller?.abort();
  document.removeEventListener("visibilitychange", resume);
});
</script>

<template>
  <div class="data-update-control" :title="`${message}\n${description}`">
    <span id="data-update-status" class="data-update-pill" role="status" aria-live="polite" aria-atomic="true"
      :class="`is-${tone}`" :aria-label="message">
      <svg v-if="tone === 'warning'" class="status-warning" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="8" cy="8" r="5.75" /><path d="M8 4.6v3.7M8 10.8h.01" />
      </svg>
      <span v-else-if="tone === 'busy'" class="status-spinner" aria-hidden="true"></span>
      <span v-else class="status-dot" aria-hidden="true"></span>
      <span>{{ label }}</span>
    </span>
    <button type="button" class="data-update-button" :disabled="busy || !state.enabled"
      aria-describedby="data-update-status" @click="poll(true)">{{ busy ? "更新处理中…" : "检查更新" }}</button>
  </div>
</template>

<style scoped>
.data-update-control {
  margin-left: auto; display: flex; align-items: center; gap: 12px; min-width: 0;
  -webkit-user-select: none; user-select: none;
}
.data-update-pill {
  --status-accent: #8591a0;
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  min-height: 34px; padding: 7px 12px; flex-shrink: 0;
  border: 1px solid #ffffff0e; border-radius: 999px; background: #ffffff03;
  color: #b3bcc7; font-size: 0.76rem; font-weight: 500; line-height: 18px;
  letter-spacing: 0.035em; white-space: nowrap; cursor: default;
}
.data-update-pill.is-synced { --status-accent: #86b9a8; }
.data-update-pill.is-busy { --status-accent: #8caed2; }
.data-update-pill.is-warning { --status-accent: #c8ad7b; color: #c5b79e; }
.status-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--status-accent); flex: 0 0 auto; }
.status-spinner {
  width: 10px; height: 10px; border: 1px solid #8caed22e; border-top-color: var(--status-accent);
  border-radius: 50%; flex: 0 0 auto; animation: status-spin 1.15s linear infinite;
}
.status-warning { width: 13px; height: 13px; color: var(--status-accent); stroke-width: 1.2; flex: 0 0 auto; }
@keyframes status-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .status-spinner { animation: none; } }
.data-update-button { min-height: 36px; padding: 7px 12px; font-size: 0.82rem; white-space: nowrap; }
@media (max-width: 720px) {
  .data-update-control { gap: 8px; }
}
@media (max-width: 520px) {
  .data-update-control { width: 100%; margin: 0; justify-content: space-between; padding-bottom: 12px; }
}
</style>
