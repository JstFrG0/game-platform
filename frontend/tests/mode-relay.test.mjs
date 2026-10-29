import test from 'node:test';
import assert from 'node:assert/strict';
import {modeIds,readQuery,listParams,buildCatalogQuery,makeBrowseState,readBrowseState} from '../src/catalog.js';
import {advanceRelay,describeModes,modeCaption,relayGeometry,relayEdgePoint,relayBounds,relayViewportScale} from '../src/modeRelay.js';
import {modeTransitFrame} from '../src/modeTransit.js';
import {createFilterSpace,clampProgress,sceneAt} from '../src/filterSpace.js';
import {filterCoreTrail} from '../src/genreTransit.js';

test('legacy and plural mode URLs persist through paging, browse restoration and search',()=>{
 const f=readQuery({mode_id:'4',mode_ids:'3,1,3'}).filters;
 assert.equal(f.mode_ids,'1,3,4');assert.equal(f.mode_id,'');
 assert.equal(readQuery(buildCatalogQuery(f,4)).filters.mode_ids,'1,3,4');
 assert.equal(readBrowseState(JSON.stringify(makeBrowseState(f,4,{top:870}))).filters.mode_ids,'1,3,4');
 assert.equal(listParams({...f,q:'Game',search_scope:'global'}).mode_ids,undefined);
 assert.equal(listParams({...f,q:'Game',search_scope:'filtered'}).mode_ids,'1,3,4');
 for(const s of ['1,','1,-1','1,NaN','1,2147483648',','.repeat(101)])assert.deepEqual(modeIds(s),[]);
});
test('every real option and a saved missing tag retain selectable IDs and names',()=>{
 const modes=describeModes([{id:1,name:'Single player'},{id:6,name:'Battle Royale'},{id:99,name:'Future mode'},{id:'bad'}],[7]);
 assert.deepEqual(modes.map(m=>m.id),[1,6,7,99]);assert.equal(modes[2].label,'模式 7');assert.equal(modes[3].label,'Future mode');
 assert.equal(modeCaption([],modes),'全部模式');assert.equal(modeCaption([1,6],modes),'单人、大逃杀');
 assert.equal(modeCaption([1,6,99],modes),'已选 3 种模式');
});
test('rapid toggling reverses from the current build without resetting unrelated modules',()=>{
 const weights=new Map([[1,1],[3,.5]]);advanceRelay(weights,[1,3],60);const half=weights.get(3);
 advanceRelay(weights,[1],60);assert.ok(weights.get(3)<half);assert.equal(weights.get(1),1);
 advanceRelay(weights,[1,3,4],60);assert.ok(weights.get(3)>0);assert.ok(weights.get(4)>0);
 advanceRelay(weights,[4],0,true);assert.equal(weights.get(4),1);assert.equal(weights.get(1),0);assert.equal(weights.get(3),0);
});
test('cooperation and split screen compose around one center; removing solo leaves them intact',()=>{
 const get=(ids,id)=>relayGeometry(new Map(ids.map(i=>[i,1]))).layers.find(l=>l.id===id);
 const coop=get([3],3),paired=get([3,4],3);
 assert.ok(paired.nodes.some((n,i)=>n.point[0]!==coop.nodes[i].point[0]));
 const joints=relayGeometry(new Map([[3,1],[4,1]])).junctions;
 assert.ok(paired.edges.every(e=>joints.some(n=>n.point.every((v,i)=>v===e.from[i]))));
 assert.deepEqual(get([1,3,4],3),paired);
 for(let mask=0;mask<64;mask++){
  const ids=Array.from({length:6},(_,i)=>i+1).filter((_,i)=>mask&(1<<i));const geometry=relayGeometry(new Map(ids.map(i=>[i,1])));
  assert.deepEqual(geometry.layers.map(l=>l.id).sort((a,b)=>a-b),ids);
  for(const l of geometry.layers)for(const n of l.nodes)assert.ok(n.point.every(Number.isFinite));
 }
 assert.equal(relayGeometry(new Map([[99,1]])).layers[0].id,99);
});
test('all four endpoints are reachable and intermediate mode navigation blocks interaction',()=>{
 const s=createFilterSpace(()=>{});s.state.opened=true;assert.equal(clampProgress(4),3);assert.equal(sceneAt(3),'mode');
 for(const p of [2.2,2.5,2.8]){s.state.progress=p;assert.ok(s.blocked('mode'));assert.ok(s.blocked('genre'));}
 s.state.progress=3;assert.equal(s.blocked('mode'),false);assert.ok(s.blocked('genre'));
 s.state.closing=true;assert.ok(s.blocked('mode'));
});
test('all six modes leave the central area clear of long peripheral communication lines',()=>{
 const geometry=relayGeometry(new Map([1,2,3,4,5,6].map(id=>[id,1])));
 for(const layer of geometry.layers){
  if(layer.id===4)continue; // The two short shared-core links are intentional.
  for(const edge of layer.edges)for(let k=0;k<=24;k++)assert.ok(Math.hypot(...relayEdgePoint(edge,k/24))>60,`mode ${layer.id} crowds the core`);
 }
 const multi=geometry.layers.find(l=>l.id===2);
 for(const e of multi.edges){assert.ok(e.arc);assert.deepEqual(relayEdgePoint(e,0),e.from);assert.ok(Math.hypot(...relayEdgePoint(e,1).map((v,i)=>v-e.to[i]))<1e-8);}
});
test('dense arrays expand progressively and fit the actual canvas including node glow',()=>{
 const dense=relayGeometry(new Map([1,2,3,4,5,6].map(id=>[id,1]))),single=relayGeometry(new Map([[5,1]]));
 const projected=(g,w,h)=>relayBounds(g).x*relayViewportScale(w,h,g);
 assert.ok(projected(dense,1000,600)>projected(single,1000,600)*1.15);
 for(const [w,h] of [[160,150],[280,280],[400,220],[700,500],[1000,600]]){
  for(const ids of [[1,2,3,4,5,6],[1,2,3,4,5,6,99]]){
   const g=relayGeometry(new Map(ids.map(id=>[id,1]))),b=relayBounds(g),scale=relayViewportScale(w,h,g);
   assert.ok(b.x*scale<=w/2-12+1e-8);assert.ok(b.y*scale<=h/2-12+1e-8);
  }
 }
 const base=new Map([[1,1],[2,1],[3,1],[4,1],[5,1],[6,.5]]),a=relayGeometry(base);
 const partial=relayGeometry(new Map([...base].map(([id,p])=>[id,id===6?p+.0001:p])));
 assert.ok(partial.density>a.density);assert.ok(Math.abs(relayBounds(partial).x-relayBounds(a).x)<.1);
 assert.deepEqual(relayGeometry(base),a);
});
test('genre gathers before core travel; mode chrome rises before assembly and reverses deterministically',()=>{
 const genre={x:680,y:450},mode={x:720,y:490};
 for(const height of [568,900,1440]){
  const at=p=>modeTransitFrame(p,height,genre,mode);
  assert.deepEqual(at(2.2).core,genre);assert.ok(at(2.2).gather<1);assert.ok(Math.abs(at(2.2).genreY)<1e-8);
  assert.equal(at(2.32).gather,0);assert.equal(at(2.58).genreOpacity,0);
  assert.ok(at(2.58).modeY>=height);assert.equal(at(2.7).reveal,0);
  assert.deepEqual(at(2.76).core,mode);assert.ok(Math.abs(at(2.76).modeY)<1e-8);
  const held=at(2.88);at(2.7);assert.deepEqual(at(2.88),held);assert.ok(held.reveal>0&&held.reveal<1);
  assert.equal(at(3).reveal,1);assert.equal(at(3).modeOpacity,1);
 }
 assert.ok(filterCoreTrail(2.5,1,1).opacity>0);assert.equal(filterCoreTrail(2.5,-1,1).angle-filterCoreTrail(2.5,1,1).angle,180);
});
