<script setup>
defineProps({ family: String, name: String });
</script>
<template>
  <svg class="platform-mark" viewBox="0 0 48 48" fill="none" aria-hidden="true">
    <g v-if="family === 'PC' && /windows/i.test(name || '')" fill="currentColor">
      <path d="M7 10h15v13H7zm19 0h15v13H26zM7 27h15v13H7zm19 0h15v13H26z" />
    </g>
    <g v-else-if="family === 'PC'" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <rect x="6" y="7" width="36" height="27" rx="3" /><path d="M18 41h12m-6-7v7" />
      <path v-if="/linux/i.test(name || '')" d="m13 15 5 5-5 5m11 0h8" />
      <path v-else-if="/mac/i.test(name || '')" d="M16 26V15l8 8 8-8v11" />
      <path v-else d="M15 20h18" />
    </g>
    <g v-else-if="family === 'PlayStation'" fill="currentColor">
      <text x="4" y="33" font-size="28" font-weight="600" font-family="Arial, sans-serif" letter-spacing="-3">PS</text>
    </g>
    <g v-else-if="family === 'Xbox'" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
      <circle cx="24" cy="24" r="18" /><path d="M13 12c7 3 15 13 22 24M35 12C28 15 20 25 13 36" />
    </g>
    <g v-else-if="family === 'Nintendo'" stroke="currentColor" stroke-width="2.2">
      <path d="M22 7h-7a9 9 0 0 0-9 9v16a9 9 0 0 0 9 9h7zm5 0h6a9 9 0 0 1 9 9v16a9 9 0 0 1-9 9h-6z" />
      <circle cx="14" cy="18" r="3" fill="currentColor" /><circle cx="34" cy="30" r="3" fill="currentColor" />
    </g>
    <g v-else-if="family === '移动设备'" stroke="currentColor" stroke-width="2.2">
      <rect x="13" y="5" width="22" height="38" rx="5" /><path d="M20 10h8m-7 27h6" />
    </g>
    <g v-else stroke="currentColor" stroke-width="2">
      <path d="m24 5 17 10v19L24 44 7 34V15zm0 0v19m17-9L24 25 7 15m17 10v19" />
    </g>
  </svg>
</template>
<style scoped>
.platform-mark { width: 36px; height: 36px; flex: none; }
</style>
