import test from 'node:test';
import assert from 'node:assert/strict';
import {constellationNodes,constellationBurst} from '../src/genreConstellations.js';
const options=Array.from({length:22},(_,i)=>({id:i+1,name:'Adventure'}));

test('responsive scatter stays stable, covers the field and reserves distinct readable hit areas',()=>{
 for(const bounds of [{width:1376,height:700},{width:1856,height:780},{width:680,height:500},{width:340,height:400}]){
  const nodes=constellationNodes(options,bounds);
  assert.deepEqual(nodes,constellationNodes([...options].reverse(),bounds));
  assert.ok(nodes.some(n=>n.x<0)&&nodes.some(n=>n.x>0));assert.ok(nodes.some(n=>n.y<0)&&nodes.some(n=>n.y>0));
  for(let i=0;i<nodes.length;i++){
   const a=nodes[i];assert.ok(a.width>=170);assert.ok(Number.isFinite(a.x+a.y+a.width+a.height));
   for(let j=i+1;j<nodes.length;j++){
    const b=nodes[j];
    assert.ok(Math.abs(a.x-b.x)>=(a.width+b.width)/2 || Math.abs(a.y-b.y)>=(a.height+b.height)/2,'node hit areas overlap');
   }
  }
 }
 assert.deepEqual(constellationNodes([],{width:1000,height:600}),[]);
 for(const count of [1,2,3,45,100]){
  const many=Array.from({length:count},(_,i)=>({id:i+1,name:'Adventure'})),nodes=constellationNodes(many,{width:1200,height:600});
  assert.equal(nodes.length,count);assert.ok(nodes.every(n=>Number.isFinite(n.x+n.y)));
 }
});
test('all complete constellations burst from the same origin simultaneously after reveal starts',()=>{
 const nodes=constellationNodes(options);
 for(const node of nodes){
  const start=constellationBurst(node,0),early=constellationBurst(node,.03),end=constellationBurst(node,1);
  assert.equal(Math.hypot(start.x,start.y),0);assert.equal(start.opacity,0);
  assert.ok(early.opacity>0&&Math.hypot(early.x,early.y)>0);assert.ok(early.scale<.2);
  assert.equal(end.x,node.x);assert.equal(end.y,node.y);assert.equal(end.scale,1);assert.equal(end.opacity,1);assert.equal(end.labelOpacity,1);
  assert.equal(end.yaw,node.yaw);assert.equal(end.roll,node.roll);
 }
});
test('burst positions and spatial attitudes rewind exactly, with restrained varied final poses',()=>{
 const nodes=constellationNodes(options),a=nodes.map(n=>constellationBurst(n,.37));
 nodes.map(n=>constellationBurst(n,.85));assert.deepEqual(nodes.map(n=>constellationBurst(n,.37)),a);
 assert.ok(nodes.some(n=>n.yaw<-10)&&nodes.some(n=>n.yaw>10));assert.ok(nodes.some(n=>n.roll<-6)&&nodes.some(n=>n.roll>6));
 for(const n of nodes){assert.ok(Math.abs(n.yaw)<=34);assert.ok(Math.abs(n.roll)<=18);assert.deepEqual(constellationBurst(n,.2,true),constellationBurst(n,1));}
});
