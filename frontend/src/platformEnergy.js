import {trunkPath,twigPath} from './platformTreeLayout.js';
import {clusterPath} from './platformOtherGroups.js';
const clamp=x=>Math.max(0,Math.min(1,x));
const smooth=x=>{const t=clamp(x);return t*t*(3-2*t);};
function reversedCurve(path){
 // All three layout builders emit exactly one M + cubic C segment.
 const n=path.match(/-?(?:\d*\.)?\d+(?:e[-+]?\d+)?/gi).map(Number);
 return Array.from({length:49},(_,i)=>{
  const t=1-i/48,u=1-t;
  return {x:u**3*n[0]+3*u*u*t*n[2]+3*u*t*t*n[4]+t**3*n[6],y:u**3*n[1]+3*u*u*t*n[3]+3*u*t*t*n[5]+t**3*n[7]};
 });
}
function route(key,paths){
 const points=paths.flatMap((path,i)=>reversedCurve(path).slice(i?1:0)),distances=[0];
 for(let i=1;i<points.length;i++)distances.push(distances.at(-1)+Math.hypot(points[i].x-points[i-1].x,points[i].y-points[i-1].y));
 return {key,points,distances,length:distances.at(-1)};
}
export function platformEnergyRoutes(branches,detail=null,anchor=null){
 const routes=[];
 for(const branch of branches){
  const indices=[...new Set([0,Math.floor(branch.leaves.length/2),branch.leaves.length-1])].filter(i=>i>=0&&i<branch.leaves.length);
  if(!indices.length)routes.push(route(branch.family,[trunkPath(branch)]));
  for(const i of indices)routes.push(route(`${branch.family}:${branch.leaves[i].id}`,[twigPath(branch,branch.leaves[i]),trunkPath(branch)]));
 }
 const other=branches.find(b=>b.family==='其他');
 if(other&&detail&&anchor)for(const leaf of [detail.leaves[0],detail.leaves.at(-1)].filter((x,i,a)=>x&&a.indexOf(x)===i)){
  routes.push(route(`detail:${leaf.id}`,[clusterPath(detail.header,leaf),clusterPath(anchor,detail.header),twigPath(other,anchor),trunkPath(other)]));
 }
 return routes;
}
export function sampleEnergyRoute(route,progress){
 const distance=clamp(progress)*route.length;let lo=0,hi=route.distances.length-1;
 while(lo+1<hi){const mid=(lo+hi)>>1;if(route.distances[mid]<distance)lo=mid;else hi=mid;}
 const span=route.distances[hi]-route.distances[lo],t=span?(distance-route.distances[lo])/span:0,a=route.points[lo],b=route.points[hi];
 return {x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t};
}
export function platformEnergyFrame(route,flow,index,direction=1){
 const delay=(index%3)*.035+Math.floor(index/3)*.004,t=clamp((flow-delay)/(1-delay));
 const opacity=smooth(t/.045)*smooth((1-t)/.045)*.82,head=sampleEnergyRoute(route,t),length=Math.min(.10,34/Math.max(1,route.length));
 const tail=Array.from({length:7},(_,i)=>sampleEnergyRoute(route,t-direction*length*(1-i/6)));
 return {key:route.key,head,opacity,path:tail.map((p,i)=>`${i?'L':'M'}${p.x} ${p.y}`).join(' ')};
}
