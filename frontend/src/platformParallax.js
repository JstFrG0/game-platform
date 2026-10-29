// A virtual star field: stars belong to stable world cells, never screen edges.
// Only a bounded window is retained; going back reveals the same coordinates.
export const SKY_LAYERS = Object.freeze([
  Object.freeze({ depth: .10, cell: 210, size: .65, peak: .18 }),
  Object.freeze({ depth: .22, cell: 250, size: .95, peak: .23 }),
  Object.freeze({ depth: .36, cell: 300, size: 1.25, peak: .28 }),
]);
function random(seed, x, y, layer, salt) {
  let h = seed ^ Math.imul(x, 1597334677) ^ Math.imul(y, 3812015801) ^ Math.imul(layer + 1, 958282117) ^ Math.imul(salt, 1103515245);
  h = Math.imul(h ^ (h >>> 16), 2246822507);
  h = Math.imul(h ^ (h >>> 13), 3266489909);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
export function createParallaxSky(seed = 1) {
  let signature = '', previous = new Map(), layers = [];
  return {
    frame({ width, height, x = 0, y = 0, sky = 0, elapsed = 0 }) {
      if (!(width > 0 && height > 0) || ![width, height, x, y, sky, elapsed].every(Number.isFinite)) return [];
      const scale = Math.max(1, Math.sqrt(width * height / 1800000));
      const windows = SKY_LAYERS.map(layer => {
        const cell = Math.round(layer.cell * scale), dx = x * layer.depth, dy = y * layer.depth - sky;
        // One complete cell outside every edge: allocate before a star is visible.
        return { ...layer, cell, left: Math.floor(-dx / cell) - 1, right: Math.ceil((width - dx) / cell) + 1,
          top: Math.floor(-dy / cell) - 1, bottom: Math.ceil((height - dy) / cell) + 1 };
      });
      const key = windows.map(w => [w.cell, w.left, w.right, w.top, w.bottom].join(':')).join('|');
      if (key === signature) return layers;
      const retained = new Map();
      layers = windows.map((window, layer) => {
        const stars = [];
        for (let cy = window.top; cy <= window.bottom; cy++) for (let cx = window.left; cx <= window.right; cx++) {
          const id = `${layer}:${window.cell}:${cx}:${cy}`;
          let star = previous.get(id);
          if (!star) {
            const rand = salt => random(seed, cx, cy, layer, salt), life = 14 + rand(5) * 12, delay = rand(6) * 5;
            star = { id, x: (cx + .18 + rand(1) * .64) * window.cell, y: (cy + .18 + rand(2) * .64) * window.cell };
            star.style = { left: `${star.x}px`, top: `${star.y}px`, '--size': `${window.size + rand(3) * .6}px`,
              '--peak': window.peak + rand(4) * .18, '--life': `${life}s`, '--delay': `${delay - elapsed / 1000}s` };
          }
          retained.set(id, star); stars.push(star);
        }
        return { id: layer, depth: window.depth, stars };
      });
      previous = retained; signature = key;
      return layers;
    },
  };
}
