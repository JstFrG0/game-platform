import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createFilterMotion, FILTER_MOTION_KEY } from '../src/filterMotion.js';

function media(initial = false) {
  const listeners = new Set();
  return { matches:initial, addEventListener:(_, fn)=>listeners.add(fn), removeEventListener:(_, fn)=>listeners.delete(fn),
    change(value) { this.matches = value; for (const fn of listeners) fn({matches:value}); } };
}
function storage(initial = null) {
  let value = initial;
  return { getItem:()=>value, setItem:(key, next)=>{assert.equal(key,FILTER_MOTION_KEY);value=next;} };
}
test('simplification persists and is restored while off preserves the original motion default', () => {
  const saved=storage(), first=createFilterMotion(media(),saved);
  assert.equal(first.motion.matches,false);
  const changes=[];const listener=e=>changes.push(e.matches);
  first.motion.addEventListener('change',listener);
  first.setSimplified(true);
  assert.deepEqual(changes,[true]);
  const restored=createFilterMotion(media(),saved);
  assert.equal(restored.simplified.value,true);
  first.setSimplified(false);
  assert.equal(first.motion.matches,false);
  first.motion.removeEventListener('change',listener);
  first.setSimplified(true);
  assert.deepEqual(changes,[true,false]);
  first.dispose();restored.dispose();
});
test('turning the setting off never overrides system reduced motion, and runtime system changes propagate', () => {
  const system=media(true), preferences=createFilterMotion(system,storage());
  preferences.setSimplified(false);
  assert.equal(preferences.motion.matches,true);
  system.change(false);
  assert.equal(preferences.motion.matches,false);
  preferences.setSimplified(true);
  system.change(true);system.change(false);
  assert.equal(preferences.motion.matches,true);
  preferences.dispose();
});
test('blocked or malformed storage does not prevent changes in the current window', () => {
  const preferences=createFilterMotion(media(),{getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}});
  preferences.setSimplified(true);
  assert.equal(preferences.motion.matches,true);
  assert.equal(preferences.saveFailed.value,true);
  preferences.receiveStoredValue(null);
  assert.equal(preferences.simplified.value,false);
  preferences.dispose();
  const malformed=createFilterMotion(media(),storage('{bad'));
  assert.equal(malformed.motion.matches,false);
  malformed.dispose();
});
