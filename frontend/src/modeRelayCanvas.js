import {orbitPoint,relayGeometry,relayEdgePoint,relayViewportScale,relayBounds} from './modeRelay.js';
const TAU=Math.PI*2;
function surface(canvas,ratio=window.devicePixelRatio||1){
  if(!canvas)return null;const width=canvas.clientWidth,height=canvas.clientHeight;if(!width||!height)return null;
  const d=Math.min(2,ratio),w=Math.round(width*d),h=Math.round(height*d);
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
  const c=canvas.getContext('2d');if(!c)return null;
  c.setTransform(d,0,0,d,0,0);c.clearRect(0,0,width,height);return{c,width,height};
}
function glow(c,p,r,alpha){
  const g=c.createRadialGradient(...p,0,...p,r);g.addColorStop(0,`rgba(180,218,255,${alpha})`);g.addColorStop(.16,`rgba(118,182,255,${alpha*.46})`);g.addColorStop(.5,`rgba(65,128,218,${alpha*.12})`);g.addColorStop(1,'rgba(59,114,208,0)');c.fillStyle=g;c.beginPath();c.arc(...p,r,0,TAU);c.fill();
}
function node(c,p,r,a){glow(c,p,r*5,.5*a);c.fillStyle=`rgba(207,229,255,${a})`;c.beginPath();c.arc(...p,r,0,TAU);c.fill();}
function orbit(c,o,alpha){
  const center=o.center||[0,0];c.save();c.translate(...center);c.strokeStyle=`rgba(120,169,224,${alpha})`;c.lineWidth=.7;c.beginPath();
  const start=o.start??0,end=o.end??TAU;
  for(let k=0;k<=96;k++){const p=orbitPoint(o.radius,start+(end-start)*o.reveal*k/96,o.tilt,o.rotation);if(k===0)c.moveTo(...p);else c.lineTo(...p);}c.stroke();c.restore();
}
function edgePath(c,e,start=0,end=1,alpha=.35,width=.7){
  c.strokeStyle=`rgba(139,187,238,${alpha})`;c.lineWidth=width;c.beginPath();
  const count=e.arc?24:1;for(let k=0;k<=count;k++){const p=relayEdgePoint(e,start+(end-start)*k/count);if(!k)c.moveTo(...p);else c.lineTo(...p);}c.stroke();
}
function pulse(c,e,phase,alpha,reverse=false){
  const p=((phase%1)+1)%1;if(p<.03||p>.97)return;
  const start=Math.max(0,p-.1),from=reverse?1-start:start,to=reverse?1-p:p;
  edgePath(c,e,from,to,alpha,1.2);node(c,relayEdgePoint(e,to),.85,alpha);
}
function layer(c,layer,time,animated=true){
  const a=layer.alpha;c.save();c.globalAlpha*=a;
  layer.orbits.forEach((o,k)=>{
    const opacity=o.opacity??1;orbit(c,o,(k===1?.13:.36)*opacity);
    if(animated&&o.reveal===1&&opacity>0&&layer.id!==1){
      const start=o.start??0,end=o.end??TAU,phase=Math.abs(end-start-TAU)<1e-8?(time*.045+k/3)%1:.5-.5*Math.cos(time*.15+k);
      const p=orbitPoint(o.radius,start+(end-start)*phase,o.tilt,o.rotation);node(c,[(o.center?.[0]||0)+p[0],(o.center?.[1]||0)+p[1]],.95,.75*opacity);
    }
  });
  layer.edges.forEach(e=>{edgePath(c,e);if(animated){pulse(c,e,time*.2+e.phase,.78);if(e.sync)pulse(c,e,time*.2+.5,.56,true);}});
  layer.nodes.forEach(n=>{c.save();c.globalAlpha*=n.alpha??1;node(c,n.point,n.r,.9);c.strokeStyle='#7cb6ec70';c.lineWidth=.65;c.beginPath();c.arc(...n.point,n.r+4,0,TAU);c.stroke();c.restore();});c.restore();
}
function sharedChannels(c,geometry,time,animated){
  for(const e of geometry.channels){c.save();c.globalAlpha*=e.alpha;edgePath(c,e);if(animated){pulse(c,e,time*.2,.75);pulse(c,e,time*.2+.5,.5,true);}c.restore();}
  for(const n of geometry.junctions)node(c,n.point,n.r,n.alpha*.9);
}
export function drawRelay(canvas,weights,{time=0,reveal=1,animated=true}={}){
  const s=surface(canvas);if(!s)return;const {c,width,height}=s,geometry=relayGeometry(weights,time),scale=relayViewportScale(width,height,geometry);
  c.translate(width/2,height/2);c.scale(scale,scale);
  c.globalAlpha=reveal;glow(c,[0,0],145,.08+geometry.energy*.08);
  if(!geometry.layers.length){orbit(c,{radius:54,tilt:.65,rotation:-.35,reveal:1},.15);orbit(c,{radius:125,tilt:.6,rotation:-.35,reveal:1},.075);}
  c.save();c.scale(.1+.9*reveal,.1+.9*reveal);geometry.layers.forEach(l=>layer(c,l,time,animated));sharedChannels(c,geometry,time,animated);c.restore();
  for(let k=0;k<36;k++){const r=35+(k*71%175),p=orbitPoint(r,k*2.39996,.75);c.fillStyle=`rgba(156,203,255,${(.07+(k%5)*.025)*geometry.energy})`;c.beginPath();c.arc(p[0]+(animated?Math.sin(time*.17+k)*1.5:0),p[1],.55,0,TAU);c.fill();}
  // The single opaque light belongs to FilterSpace; only its halo is painted here.
  glow(c,[0,0],55,.25);
}
export function drawModeMark(canvas,id,selected){
  const s=surface(canvas);if(!s)return;const {c,width,height}=s,g=relayGeometry(new Map([[id,1]])),l=g.layers[0];if(!l)return;
  const b=relayBounds(g,0),scale=Math.min((width-22)/(Math.max(40,b.x)*2),(height-12)/(Math.max(30,b.y)*2));
  c.translate(width/2,height/2);c.scale(scale,scale);c.globalAlpha=selected?.95:.57;layer(c,l,0,false);sharedChannels(c,g,0,false);if([1,3,5].includes(id))node(c,[0,0],3,.8);
}
