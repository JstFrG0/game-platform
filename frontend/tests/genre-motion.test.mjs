import test from 'node:test';
import assert from 'node:assert/strict';
import {genreTransitFrame,filterCoreTrail} from '../src/genreTransit.js';

const platform={x:820,y:700},genre={x:640,y:450};
test('genre chrome starts below the viewport, rises into place and reverses without a different path',()=>{
 for(const height of [568,1000,1440]){
  const at=p=>genreTransitFrame(p,height,platform,genre);
  assert.ok(at(1.60).genreY>height);
  assert.ok(at(1.60).genreOpacity<1e-12);
  let previous=at(1.60).genreY;
  for(let i=1;i<=18;i++){
   const p=1.60+i*.01,frame=at(p);
   assert.ok(frame.genreY<=previous);assert.ok(Number.isFinite(frame.genreY));previous=frame.genreY;
   at(p-.005);assert.deepEqual(at(p),frame);
  }
  assert.ok(Math.abs(at(1.78).genreY)<1e-8);
  assert.equal(at(2).genreY,0);assert.equal(at(2).genreOpacity,1);
  assert.equal(at(1.7).reveal,0);
 }
});
test('both scene pairs trail in their confirmed screen-space quadrant in either direction',()=>{
 for(const [p,direction,horizontal,vertical] of [[.6,1,-1,-1],[.6,-1,1,1],[1.56,1,1,-1],[1.56,-1,-1,1]]){
  const tail=filterCoreTrail(p,direction,1),r=tail.angle*Math.PI/180;
  assert.ok(tail.opacity>0);
  assert.equal(Math.sign(Math.sin(r)),horizontal);assert.equal(Math.sign(-Math.cos(r)),vertical);
  assert.ok(Math.abs(Math.sin(r))<Math.abs(Math.cos(r)),'tail should remain mostly vertical');
  assert.equal(filterCoreTrail(p,-direction,1).angle-tail.angle,direction*180);
 }
});
test('tail is absent in stationary phases and fades with speed while keeping its direction',()=>{
 for(const p of [0,.2,.32,.84,1,1.2,1.4,1.72,1.9,2])assert.equal(filterCoreTrail(p,1,1).opacity,0);
 for(const p of [.6,1.56]){
  const moving=filterCoreTrail(p,1,1),fading=filterCoreTrail(p,1,.2),paused=filterCoreTrail(p,1,0);
  assert.ok(fading.opacity<moving.opacity);assert.equal(paused.opacity,0);assert.equal(moving.angle,fading.angle);
 }
 for(const [edge,middle] of [[.321,.6],[.839,.6],[1.401,1.56],[1.719,1.56]])assert.ok(filterCoreTrail(edge,1,1).opacity<filterCoreTrail(middle,1,1).opacity);
});
