import { computed, ref, watch } from 'vue';

export const FILTER_MOTION_KEY = 'game-platform.simplify-filter-animations';

export function createFilterMotion(media, storage) {
  let saved = false;
  try { saved = storage?.getItem(FILTER_MOTION_KEY) === 'true'; } catch { /* Optional persistence. */ }
  const simplified = ref(saved), systemReduced = ref(!!media?.matches), saveFailed = ref(false);
  const reduced = computed(() => simplified.value || systemReduced.value);
  const listeners = new Set();
  const updateSystem = event => { systemReduced.value = event.matches; };
  media?.addEventListener('change', updateSystem);
  const stop = watch(reduced, matches => {
    for (const listener of listeners) listener({ matches, media: '(prefers-reduced-motion: reduce)' });
  }, { flush: 'sync' });
  return {
    simplified, reduced, saveFailed,
    motion: {
      get matches() { return reduced.value; },
      addEventListener(type, listener) { if (type === 'change') listeners.add(listener); },
      removeEventListener(type, listener) { if (type === 'change') listeners.delete(listener); },
    },
    setSimplified(value) {
      simplified.value = value === true;
      try {
        if (!storage) throw new Error('Storage unavailable');
        storage.setItem(FILTER_MOTION_KEY, String(simplified.value));
        saveFailed.value = false;
      } catch { saveFailed.value = true; }
    },
    receiveStoredValue(value) { simplified.value = value === 'true'; },
    dispose() { stop(); media?.removeEventListener('change', updateSystem); listeners.clear(); },
  };
}

let storage;
try { storage = globalThis.window?.localStorage; } catch { /* Browser may deny storage. */ }
export const filterPreferences = createFilterMotion(globalThis.window?.matchMedia('(prefers-reduced-motion: reduce)'), storage);
export const filterMotion = filterPreferences.motion;
watch(filterPreferences.simplified, enabled => {
  if (globalThis.document) document.documentElement.dataset.filterMotion = enabled ? 'simplified' : 'full';
}, { immediate: true, flush: 'sync' });
globalThis.window?.addEventListener('storage', event => {
  if (event.storageArea === storage && (event.key === FILTER_MOTION_KEY || event.key === null)) {
    filterPreferences.receiveStoredValue(event.newValue);
  }
});
