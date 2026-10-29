const clamp=x=>Math.max(0,Math.min(1,x));
const smooth=x=>{const t=clamp(x);return t*t*(3-2*t);};
const random=(id,salt)=>{const n=Math.sin(id*127.1+salt*311.7)*43758.5453;return n-Math.floor(n);};

export function genreGatherPhase(progress){
 const t=clamp(progress-2);
 return {active:progress>2&&progress<3,complete:t>=.28,
  handoff:smooth(t/.018),lines:1-smooth(t/.16),labels:1-smooth((t-.035)/.18),dust:1-smooth(t/.085)};
}
export function gatherRoute(star,center){
 const seed=Number(star.id)*31+star.index,dx=center.x-star.x,dy=center.y-star.y,bend=(random(seed,1)-.5)*.44;
 return {...star,to:{...center},control:{x:(star.x+center.x)/2-dy*bend,y:(star.y+center.y)/2+dx*bend},
  start:.012+random(seed,2)*.035,end:.21+random(seed,3)*.06};
}
export function gatherParticle(route,progress,direction=1){
 const phase=genreGatherPhase(progress),q=smooth((progress-2-route.start)/(route.end-route.start)),u=1-q,c=route.control,b=route.to;
 const x=u*u*route.x+2*u*q*c.x+q*q*b.x,y=u*u*route.y+2*u*q*c.y+q*q*b.y;
 const dx=2*(u*(c.x-route.x)+q*(b.x-c.x))*direction,dy=2*(u*(c.y-route.y)+q*(b.y-c.y))*direction;
 const length=16*Math.sin(q*Math.PI),norm=Math.hypot(dx,dy)||1;
 return {x,y,r:route.r,color:route.color,selected:route.selected,
  opacity:route.opacity*phase.handoff*(1-smooth((q-.84)/.16)),
  tail:{x:x-dx/norm*length,y:y-dy/norm*length},q};
}

// Sample the rendered circles, including current zoom, 3D attitude and paused
// drift. Store viewport-local coordinates so page translation never feeds back.
export function readGatherRoutes(viewport,center){
 if(!viewport)return [];
 const box=viewport.getBoundingClientRect(),routes=[];
 for(const node of viewport.querySelectorAll('.constellation-node')){
  const opacity=Number(getComputedStyle(node).opacity),selected=node.classList.contains('selected');
  if(opacity<=0)continue;
  const circles=node.querySelectorAll('.constellation-point > circle:last-child');
  for(let index=0;index<circles.length;index++){
   const circle=circles[index],r=circle.getBoundingClientRect();
   if(!r.width||!r.height||r.right<box.left||r.left>box.right||r.bottom<box.top||r.top>box.bottom)continue;
   routes.push(gatherRoute({id:Number(node.dataset.genre),index,x:r.x+r.width/2-box.x,y:r.y+r.height/2-box.y,
    r:Math.sqrt(r.width*r.height)/2,opacity,selected,color:getComputedStyle(circle).fill},center));
  }
 }
 return routes;
}
function surface(canvas,ratio){
 if(!canvas||!canvas.clientWidth||!canvas.clientHeight)return null;
 const width=canvas.clientWidth,height=canvas.clientHeight,d=Math.min(2,ratio),context=canvas.getContext('2d');
 if(!context)return null;
 const w=Math.round(width*d),h=Math.round(height*d);
 if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
 context.setTransform(d,0,0,d,0,0);context.clearRect(0,0,width,height);
 return {context,width,height};
}
export function clearEffect(canvas){
 const context=canvas?.getContext('2d');if(!context)return;
 context.save();context.setTransform(1,0,0,1,0,0);context.clearRect(0,0,canvas.width,canvas.height);context.restore();
}
export function drawGather(canvas,routes,progress,direction=1,ratio=1){
 const s=surface(canvas,ratio);if(!s)return false;
 const c=s.context;
 for(const route of routes){
  const point=gatherParticle(route,progress,direction);if(point.opacity<.001)continue;
  const length=Math.hypot(point.x-point.tail.x,point.y-point.tail.y);
  c.save();
  if(length>.05){
   const tail=c.createLinearGradient(point.tail.x,point.tail.y,point.x,point.y);
   tail.addColorStop(0,'rgba(169,206,255,0)');tail.addColorStop(1,'rgba(188,220,255,.48)');
   c.strokeStyle=tail;c.globalAlpha=point.opacity*.7;c.lineWidth=Math.max(.6,point.r*.72);c.lineCap='round';
   c.beginPath();c.moveTo(point.tail.x,point.tail.y);c.lineTo(point.x,point.y);c.stroke();
  }
  c.fillStyle=point.color;
  for(const [scale,alpha] of [[3.3,point.selected?.1:.04],[2,point.selected?.23:.08],[1,1]]){
   c.globalAlpha=point.opacity*alpha;c.beginPath();c.arc(point.x,point.y,point.r*scale,0,Math.PI*2);c.fill();
  }
  c.restore();
 }
 return true;
}
export function modeScanFrame(progress,width,height){
 const t=clamp((progress-2.76)/.14),radius=5+Math.max(0,Math.min(width,height)*.46-5)*smooth(t);
 return {x:width/2,y:height/2,radius,opacity:progress>2.76&&progress<2.90?Math.sin(t*Math.PI)*.32:0};
}
export function drawModeScan(canvas,progress,ratio=1){
 const s=surface(canvas,ratio);if(!s)return false;
 const wave=modeScanFrame(progress,s.width,s.height);if(wave.opacity<.001)return true;
 const c=s.context;c.strokeStyle=`rgba(151,198,246,${wave.opacity})`;c.lineWidth=1;
 c.beginPath();c.arc(wave.x,wave.y,wave.radius,0,Math.PI*2);c.stroke();
 c.strokeStyle=`rgba(114,171,233,${wave.opacity*.16})`;c.lineWidth=5;
 c.beginPath();c.arc(wave.x,wave.y,wave.radius,0,Math.PI*2);c.stroke();
 return true;
}
