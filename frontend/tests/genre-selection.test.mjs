import test from 'node:test';import assert from 'node:assert/strict';
import {genreIds,readQuery,listParams,buildCatalogQuery,makeBrowseState,readBrowseState} from '../src/catalog.js';
import {constellationNodes,genreLabel} from '../src/genreConstellations.js';
import {genreTransitFrame} from '../src/genreTransit.js';

test('multi genres and legacy URLs survive pagination, refresh and saved global search',()=>{
 const f=readQuery({genre_ids:'31,12,31',genre_id:'5',year:'2025'}).filters;assert.equal(f.genre_ids,'5,12,31');assert.equal(f.genre_id,'');
 assert.equal(readQuery(buildCatalogQuery(f,3)).filters.genre_ids,f.genre_ids);
 const saved=makeBrowseState(f,3,{top:600});assert.equal(readBrowseState(JSON.stringify(saved)).filters.genre_ids,f.genre_ids);
 assert.equal(listParams({...f,q:'Game',search_scope:'global'}).genre_ids,undefined);
 assert.equal(listParams({...f,q:'Game',search_scope:'filtered'}).genre_ids,'5,12,31');
 for(const value of ['12,','12,-1','12,1e3','12,NaN','12,2147483648'])assert.deepEqual(genreIds(value),[]);
 assert.equal(readQuery({genre_id:'12'}).filters.genre_ids,'12');assert.deepEqual(genreIds(''),[]);
});
test('all types have stable separate constellations and unknown names remain available',()=>{
 const values=Array.from({length:45},(_,i)=>({id:i+1,name:i===0?'Unlisted type':'Adventure'}));
 const a=constellationNodes(values),b=constellationNodes([...values].reverse());assert.deepEqual(a,b);assert.equal(a[0].label,'Unlisted type');assert.equal(genreLabel({id:999}),'类型 999');assert.equal(genreLabel({id:999,name:'constructor'}),'constructor');assert.equal(genreLabel({id:25,name:"Hack and slash/Beat 'em up"}),'砍杀／清版动作');
 for(let i=0;i<a.length;i++){assert.ok(Math.hypot(a[i].x,a[i].y)>150);for(let j=i+1;j<a.length;j++)assert.ok(Math.abs(a[i].x-a[j].x)>245||Math.abs(a[i].y-a[j].y)>160,'nodes overlap');}
 assert.equal(new Set(a.map(n=>n.path)).size,a.length);
});
test('platform keeps its structure while energy returns and the aperture opens before the orb falls',()=>{
 const p={x:800,y:550},g={x:720,y:500},at=t=>genreTransitFrame(t,1000,p,g);
 assert.ok(Math.abs(at(1.2).platformY)<1e-8);assert.deepEqual(at(1.2).core,p);assert.equal(at(1.2).gather,1);
 assert.equal(at(1.44).aperture,1);assert.equal(at(1.44).fall,0);assert.equal(at(1.44).base,1);
 assert.equal(at(1.6).reveal,0);assert.deepEqual(at(1.78).core,g);assert.equal(at(1.8).reveal,0);
 const held=at(1.86);at(1.7);assert.deepEqual(at(1.86),held);assert.ok(held.reveal>0&&held.reveal<1);assert.equal(at(2).reveal,1);
});
