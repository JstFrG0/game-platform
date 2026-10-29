import test from 'node:test';
import assert from 'node:assert/strict';
import { createParallaxSky, SKY_LAYERS } from '../src/platformParallax.js';
const frame = { width: 1440, height: 1000, x: 40, y: 40, sky: 980, elapsed: 0 };
const flatten = layers => layers.flatMap(layer => layer.stars);

test('far, mid and near sky have distinct restrained depths and useful viewport coverage', () => {
  assert.deepEqual(SKY_LAYERS.map(layer => layer.depth), [.1, .22, .36]);
  const layers = createParallaxSky(1234).frame(frame);
  assert.equal(layers.length, 3);
  for (const layer of layers) {
    const visible = layer.stars.filter(star => star.x + frame.x * layer.depth >= 0 && star.x + frame.x * layer.depth < frame.width &&
      star.y + frame.y * layer.depth - frame.sky >= 0 && star.y + frame.y * layer.depth - frame.sky < frame.height);
    assert.ok(visible.length > 9);
    for (const [a,b] of [[0,0],[0,1],[1,0],[1,1]]) assert.ok(visible.some(star =>
      (star.x + frame.x * layer.depth >= frame.width / 2) === !!a && (star.y + frame.y * layer.depth - frame.sky >= frame.height / 2) === !!b));
  }
});
test('new columns are allocated outside the viewport without reseeding retained stars or restarting their twinkle', () => {
  const sky = createParallaxSky(1234), before = sky.frame(frame), after = sky.frame({ ...frame, x: 1400, elapsed: 1000 });
  const old = new Map(flatten(before).map(star => [star.id, star]));
  const common = flatten(after).filter(star => old.has(star.id));
  assert.ok(common.length > 30);
  for (const star of common) assert.equal(star, old.get(star.id));
  for (const layer of after) for (const star of layer.stars.filter(star => !old.has(star.id))) {
    const x = star.x + frame.x * layer.depth, y = star.y + frame.y * layer.depth - frame.sky;
    assert.ok(x < 0 || x > frame.width || y < 0 || y > frame.height, 'new star was inserted into the old visible viewport');
  }
});
test('long travel stays bounded and reverse travel restores original positions with continuous twinkle phase', () => {
  const sky = createParallaxSky(1234), first = flatten(sky.frame(frame));
  let last;
  for (let i = 1; i <= 50; i++) {
    last = flatten(sky.frame({ ...frame, x: i * 10000, y: -i * 10000, elapsed: i * 1000 }));
    assert.ok(last.length < 500);
  }
  assert.ok(last.every(star => !first.some(previous => previous.id === star.id)));
  const back = flatten(sky.frame({ ...frame, elapsed: 60000 }));
  assert.deepEqual(back.map(({id,x,y}) => ({id,x,y})), first.map(({id,x,y}) => ({id,x,y})));
  for (let i = 0; i < first.length; i++) assert.ok(Math.abs(parseFloat(back[i].style['--delay']) + 60 - parseFloat(first[i].style['--delay'])) < 1e-10);
});
test('idle and movement within the same grid window reuse nodes; transition and resize keep a bounded field', () => {
  const sky = createParallaxSky(1234), a = sky.frame(frame);
  assert.equal(sky.frame({ ...frame, x: 42, y: 42, elapsed: 50000 }), a);
  for (const dimensions of [{width:700,height:900},{width:3840,height:2160}]) {
    const b = sky.frame({ ...frame, ...dimensions, sky: 0 });
    assert.ok(flatten(b).length < 500);
    assert.ok(flatten(b).every(star => Number.isFinite(star.x) && Number.isFinite(star.y)));
  }
});
