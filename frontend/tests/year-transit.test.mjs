import test from 'node:test';import assert from 'node:assert/strict';
import {transitLeg,yearTransitFrame} from '../src/yearTransit.js';
import {descentFrame} from '../src/filterDescent.js';
import {powderCut,powderParticles,sampleWireMesh} from '../src/spherePowder.js';
const a={x:600,y:500},b={x:800,y:540};

test('outbound years collapse before powder clears, with page and stars fixed until both finish',()=>{
 assert.equal(yearTransitFrame(.1).radius,0);
 assert.ok(yearTransitFrame(.18).powder>0 && yearTransitFrame(.18).powder<1);
 for(const p of [0,.04,.1,.2,.3,.32]){
  const f=yearTransitFrame(p);assert.equal(f.shift,0);assert.equal(f.sky,0);
  assert.equal(descentFrame(p,1000,a,b).yearY,0);assert.deepEqual(descentFrame(p,1000,a,b).core,a);
 }
 assert.equal(yearTransitFrame(.3).powder,1);assert.ok(yearTransitFrame(.4).shift>0);
});
test('return core is settled before years extend, then sphere rebuilds only after years are complete',()=>{
 const waiting=yearTransitFrame(.31,'return');assert.equal(waiting.radius,0);assert.equal(waiting.powder,1);
 const extending=yearTransitFrame(.24,'return');assert.ok(extending.radius>0&&extending.radius<1);assert.equal(extending.powder,1);
 const ready=yearTransitFrame(.18,'return');assert.equal(ready.radius,1);assert.equal(ready.powder,1);
 const mesh=yearTransitFrame(.08,'return');assert.equal(mesh.radius,1);assert.ok(mesh.powder>0&&mesh.powder<1);
 for(const p of [.31,.24,.18,.08,0])assert.deepEqual(descentFrame(p,1000,a,b).core,a);
});
test('direction reversals keep the current leg until reaching a complete endpoint',()=>{
 assert.equal(transitLeg('depart',.2,.1),'depart');assert.equal(transitLeg('return',.2,.4),'return');
 assert.equal(transitLeg('depart',1,.9),'return');assert.equal(transitLeg('return',0,.1),'depart');
 for(const p of [0,1]){
  const f=yearTransitFrame(p,'depart'),r=yearTransitFrame(p,'return');
  for(const key of ['radius','powder','shift','sky','meshVisible'])assert.equal(f[key],r[key]);
 }
 const saved=yearTransitFrame(.23,'return');yearTransitFrame(.15,'return');assert.deepEqual(yearTransitFrame(.23,'return'),saved);
});
test('wire dust is deterministic, remains local and disappears at both complete endpoints',()=>{
 const paths=[{d:'M200,16 L240,100 L200,200 L160,300 L200,384',back:false}];
 const samples=sampleWireMesh(paths);assert.equal(sampleWireMesh(paths),samples);
 for(const returning of [false,true]){
  for(const amount of [0,1])assert.ok(powderParticles(samples,amount,returning).every(p=>p.opacity===0));
  let visible=false;
  for(let i=1;i<20;i++){
   const particles=powderParticles(samples,i/20,returning);
   particles.forEach((p,j)=>{assert.ok(Math.hypot(p.x-samples[j].x,p.y-samples[j].y)<40);if(p.opacity>0)visible=true;});
   assert.deepEqual(powderParticles(samples,i/20,returning),particles);
  }
  assert.ok(visible);
 }
 assert.ok(powderCut(0)<0 && powderCut(1)>1);
});
