import test from 'node:test';import assert from 'node:assert/strict';
import {retryCatalogStartup} from '../src/catalogStartup.js';

test('cold-start connection and 503 failures recover with bounded backoff',async()=>{
 let calls=0;const delays=[];
 const value=await retryCatalogStartup(async()=>{calls++;if(calls===1)throw new TypeError('Failed to fetch');if(calls===2)throw Object.assign(Error('not ready'),{status:503});return 'ready';},{wait:async ms=>delays.push(ms)});
 assert.equal(value,'ready');assert.equal(calls,3);assert.deepEqual(delays,[350,900]);
});
test('missing endpoints and invalid parameters surface without retries',async()=>{
 for(const status of [404,422]){let calls=0;await assert.rejects(retryCatalogStartup(async()=>{calls++;throw Object.assign(Error('invalid'),{status});},{wait:async()=>assert.fail('unexpected retry')}),/invalid/);assert.equal(calls,1);}
});
test('an unavailable backend stops after three attempts',async()=>{
 let calls=0;await assert.rejects(retryCatalogStartup(async()=>{calls++;throw Object.assign(Error('unavailable'),{status:503});},{wait:async()=>{}}),/unavailable/);assert.equal(calls,3);
});
test('canceling navigation stops cold-start retry during the backoff',async()=>{
 let calls=0;const controller=new AbortController();
 const pending=retryCatalogStartup(async()=>{calls++;throw new TypeError('Failed to fetch');},{signal:controller.signal});
 await Promise.resolve();controller.abort();await assert.rejects(pending,{name:'AbortError'});assert.equal(calls,1);
});
