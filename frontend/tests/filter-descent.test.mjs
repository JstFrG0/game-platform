import test from 'node:test';import assert from 'node:assert/strict';
import {descentFrame,descentStars,landingParticles,CORE_CONTACT} from '../src/filterDescent.js';
const a={x:720,y:530},b={x:812,y:548};
test('year content exits before the incoming platform appears, at every window height',()=>{for(const h of [480,844,1000]){const gap=descentFrame(.47,h,a,b);assert.ok(gap.yearY+h<0);assert.ok(gap.platformY>h);assert.equal(gap.stage,'core-only');assert.equal(descentFrame(0,h,a,b).yearY,0);assert.equal(descentFrame(1,h,a,b).platformY,0);}});
test('the core stays fixed during year departure and locks to the rising base on contact',()=>{for(const p of [0,.1,.3,.44,.5])assert.deepEqual(descentFrame(p,1000,a,b).core,a);for(const p of [CORE_CONTACT,.86,.93,1]){const f=descentFrame(p,1000,a,b);assert.equal(f.core.x,b.x);assert.equal(f.core.y,b.y+f.platformY);}assert.deepEqual(descentFrame(1,1000,a,b).core,b);});
test('the platform rises monotonically and arrival particles disappear exactly at rest',()=>{let y=Infinity;for(let i=50;i<=100;i++){const f=descentFrame(i/100,1000,a,b);assert.ok(f.platformY<=y);y=f.platformY;}for(const p of landingParticles(0))assert.equal(p.opacity,0);for(const p of landingParticles(1))assert.equal(p.opacity,0);assert.ok(landingParticles(.5).some(p=>p.opacity>0));assert.ok(landingParticles(.8).every(p=>Math.hypot(p.x,p.y)<100));});
test('one base flash and reversible particle positions follow progress, not timers',()=>{const flashes=Array.from({length:101},(_,i)=>descentFrame(CORE_CONTACT+(1-CORE_CONTACT)*i/100,1000,a,b).flash);const peaks=flashes.slice(1,-1).filter((v,i)=>v>flashes[i]&&v>=flashes[i+2]);assert.equal(peaks.length,1);const paused=landingParticles(.6);landingParticles(.9);assert.deepEqual(landingParticles(.6),paused);assert.equal(descentFrame(1,1000,a,b).flash,0);});
test('sparks launch from the full base perimeter and travel only a short distance outward',()=>{
  const rim=[[0,-27],[48,-1],[48,16],[0,43],[-48,16],[-48,-1]];
  const starts=landingParticles(0),ends=landingParticles(1);
  const distanceToEdge=(p,a,b)=>{
    const dx=b[0]-a[0],dy=b[1]-a[1];
    const t=Math.max(0,Math.min(1,((p.x-a[0])*dx+(p.y-a[1])*dy)/(dx*dx+dy*dy)));
    return Math.hypot(p.x-a[0]-t*dx,p.y-a[1]-t*dy);
  };
  for(let i=0;i<starts.length;i++){
    const start=starts[i],end=ends[i],travel=Math.hypot(end.x-start.x,end.y-start.y);
    assert.ok(Math.min(...rim.map((a,j)=>distanceToEdge(start,a,rim[(j+1)%6])))<1e-8);
    assert.ok(Math.hypot(start.x,start.y)>20,'no central emission');
    assert.ok(travel>=12 && travel<30,'short burst');
    assert.ok(Math.hypot(end.x,end.y)>Math.hypot(start.x,start.y),'outward emission');
  }
  assert.equal(new Set(starts.map(p=>`${p.x},${p.y}`)).size,36);
});
test('the star field includes distinct replacement rows without recycling coordinates',()=>{let seed=42;const rng=()=>((seed=(seed*1664525+1013904223)>>>0)/4294967296);const stars=descentStars(1440,1000,rng);const tops=stars.map(s=>parseFloat(s.top.slice(5)));assert.ok(tops.some(v=>v<100));assert.ok(tops.some(v=>v>150));assert.ok(stars.every(s=>s.top.includes('var(--sky-travel)')));assert.ok(new Set(stars.map(s=>s.left)).size===stars.length);});
