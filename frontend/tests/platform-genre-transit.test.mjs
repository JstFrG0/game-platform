import test from 'node:test';
import assert from 'node:assert/strict';
import {platformExitPhases,platformGenreFrame,platformGenreTail} from '../src/platformGenreTransit.js';
import {platformEnergyRoutes,platformEnergyFrame,sampleEnergyRoute} from '../src/platformEnergy.js';
import {createBranch} from '../src/platformTreeLayout.js';
import {createOtherCluster} from '../src/platformOtherGroups.js';
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-7,`${a} != ${b}`);

test('energy returns before the aperture opens; a bare base skips the energy stage',()=>{
 for(let i=0;i<=1000;i++){
  const p=1+i/1000,a=platformExitPhases(p,true),b=platformExitPhases(p,false);
  if(a.aperture>0)assert.equal(a.flow,1);if(a.fall>0)assert.equal(a.aperture,1);
  assert.equal(b.flow,0);if(b.fall>0)assert.equal(b.aperture,1);
 }
 assert.equal(platformExitPhases(1.25,true).aperture,0);assert.ok(platformExitPhases(1.25,false).aperture>.99);
});
test('the original tree scale and base opacity remain intact, with no transition at the platform endpoint',()=>{
 const source={x:800,y:650},dest={x:680,y:490};
 const at=p=>platformGenreFrame(p,1000,source,dest);
 for(const p of [1,1.15,1.3,1.6,1.9,2]){assert.equal(at(p).gather,1);assert.equal(at(p).base,1);}
 assert.deepEqual(at(1).core,source);near(at(1).platformY,0);assert.equal(at(1).aperture,0);
 near(at(1.28).platformY,0);assert.equal(at(1.28).platformOpacity,1);
});
test('opening stays still; the camera follows a downward world-space release that clears the base before turning',()=>{
 for(const height of [568,1000,1440])for(const y of [height*.1,height*.6,height*1.4])for(const scale of [.35,1,1.1])for(const mounted of [true,false]){
  const source={x:height*.8,y},dest={x:height*.4,y:height*.5},at=p=>platformGenreFrame(p,height,source,dest,{baseScale:scale,mounted});
  let releaseY=-Infinity;
  for(let i=0;i<=500;i++){
   const p=1+i/500,f=at(p);
   assert.ok(Number.isFinite(f.core.x+f.core.y+f.platformY));
   if(f.fall===0){near(f.core.x,source.x);near(f.core.y,source.y);near(f.platformY,0);near(f.sky,0);}
   else{const worldY=f.core.y-f.platformY;assert.ok(worldY>=releaseY-1e-7);releaseY=worldY;
    if(Math.abs(f.core.x-source.x)>.01)assert.ok(f.core.y-source.y-f.platformY>=scale*46+10,'turned inside the base');
   }
   if(f.reveal>0){near(f.core.x,dest.x);near(f.core.y,dest.y);assert.equal(f.genreY,0);assert.equal(f.platformOpacity,0);}
  }
  assert.deepEqual(at(2).core,dest);assert.equal(at(2).reveal,1);
 }
});
test('scrubbing and reverse direction preserve exactly the same geometry, with no timers',()=>{
 const a={x:820,y:700},b={x:640,y:450},at=p=>platformGenreFrame(p,1000,a,b);
 for(const p of [1,1.2,1.36,1.50,1.64,1.78,1.9,2]){const held=at(p);at(p+.03);at(p-.09);assert.deepEqual(at(p),held);}
 for(const p of [1.3,1.44,1.46,1.55,1.64,1.78,1.8]){
  const before=at(p-1e-6),after=at(p+1e-6);assert.ok(Math.hypot(before.core.x-after.core.x,before.core.y-after.core.y)<.05);
 }
});
test('flight tail points behind the actual orb direction, including both sideways destinations',()=>{
 for(const x of [300,820,1300])for(const mounted of [true,false])for(const direction of [-1,1]){
  const source={x:820,y:700},dest={x,y:450},options={mounted};
  for(const p of [1.53,1.60,1.67,1.73]){
   const tail=platformGenreTail(p,direction,1,1000,source,dest,options);if(!tail.opacity)continue;
   const a=platformGenreFrame(p-.0001,1000,source,dest,options).core,b=platformGenreFrame(p+.0001,1000,source,dest,options).core,r=tail.angle*Math.PI/180;
   assert.ok((Math.sin(r)*(b.x-a.x)-Math.cos(r)*(b.y-a.y))*direction<0);
   assert.equal(platformGenreTail(p,direction,0,1000,source,dest,options).opacity,0);
  }
 }
});
test('energy uses the existing cubic wire geometry and stays bounded for large trees',()=>{
 const branches=[];for(const [i,family] of ['PC','PlayStation','Xbox','Nintendo','移动设备','其他'].entries())branches.push(createBranch(family,Array.from({length:70},(_,j)=>({id:i*1000+j})),i*60,branches));
 const anchor=branches.at(-1).leaves[0],detail=createOtherCluster(anchor,Array.from({length:6},(_,id)=>({id})),90,[]),routes=platformEnergyRoutes(branches,detail,anchor);
 assert.equal(routes.length,20);assert.equal(new Set(routes.map(r=>r.key)).size,20);
 for(const route of routes){
  const head=sampleEnergyRoute(route,0),end=sampleEnergyRoute(route,1);assert.ok(Math.hypot(head.x,head.y)>100);near(end.x,0);near(end.y,0);
  for(const t of [0,.1,.5,.9,1]){const a=sampleEnergyRoute(route,t);assert.ok(Number.isFinite(a.x+a.y));}
  const first=platformEnergyFrame(route,0,0),last=platformEnergyFrame(route,1,0);assert.equal(first.opacity,0);assert.equal(last.opacity,0);
  const a=platformEnergyFrame(route,.5,0,1),b=platformEnergyFrame(route,.5,0,-1);assert.deepEqual(a.head,b.head);assert.notEqual(a.path,b.path);
 }
 assert.deepEqual(platformEnergyRoutes([]),[]);
});
