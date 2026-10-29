import test from 'node:test';
import assert from 'node:assert/strict';
import {createBranch, branchRects, overlaps, angleDistance, treeBounds} from '../src/platformTreeLayout.js';
const platforms=n=>Array.from({length:n},(_,i)=>({id:i+1}));
test('new branches honour direction, avoid collisions and do not move existing geometry',()=>{
 let branches=[];
 for(let i=0;i<6;i++){
  const previous=JSON.stringify(branches);
  const branch=createBranch('brand'+i,platforms(12),0,branches);
  assert.equal(JSON.stringify(branches),previous);
  assert.equal(branch.leaves.length,12);
  assert(branches.every(other=>angleDistance(other.angle,branch.angle)>=36));
  branches.push(branch);
 }
 const rects=branches.flatMap(branchRects);
 for(let i=0;i<rects.length;i++)for(let j=i+1;j<rects.length;j++) assert(!overlaps(rects[i],rects[j],17),`collision ${i}/${j}`);
 const bounds=treeBounds(branches);assert(bounds.left<bounds.right&&bounds.top<bounds.bottom);
});
test('arbitrary directional layouts stay finite, nonoverlapping and within independent cones',()=>{
 for(let trial=0;trial<20;trial++){
  const branches=[];
  for(let j=0;j<6;j++){
   const desired=((trial*83+j*71)%360)-180;
   const branch=createBranch('brand'+j,platforms(3+j*3),desired,branches);
   if(!j)assert.equal(branch.angle,desired);
   for(const leaf of branch.leaves){
    const angle=Math.atan2(leaf.y,leaf.x)*180/Math.PI;
    assert(angleDistance(angle,branch.angle)<=18.001);
    assert(Number.isFinite(leaf.x)&&Number.isFinite(leaf.y));
   }
   branches.push(branch);
  }
  const rects=branches.flatMap(branchRects);
  for(let i=0;i<rects.length;i++)for(let j=i+1;j<rects.length;j++)assert(!overlaps(rects[i],rects[j],17));
 }
});
