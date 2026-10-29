import test from 'node:test';
import assert from 'node:assert/strict';
import {baseBlocksPoint,tagBlocksPoint,coreVisibleFraction,platformCoreOcclusion,wireApertureTransform} from '../src/platformOcclusion.js';
import {platformGenreFrame} from '../src/platformGenreTransit.js';

test('fall traverses real aperture and solid base: clear, entering, hidden, emerging, clear at different zooms',()=>{
 for(const scale of [.35,1,2]){
  const base={x:300,y:200},r=5*scale;
  const fraction=y=>coreVisibleFraction({x:300,y:200+y*scale},base,scale,1,[],r);
  assert.equal(fraction(0),1);
  assert.ok(fraction(9)>0&&fraction(9)<1);
  assert.equal(fraction(24),0);
  assert.ok(fraction(43)>0&&fraction(43)<1);
  assert.equal(fraction(50),1);
  assert.equal(baseBlocksPoint(base,base,scale,0),true);
 }
});
test('rounded cards respect viewport clipping and can cover the open hole',()=>{
 const tag={x:90,y:90,width:20,height:20,radius:5},clip={x:100,y:100,width:100,height:100};
 assert.equal(tagBlocksPoint({x:90,y:90},tag),false);
 assert.equal(tagBlocksPoint({x:95,y:100},tag,clip),false);
 assert.equal(tagBlocksPoint({x:105,y:105},tag,clip),true);
 assert.equal(coreVisibleFraction({x:100,y:100},{x:100,y:100},1,1,[{tags:[tag]}]),0);
});
test('no camera or sky pre-lift, then immediate continuous follow; occlusion is reversible',()=>{
 for(const mounted of [true,false]){
  const options={mounted,baseScale:1},platform={x:240,y:500},genre={x:600,y:140},start=mounted?1.44:1.22;
  for(const p of [1,1.1,start]){
   const f=platformGenreFrame(p,900,platform,genre,options);
   assert.ok(Math.abs(f.platformY)<1e-10);assert.equal(f.sky,0);assert.deepEqual(f.core,platform);
   assert.equal(platformCoreOcclusion(p,f,platform,1).active,false);
  }
  const f=platformGenreFrame(start+.001,900,platform,genre,options);
  assert.ok(f.worldFallY>0);assert.ok(f.cameraY>0);assert.ok(f.sky>0);
  const frames=[.005,.015,.035,.06,.09].map(d=>{
   const p=start+d,f=platformGenreFrame(p,900,platform,genre,options);
   return platformCoreOcclusion(p,f,platform,1);
  });
  for(let i=frames.length-1;i>=0;i--){
   const p=start+[.005,.015,.035,.06,.09][i];
   assert.deepEqual(platformCoreOcclusion(p,platformGenreFrame(p,900,platform,genre,options),platform,1),frames[i]);
  }
 }
});
test('wire cutout maps base SVG socket and aperture to tree world coordinates',()=>{
 assert.equal(wireApertureTransform(1),`translate(0 ${4/15}) scale(${29/30})`);
 assert.equal(wireApertureTransform(0),`translate(0 ${4/15}) scale(0)`);
});
