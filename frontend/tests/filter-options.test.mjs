import test from 'node:test';
import assert from 'node:assert/strict';
import { createFilterOptionsCache } from '../src/filterOptions.js';

test('concurrent consumers share one request and detail navigation reuses successful options', async () => {
  let calls=0, resolve;
  const load=createFilterOptionsCache(() => { calls++;return new Promise(done => { resolve=done; }); });
  const first=load(), second=load();
  assert.equal(first,second);
  await Promise.resolve();
  const data={platforms:[{id:6,name:'Windows'}]};resolve(data);
  assert.equal(await first,data);assert.equal(await second,data);
  assert.equal(await load(),data);assert.equal(calls,1);
});

test('failed option requests can be retried and a success is then cached', async () => {
  let calls=0;
  const load=createFilterOptionsCache(async () => { if(++calls===1)throw Error('not ready');return {available_years:[2016,2026]}; });
  await assert.rejects(load(),/not ready/);
  assert.deepEqual(await load(),{available_years:[2016,2026]});
  await load();assert.equal(calls,2);
});

test('synchronous fetch errors do not poison the shared cache', async () => {
  let calls=0;const load=createFilterOptionsCache(() => { if(++calls===1)throw Error('offline');return {platforms:[]}; });
  await assert.rejects(load(),/offline/);assert.deepEqual(await load(),{platforms:[]});
});

test('a data update invalidates options and an older response cannot overwrite the new cache', async () => {
  const resolvers = [];
  const load = createFilterOptionsCache(() => new Promise(resolve => resolvers.push(resolve)));
  const old = load();
  await Promise.resolve();
  load.invalidate();
  const fresh = load();
  await Promise.resolve();
  resolvers[1]({available_years:[2025,2026]});
  await fresh;
  resolvers[0]({available_years:[2025]});
  await old;
  assert.deepEqual(await load(), {available_years:[2025,2026]});
});
