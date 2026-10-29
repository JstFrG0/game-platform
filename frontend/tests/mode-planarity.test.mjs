import test from 'node:test';
import assert from 'node:assert/strict';
import {relayGeometry,relayEdgePoint,orbitPoint} from '../src/modeRelay.js';

const EPS=1e-7,TAU=Math.PI*2,sub=(a,b)=>[a[0]-b[0],a[1]-b[1]],cross=(a,b)=>a[0]*b[1]-a[1]*b[0];
const close=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1])<1e-5;
function box(points){return {minX:Math.min(...points.map(p=>p[0])),maxX:Math.max(...points.map(p=>p[0])),minY:Math.min(...points.map(p=>p[1])),maxY:Math.max(...points.map(p=>p[1]))};}
function overlaps(a,b){return a.minX<=b.maxX+EPS&&b.minX<=a.maxX+EPS&&a.minY<=b.maxY+EPS&&b.minY<=a.maxY+EPS;}
function path(points,name){return {points,name,box:box(points)};}
function paths(g){
 const result=[];
 for(const l of g.layers){
  for(const [i,e] of l.edges.entries()){
   const count=e.arc?Math.max(2,Math.ceil(Math.abs(e.arc.end-e.arc.start)/.08)):1;
   result.push(path(Array.from({length:count+1},(_,k)=>relayEdgePoint(e,k/count)),`mode-${l.id}-edge-${i}`));
  }
  for(const [i,o] of l.orbits.entries()){
   if(o.opacity===0)continue;const start=o.start??0,end=start+((o.end??TAU)-start)*o.reveal,count=Math.max(2,Math.ceil(Math.abs(end-start)/.08));
   result.push(path(Array.from({length:count+1},(_,k)=>{const p=orbitPoint(o.radius,start+(end-start)*k/count,o.tilt,o.rotation);return [p[0]+(o.center?.[0]||0),p[1]+(o.center?.[1]||0)];}),`mode-${l.id}-orbit-${i}`));
  }
 }
 for(const [i,e] of g.channels.entries())result.push(path([e.from,e.to],`shared-channel-${i}`));
 return result;
}
function crossing(a,b,c,d,junctions){
 const r=sub(b,a),s=sub(d,c),rs=cross(r,s),q=sub(c,a);
 if(Math.hypot(...r)<EPS||Math.hypot(...s)<EPS)return false;
 if(Math.abs(rs)<EPS){
  if(Math.abs(cross(q,r))>EPS)return false;
  const axis=Math.abs(r[0])>Math.abs(r[1])?0:1;
  const overlap=Math.min(Math.max(a[axis],b[axis]),Math.max(c[axis],d[axis]))-Math.max(Math.min(a[axis],b[axis]),Math.min(c[axis],d[axis]));
  if(overlap>1e-5)return true; // Coincident segments are clutter too.
  if(overlap<-EPS)return false;
  const shared=[a,b].find(p=>close(p,c)||close(p,d));
  return !shared||!junctions.some(j=>close(shared,j));
 }
 const t=cross(q,s)/rs,u=cross(q,r)/rs;
 if(t<-EPS||t>1+EPS||u<-EPS||u>1+EPS)return false;
 const p=[a[0]+r[0]*t,a[1]+r[1]*t];
 const endpoints=(t<EPS||t>1-EPS)&&(u<EPS||u>1-EPS);
 return !(endpoints&&junctions.some(j=>close(p,j)));
}
function audit(weights,time=0){
 const g=relayGeometry(weights,time),lines=paths(g),junctions=[[0,0],...g.junctions.map(n=>n.point),...g.layers.flatMap(l=>l.nodes.map(n=>n.point))];
 for(let i=0;i<lines.length;i++)for(let j=i+1;j<lines.length;j++){
  const a=lines[i],b=lines[j];if(!overlaps(a.box,b.box))continue;
  for(let m=1;m<a.points.length;m++)for(let n=1;n<b.points.length;n++){
   const x=[a.points[m-1],a.points[m]],y=[b.points[n-1],b.points[n]];
   if(!overlaps(box(x),box(y)))continue;
   assert.equal(crossing(...x,...y,junctions),false,`${JSON.stringify([...weights])}: ${a.name} crosses ${b.name}`);
  }
 }
}

test('all 64 known-mode selections have no line crossings, tangent joins or duplicate segments',()=>{
 for(let mask=0;mask<64;mask++)for(const time of [0,9,34,80])audit(new Map(Array.from({length:6},(_,i)=>[i+1,mask&(1<<i)?1:0])),time);
});
test('all add/remove combinations remain planar through 1,344 sampled assembly states',()=>{
 for(let id=1;id<=6;id++)for(let mask=0;mask<32;mask++)for(const progress of [.02,.12,.25,.5,.75,.88,.98]){
  const others=[1,2,3,4,5,6].filter(n=>n!==id);
  audit(new Map([[id,progress],...others.map((n,i)=>[n,mask&(1<<i)?1:0])]),17);
 }
});
test('mixed simultaneous transitions and future modes retain disjoint lanes',()=>{
 let seed=2718;const random=()=>{seed=(1664525*seed+1013904223)>>>0;return seed/4294967296;};
 for(let k=0;k<250;k++)audit(new Map([1,2,3,4,5,6,7,99].map(id=>[id,random()])),random()*90);
 const weights=new Map([[1,1],[2,1],[3,1],[4,1],[5,1],[6,1],[99,1],[7,0]]);
 const old=relayGeometry(weights).layers.find(l=>l.id===99);weights.set(7,.02);
 // Density is already saturated, so the existing unknown lane stays exact.
 assert.deepEqual(relayGeometry(weights).layers.find(l=>l.id===99),old);
});
