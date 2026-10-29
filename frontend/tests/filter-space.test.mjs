import test from 'node:test';
import assert from 'node:assert/strict';
import { clampProgress, wheelStep, spaceLayers, createFilterSpace } from '../src/filterSpace.js';

test('wheel units agree, large input is bounded, and direction is retained', () => {
  assert.equal(wheelStep({deltaMode:0,deltaY:160}),wheelStep({deltaMode:1,deltaY:10}));
  assert.equal(wheelStep({deltaMode:2,deltaY:.2},800),wheelStep({deltaMode:0,deltaY:160}));
  assert.equal(wheelStep({deltaMode:0,deltaY:5000}),.22);
  assert.equal(wheelStep({deltaMode:0,deltaY:-5000}),-.22);
  assert.equal(clampProgress(-.2),0);assert.equal(clampProgress(1.2),1.2);
});
test('structures collapse around a continuing core and reverse deterministically', () => {
  assert.deepEqual(spaceLayers(0),{year:1,platform:0,core:0});
  assert.equal(spaceLayers(1).platform,1);
  assert.equal(spaceLayers(.5).year,0);assert.equal(spaceLayers(.5).platform,0);
  const held=spaceLayers(.31);spaceLayers(.83);assert.deepEqual(spaceLayers(.31),held);
  for(let i=0;i<=100;i++) {
    const {year,platform}=spaceLayers(i/100);
    assert.ok(year>=0&&year<=1&&platform>=0&&platform<=1);
  }
});
test('only endpoint scenes are interactive and closing blocks both', () => {
  const s=createFilterSpace(()=>{});assert.ok(s.blocked('year'));
  s.state.opened=true;assert.equal(s.blocked('year'),false);assert.ok(s.blocked('platform'));
  s.state.progress=.4;assert.ok(s.blocked('year'));assert.ok(s.blocked('platform'));
  s.state.progress=1;assert.equal(s.blocked('platform'),false);
  s.state.progress=1.5;assert.ok(s.blocked('platform'));assert.ok(s.blocked('genre'));
  s.state.progress=2;assert.equal(s.blocked('genre'),false);assert.ok(s.blocked('platform'));
  s.state.closing=true;assert.ok(s.blocked('platform'));
});
