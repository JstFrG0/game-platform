import { request } from './api.js';

// Detail navigation reuses successful options; committed data updates invalidate them.
export function createFilterOptionsCache(fetchOptions) {
  let cached, pending, generation = 0;
  function load() {
    if (cached !== undefined) return Promise.resolve(cached);
    if (pending) return pending;
    const current = generation;
    const task = Promise.resolve().then(fetchOptions).then(value => {
      if (generation === current) cached = value;
      return value;
    }).finally(() => { if (pending === task) pending = undefined; });
    pending = task;
    return pending;
  }
  load.invalidate = () => { generation++; cached = undefined; pending = undefined; };
  return load;
}

export const loadFilterOptions = createFilterOptionsCache(() => request('filter-options', {}));
