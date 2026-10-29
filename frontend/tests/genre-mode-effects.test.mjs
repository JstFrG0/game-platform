import test from 'node:test';
import assert from 'node:assert/strict';
import {genreGatherPhase,gatherRoute,gatherParticle,modeScanFrame,drawModeScan,drawGather} from '../src/genreModeEffects.js';
import {modeTransitFrame} from '../src/modeTransit.js';

test('all rendered star routes finish before page departure and core travel',()=>{
 const origin={x:540,y:390};
 for(let id=1;id<=40;id++)for(let index=0;index<7;index++){
  const star={id,index,x:id%2?50:980,y:60+index*100,r:2,color:'#e1e8ff',opacity:.9,selected:id%2===0};
  const route=gatherRoute(star,origin),start=gatherParticle(route,2),end=gatherParticle(route,2.28);
  assert.equal(start.x,star.x);assert.equal(start.y,star.y);assert.equal(start.opacity,0);
  assert.equal(end.x,origin.x);assert.equal(end.y,origin.y);assert.equal(end.opacity,0);
  assert.ok(route.start<route.end&&route.end<.28);
  assert.equal(genreGatherPhase(2.28).lines,0);assert.equal(genreGatherPhase(2.28).labels,0);
  const frame=modeTransitFrame(2.28,900,origin,{x:640,y:450});
  assert.deepEqual(frame.core,origin);assert.ok(Math.abs(frame.genreY)<1e-8);
 }
});
test('stars keep measured positions, colors, scale and dimming; arcs are deterministic with varied arrival',()=>{
 const center={x:200,y:200},ends=new Set();
 for(let id=1;id<=30;id++){
  const star={id,index:0,x:50,y:40,r:1.15,color:'rgb(179,199,237)',opacity:.09,selected:false};
  const route=gatherRoute(star,center);ends.add(route.end);
  assert.deepEqual(gatherRoute(star,center),route);
  const frame=gatherParticle(route,2+(route.start+route.end)/2);
  assert.equal(frame.r,star.r);assert.equal(frame.color,star.color);assert.ok(frame.opacity<=.09);
  const cross=(frame.x-star.x)*(center.y-star.y)-(frame.y-star.y)*(center.x-star.x);
  assert.ok(Math.abs(cross)>1e-4,'trajectory must bend away from the straight chord');
 }
 assert.ok(ends.size>20);
});
test('holding and reverse use identical star geometry; only tails reverse with travel',()=>{
 const route=gatherRoute({id:12,index:2,x:60,y:50,r:2,color:'#fff',opacity:1}, {x:500,y:400});
 for(let p=2.07;p<2.21;p+=.007){
  const a=gatherParticle(route,p,1),b=gatherParticle(route,p,-1);
  assert.deepEqual([a.x,a.y,a.opacity,a.q],[b.x,b.y,b.opacity,b.q]);
  assert.ok(Math.abs(a.tail.x+b.tail.x-2*a.x)<1e-8);
  assert.ok(Math.abs(a.tail.y+b.tail.y-2*a.y)<1e-8);
  gatherParticle(route,p+.02);assert.deepEqual(gatherParticle(route,p),a);
 }
});
test('scan starts after landing, expands before the original array reveals, and vanishes at rest',()=>{
 for(const [width,height] of [[160,150],[500,350],[1100,700]]){
  const genre={x:200,y:500},mode={x:width/2,y:height/2};
  for(const p of [0,1,2,2.6,2.76,2.9,3])assert.equal(modeScanFrame(p,width,height).opacity,0);
  const first=modeScanFrame(2.79,width,height),peak=modeScanFrame(2.83,width,height);
  assert.ok(first.opacity>0&&peak.radius>first.radius);
  assert.deepEqual(modeTransitFrame(2.79,800,genre,mode).core,mode);
  assert.equal(modeTransitFrame(2.79,800,genre,mode).reveal,0);
  assert.ok(modeTransitFrame(2.88,800,genre,mode).reveal>0);
  assert.equal(modeTransitFrame(3,800,genre,mode).reveal,1);
  assert.ok(peak.radius<Math.min(width,height)/2);
  const held=modeScanFrame(2.83,width,height);modeScanFrame(2.78,width,height);assert.deepEqual(modeScanFrame(2.83,width,height),held);
 }
 assert.equal(genreGatherPhase(2).active,false);assert.equal(genreGatherPhase(3).active,false);
});
test('missing or zero-sized overlay canvases degrade without interrupting the existing array',()=>{
 assert.equal(drawModeScan(null,2.83),false);assert.equal(drawGather(null,[],2.1),false);
 const canvas={clientWidth:0,clientHeight:0};
 assert.equal(drawModeScan(canvas,2.83),false);assert.equal(drawGather(canvas,[],2.1),false);
});
