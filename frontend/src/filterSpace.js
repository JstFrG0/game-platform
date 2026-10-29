import { reactive } from 'vue';

export const filterSpaceKey = Symbol('filter-space');
export const sceneKinds = ['year', 'platform', 'genre', 'mode'];
export const clampProgress = value => Math.max(0, Math.min(sceneKinds.length-1, value));
export const sceneIndex = kind => Math.max(0,sceneKinds.indexOf(kind));
export const sceneAt = value => sceneKinds[Math.round(clampProgress(value))];
export const atEndpoint = value => Number.isInteger(value);
export function wheelStep(event, height = 800) {
  const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? height : 1;
  return Math.max(-.22, Math.min(.22, event.deltaY * unit / 1800));
}
export function spaceLayers(value) {
  const p = Math.min(1,clampProgress(value));
  const year = Math.max(0, 1 - p / .48), platform = Math.max(0, (p - .52) / .48);
  return { year, platform, core: Math.sin(Math.PI * p) };
}
export function createFilterSpace(commit) {
  const state = reactive({ opened: false, closing: false, initializing: false, progress: 0, year: '', loading: false, error: '' });
  const scenes = new Map();
  const space = {
    state, scenes, host: null, commit,
    register(kind, api) { scenes.set(kind, api); return () => scenes.delete(kind); },
    enter(kind) { return space.host?.open(kind); },
    close(apply) { return space.host?.close(apply); },
    blocked(kind) { return state.closing || state.initializing || !state.opened || state.progress !== sceneIndex(kind); },
  };
  return space;
}

// Layout coordinates deliberately ignore the reversible scene transform.
export function layoutPoint(node, x = node?.offsetWidth / 2, y = node?.offsetHeight / 2) {
  if (!node) return null;
  let left = x, top = y;
  for (let current=node; current; current=current.offsetParent) { left+=current.offsetLeft; top+=current.offsetTop; }
  return { x:left, y:top, width:0, height:0 };
}
