import test from 'node:test';
import assert from 'node:assert/strict';
import {otherCategories,createOtherCluster,OTHER_PAGE_SIZE} from '../src/platformOtherGroups.js';
import {createBranch,branchRects,ROOT,overlaps} from '../src/platformTreeLayout.js';
test('other platform grouping retains every ID, unknown names fall back without guessing',()=>{
 const input=[{id:1,name:'Dreamcast'},{id:2,name:'Meta Quest 3'},{id:3,name:'Web browser'},{id:4,name:'Mystery Device'},{id:5,name:null},{id:6,name:'Commodore 64'}];
 const groups=otherCategories(input);
 assert.equal(groups.length,4);
 assert.deepEqual(groups.find(g=>g.key==='classic').platforms.map(p=>p.id),[1,6]);
 assert.deepEqual(groups.find(g=>g.key==='devices').platforms.map(p=>p.id),[4,5]);
 assert.deepEqual(groups.flatMap(g=>g.platforms.map(p=>p.id)).sort((a,b)=>a-b),[1,2,3,4,5,6]);
 assert.deepEqual(otherCategories([]),[]);
});
test('large other catalog is bounded by categories and a compact six-item detail cluster',()=>{
 const input=Array.from({length:90},(_,i)=>({id:i,name:'Atari '+i}));
 const groups=otherCategories(input), main=createBranch('其他',groups,90,[]), old=createBranch('其他',input,90,[]);
 assert.equal(main.leaves.length,1);
 assert(Math.max(...old.leaves.map(p=>p.distance))>Math.max(...main.leaves.map(p=>p.distance))*3);
 const occupied=[ROOT,...branchRects(main)];
 const cluster=createOtherCluster(main.leaves[0],input.slice(0,OTHER_PAGE_SIZE),90,occupied);
 assert.equal(cluster.leaves.length,6);assert.equal(cluster.box.width,330);assert.equal(cluster.box.height,266);
 assert(occupied.every(rect=>!overlaps(cluster.box,rect)));
});
