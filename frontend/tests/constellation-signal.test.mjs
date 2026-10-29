import test from 'node:test';
import assert from 'node:assert/strict';
import {startConstellationSignal,constellationSignalFrame,advanceConstellationSignals,constellationFlareSparks,flareSparkFrame,signalTarget} from '../src/constellationSignal.js';
import {constellationNodes} from '../src/genreConstellations.js';

const node={id:12,x:320,y:-180};
test('selection keeps the constellation idle until arrival, then gently peaks and settles',()=>{
 const signal=startConstellationSignal(node,true),at=elapsed=>constellationSignalFrame({...signal,elapsed},node);
 for(const fraction of [0,.1,.5,.99]){const f=at(signal.flightMs*fraction);assert.equal(f.active,false);assert.equal(f.phase,'outbound');assert.equal(f.boost,0);assert.ok(f.flight);}
 const arrival=at(signal.flightMs);assert.equal(arrival.active,true);assert.equal(arrival.phase,'flare');assert.equal(arrival.flight,null);assert.equal(arrival.boost,0);
 assert.ok(at(signal.flightMs+220).boost>.9);assert.ok(at(signal.flightMs+1000).boost<.35);
 const settled=at(signal.flightMs+1440);assert.equal(settled.boost,0);assert.equal(settled.active,true);
});
test('deselection deactivates immediately, pauses briefly, then flies from the constellation back to the core',()=>{
 const signal=startConstellationSignal(node,false),at=elapsed=>constellationSignalFrame({...signal,elapsed},node);
 assert.equal(at(0).active,false);assert.equal(at(0).flight,null);assert.equal(at(99).flight,null);
 const start=at(100).flight,end=at(100+signal.flightMs-.001).flight;
 assert.equal(start.x,signalTarget(node).x);assert.equal(start.y,signalTarget(node).y);
 assert.ok(Math.hypot(end.x,end.y)<.001);assert.equal(at(100+signal.flightMs).flight,null);
});
test('tails point behind travel in all quadrants, both outbound and returning',()=>{
 for(const x of [-400,0,400])for(const y of [-300,0,300])for(const selected of [true,false]){
  const n={id:1,x,y},s=startConstellationSignal(n,selected),offset=selected?0:100;
  const a=constellationSignalFrame({...s,elapsed:offset+s.flightMs*.4},n).flight,b=constellationSignalFrame({...s,elapsed:offset+s.flightMs*.41},n).flight;
  const angle=a.angle*Math.PI/180,tail={x:-Math.cos(angle)*a.length,y:-Math.sin(angle)*a.length};
  assert.ok(tail.x*(b.x-a.x)+tail.y*(b.y-a.y)<0,'tail faces travel');
  assert.ok(a.length>0&&a.length<=38);assert.ok(a.opacity>0&&a.opacity<=1);
 }
});
test('independent timelines survive another selection, reversal and completion without accumulating',()=>{
 let timelines={12:startConstellationSignal(node,true)};
 for(let i=0;i<10;i++)timelines=advanceConstellationSignals(timelines,32);
 const before=timelines[12];timelines[31]=startConstellationSignal({...node,id:31},true);
 timelines=advanceConstellationSignals(timelines,16);assert.equal(timelines[12].elapsed,before.elapsed+16);assert.equal(timelines[31].elapsed,16);
 const other=timelines[31];timelines[12]=startConstellationSignal(node,false);assert.equal(timelines[31],other);
 for(let i=0;i<30;i++)timelines[12]=startConstellationSignal(node,i%2===0);
 assert.equal(Object.keys(timelines).length,2);
 for(let i=0;i<80;i++)timelines=advanceConstellationSignals(timelines,48);
 assert.deepEqual(timelines,{});
});
test('tab wake-up or a delayed frame cannot suddenly finish a flight',()=>{
 const signal=startConstellationSignal(node,true);
 assert.equal(advanceConstellationSignals({12:signal},30000)[12].elapsed,48);
 assert.equal(advanceConstellationSignals({12:signal},-100)[12].elapsed,0);
});
test('extra dust uses a fixed, wider field that smoothly disappears, leaving the original field untouched',()=>{
 assert.deepEqual(constellationFlareSparks({points:[]}),[]);
 for(const n of constellationNodes(Array.from({length:60},(_,i)=>({id:i+1,name:'Adventure'})))){
  const sparks=constellationFlareSparks(n);assert.equal(sparks.length,18);assert.deepEqual(constellationFlareSparks(n),sparks);
  const minX=Math.min(...n.points.map(p=>p.x)),maxX=Math.max(...n.points.map(p=>p.x));
  assert.ok(sparks.filter(s=>s.cx+s.dx<minX||s.cx+s.dx>maxX).length>=4);
  for(const s of sparks){
   assert.equal(flareSparkFrame(s,0).opacity,0);assert.equal(flareSparkFrame(s,1).opacity,0);
   assert.ok(flareSparkFrame(s,.25).opacity>.5);assert.ok(flareSparkFrame(s,.9).opacity<.05);
   assert.ok(s.radius<=1.1);assert.ok(Number.isFinite(s.cx+s.cy+s.dx+s.dy));
  }
 }
});
