import './focusFeedback.css';

// Only deliberate Tab navigation reveals the quiet keyboard cues.
// Page shortcuts and scripted scene focus must not flash a focus decoration.
const root = document.documentElement;
function clearCue() { root.removeAttribute('data-keyboard-focus'); }
function trackKey(event) {
  if (event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) root.setAttribute('data-keyboard-focus', '');
  else if (!['Shift', 'Control', 'Alt', 'Meta'].includes(event.key)) clearCue();
}
document.addEventListener('keydown', trackKey, true);
document.addEventListener('pointerdown', clearCue, true);
window.addEventListener('blur', clearCue);
if (import.meta.hot) import.meta.hot.dispose(() => {
  document.removeEventListener('keydown', trackKey, true);
  document.removeEventListener('pointerdown', clearCue, true);
  window.removeEventListener('blur', clearCue); clearCue();
});
