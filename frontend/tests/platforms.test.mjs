import test from 'node:test';
import assert from 'node:assert/strict';
import { defaults, readQuery, buildQuery, listParams, platformIds, makeBrowseState, readBrowseState } from '../src/catalog.js';
test('multi-platform IDs survive URL, pagination, refresh and saved search views',()=>{
 const f=readQuery({platform_ids:'167,6,167',year:'2019',page:'3'}).filters;
 assert.equal(f.platform_ids,'6,167');
 assert.equal(listParams(f,3).platform_ids,'6,167');
 assert.equal(buildQuery(f,3).page,'3');
 assert.equal(readBrowseState(JSON.stringify(makeBrowseState(f,3))).filters.platform_ids,'6,167');
 assert.equal(listParams({...f,q:'NBA',search_scope:'global'}).platform_ids,undefined);
 assert.equal(listParams({...f,q:'NBA',search_scope:'filtered'}).platform_ids,'6,167');
 assert.equal(readQuery({platform_id:'6'}).filters.platform_id,'6');
});
test('invalid multi-platform values are rejected; empty means all platforms',()=>{
 for(const value of ['1.5','6,','-1','6,x','2147483648','６','6,,7',Array(101).fill('6').join(',')]) assert.deepEqual(platformIds(value),[]);
 assert.deepEqual(platformIds(''),[]);
 assert.deepEqual(platformIds(' 167,6,6 '),[6,167]);
 assert.equal(readQuery({platform_ids:'nope'}).filters.platform_ids,defaults().platform_ids);
});
