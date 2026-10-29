import test from 'node:test';
import assert from 'node:assert/strict';
import {constellationNodes,constellationSparks} from '../src/genreConstellations.js';

test('a stable dust field covers the inside and outskirts rather than clustering around star points',()=>{
 for(const node of constellationNodes(Array.from({length:150},(_,i)=>({id:i+1,name:'Adventure'})))){
  const sparks=constellationSparks(node),minX=Math.min(...node.points.map(p=>p.x)),maxX=Math.max(...node.points.map(p=>p.x)),minY=Math.min(...node.points.map(p=>p.y)),maxY=Math.max(...node.points.map(p=>p.y)),cx=(minX+maxX)/2,cy=(minY+maxY)/2;
  const targets=sparks.map(s=>({x:s.x+s.dx,y:s.y+s.dy}));
  assert.equal(sparks.length,24);assert.equal(new Set(sparks.map(p=>p.key)).size,24);
  const inside=targets.filter(p=>p.x>=minX&&p.x<=maxX&&p.y>=minY&&p.y<=maxY).length;
  assert.ok(inside>=7&&24-inside>=7,'dust should cover both interior and exterior');
  for(const x of [-1,1])for(const y of [-1,1])assert.ok(targets.filter(p=>Math.sign(p.x-cx)===x&&Math.sign(p.y-cy)===y).length>=4,'a quadrant is sparse');
  assert.ok(targets.some(p=>node.points.every(q=>Math.hypot(p.x-q.x,p.y-q.y)>25)),'all dust stays attached to star points');
  for(let i=0;i<targets.length;i++)for(let j=i+1;j<targets.length;j++)assert.ok(Math.hypot(targets[i].x-targets[j].x,targets[i].y-targets[j].y)>7,'dust is clumped');
  for(const spark of sparks){
   const x=spark.x+spark.dx,y=spark.y+spark.dy;assert.ok(x>=minX-31&&x<=maxX+31&&y>=minY-23&&y<=maxY+23);
   assert.ok(spark.duration+spark.delay<=1060);assert.ok(spark.radius>0&&spark.radius<=1.25);
   assert.ok(Math.abs(spark.swayX)<=4&&Math.abs(spark.swayY)<=4);assert.ok(spark.driftDuration>=6000&&spark.driftDuration<=11000);
  }
  assert.deepEqual(constellationSparks(node),sparks);
 }
});
test('an empty shape emits nothing and a single point still supports a finite area field',()=>{
 assert.deepEqual(constellationSparks({id:1,points:[]}),[]);
 const sparks=constellationSparks({id:1,points:[{x:20,y:30}]});assert.equal(sparks.length,24);assert.ok(sparks.every(p=>Number.isFinite(p.x+p.y+p.dx+p.dy)));
});
