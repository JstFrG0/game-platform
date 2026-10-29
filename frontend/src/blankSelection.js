import { onBeforeUnmount, onMounted } from "vue";

// Clear a stationary click without interfering with drag selection or controls.
export function useBlankSelectionClear() {
  let start = null;
  function pointerDown(event) {
    start = event.button === 0 ? { x: event.clientX, y: event.clientY } : null;
  }
  function click(event) {
    const origin = start;
    start = null;
    if (!origin || event.defaultPrevented || event.detail !== 1) return;
    if (Math.hypot(event.clientX - origin.x, event.clientY - origin.y) >= 4) return;
    if (!(event.target instanceof Element) || event.target.closest(
      '.game-card, a, button, input, textarea, select, label, summary, [contenteditable]:not([contenteditable="false"]), [role="button"], [role="slider"], [role="option"]'
    )) return;
    window.getSelection()?.removeAllRanges();
  }
  onMounted(() => {
    document.addEventListener('pointerdown', pointerDown, true);
    document.addEventListener('click', click);
  });
  onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', pointerDown, true);
    document.removeEventListener('click', click);
  });
}
