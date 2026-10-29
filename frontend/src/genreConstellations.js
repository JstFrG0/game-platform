const names={'Point-and-click':'点击冒险',Fighting:'格斗',Shooter:'射击',Music:'音乐',Platform:'平台跳跃',Puzzle:'解谜',Racing:'竞速','Real Time Strategy (RTS)':'即时战略','Role-playing (RPG)':'角色扮演（RPG）',Simulator:'模拟',Sport:'体育',Strategy:'策略','Turn-based strategy (TBS)':'回合制策略',Tactical:'战术','Hack and slash/Beat em up':'砍杀／清版动作','Quiz/Trivia':'问答',Pinball:'弹球',Adventure:'冒险',Indie:'独立',Arcade:'街机','Visual Novel':'视觉小说','Card & Board Game':'卡牌与桌游',MOBA:'多人在线战术竞技'};
export const genreLabel=genre=>{const key=typeof genre.name==='string'?genre.name.replace(/[’']/g,''):'';return Object.hasOwn(names,key)?names[key]:genre.name||`类型 ${genre.id}`;};
const random=(id,salt)=>{const n=Math.sin(id*127.1+salt*311.7)*43758.5453;return n-Math.floor(n);};
const shapes=[[[24,70],[62,26],[104,50],[148,22],[187,68],[139,88]],[[28,30],[62,65],[113,83],[151,47],[185,27]],[[25,50],[69,28],[103,76],[153,86],[185,39],[125,32]],[[33,80],[68,43],[113,20],[157,44],[181,83],[103,66]],[[25,35],[70,69],[110,31],[151,68],[186,42]],[[30,70],[70,31],[111,60],[155,24],[181,63],[147,86],[92,87]]];
export function constellationNodes(options,bounds){
 const slots=[];let field=null;
 if(bounds?.width>0 && bounds?.height>0){
  const count=options.length,columns=Math.max(1,Math.min(Math.floor(bounds.width/220)||1,Math.round(Math.sqrt((count+1)*bounds.width/bounds.height))));
  const rows=Math.max(1,Math.ceil((count+1)/columns)),width=Math.max(bounds.width,columns*220),height=Math.max(bounds.height,rows*148),cw=width/columns,ch=height/rows;
  const cardWidth=Math.min(190,cw-50),cardHeight=cardWidth*.54+30;field={width,height};
  for(let y=0;y<rows;y++)for(let x=0;x<columns;x++){
   const px=(x+.5-columns/2)*cw,py=(y+.5-rows/2)*ch;
   if(Math.abs(px)<cw*.3&&Math.abs(py)<ch*.3)continue;
   slots.push({x:px,y:py,width:cardWidth,height:cardHeight,jitterX:Math.min(24,(cw-cardWidth)/2-8),jitterY:Math.max(0,Math.min(18,(ch-cardHeight)/2-6))});
  }
  // Keep coverage over the full field when the last row is not complete.
  const spread=Array.from({length:count},(_,i)=>slots[Math.floor((i+.5)*slots.length/count)]);
  slots.splice(0,slots.length,...spread.sort((a,b)=>random(a.x+a.y,61)-random(b.x+b.y,61)));
 }else for(let ring=1;slots.length<options.length;ring++){
  const edge=[];for(let y=-ring;y<=ring;y++)for(let x=-ring;x<=ring;x++)if(Math.max(Math.abs(x),Math.abs(y))===ring)edge.push({x,y});
  edge.sort((a,b)=>Math.atan2(a.y,a.x)-Math.atan2(b.y,b.x));slots.push(...edge.map(p=>({x:p.x*300,y:p.y*200,width:230,height:154.2,jitterX:20,jitterY:16})));
 }
 const nodes=[...options].sort((a,b)=>a.id-b.id).map((genre,i)=>{
  const points=shapes[genre.id%shapes.length].map(([x,y],j)=>({x:x+(random(genre.id,j+1)-.5)*10,y:y+(random(genre.id,j+10)-.5)*10,r:1.5+random(genre.id,j+20)*1.6}));
  const slot=slots[i];
  return {...genre,label:genreLabel(genre),x:slot.x+(random(genre.id,50)*2-1)*slot.jitterX,y:slot.y+(random(genre.id,51)*2-1)*slot.jitterY,
   width:slot.width,height:slot.height,depth:.94+random(genre.id,40)*.12,yaw:(random(genre.id,52)*2-1)*34,roll:(random(genre.id,53)*2-1)*18,
   launch:(random(genre.id,54)*2-1),points,path:points.map((p,j)=>`${j?'L':'M'} ${p.x} ${p.y}`).join(' ')};
 });
 if(field)for(let pass=0;pass<12;pass++)for(const n of nodes){
  const x=Math.max(-field.width/2+n.width/2+8,Math.min(field.width/2-n.width/2-8,n.x+(random(n.id,80+pass*2)*2-1)*58));
  const y=Math.max(-field.height/2+n.height/2+8,Math.min(field.height/2-n.height/2-8,n.y+(random(n.id,81+pass*2)*2-1)*44));
  if(Math.abs(x)<n.width/2+6&&Math.abs(y)<n.height/2+6)continue;
  if(nodes.every(other=>other===n || Math.abs(x-other.x)>=(n.width+other.width)/2+10 || Math.abs(y-other.y)>=(n.height+other.height)/2+10)){n.x=x;n.y=y;}
 }
 return nodes;
}
const clamp=value=>Math.max(0,Math.min(1,value));
const smooth=value=>{const t=clamp(value);return t*t*(3-2*t);};
export function constellationBurst(node,progress,reduced=false){
 const t=reduced?1:clamp(progress),flight=1-(1-t)**3,spread=flight+Math.sin(Math.PI*t)*.035;
 return {x:node.x*spread,y:node.y*spread,scale:.025+.975*flight,opacity:smooth(t/.1),labelOpacity:smooth((t-.12)/.34),
  yaw:node.yaw+node.launch*32*(1-flight),roll:node.roll+node.launch*42*(1-flight)};
}
export function constellationDrift(id){
 return {duration:14+random(id,130)*8,delay:random(id,131)*2.4,
  x:(1.4+random(id,132)*1.2)*(random(id,133)<.5?-1:1),y:(1.8+random(id,134)*1.2)*(random(id,135)<.5?-1:1),
  yaw:(.8+random(id,136)*.8)*(random(id,137)<.5?-1:1),roll:(.35+random(id,138)*.45)*(random(id,139)<.5?-1:1)};
}
export function constellationSparks(node){
 const points=node.points||[];if(!points.length)return [];
 const minX=Math.min(...points.map(p=>p.x)),maxX=Math.max(...points.map(p=>p.x)),minY=Math.min(...points.map(p=>p.y)),maxY=Math.max(...points.map(p=>p.y));
 const cx=(minX+maxX)/2,cy=(minY+maxY)/2,rx=Math.max(56,(maxX-minX)/2+30),ry=Math.max(36,(maxY-minY)/2+22);
 // Equal-area radial bands and golden-angle turns spread a fixed field
 // through the whole shape and its outskirts, independently of star count.
 const count=24,turn=Math.PI*(3-Math.sqrt(5)),phase=random(node.id,400)*Math.PI*2;
 return Array.from({length:count},(_,i)=>{
  const salt=420+i*12,r=Math.sqrt((i+.35+random(node.id,salt)*.3)/count),angle=i*turn+phase+(random(node.id,salt+1)-.5)*.16;
  const x=Math.cos(angle)*rx*r,y=Math.sin(angle)*ry*r;
  return {key:`dust-${i}`,x:cx+x*.62,y:cy+y*.62,dx:x*.38,dy:y*.38,
   radius:.65+random(node.id,salt+3)*.6,delay:random(node.id,salt+4)*60,duration:720+random(node.id,salt+5)*280,
   swayX:(2+random(node.id,salt+7)*2)*(random(node.id,salt+8)<.5?-1:1),swayY:(2+random(node.id,salt+9)*2)*(random(node.id,salt+10)<.5?-1:1),
   driftDuration:6000+random(node.id,salt+11)*5000};
 });
}
