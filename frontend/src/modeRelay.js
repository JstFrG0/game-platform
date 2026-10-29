// Geometry is keyed by the saved IGDB tag ID. Display labels never change data.
const LABELS = {1:'单人',2:'多人',3:'合作',4:'分屏',5:'大型多人',6:'大逃杀'};
export const clamp = value => Math.max(0,Math.min(1,value));
export const smooth = value => { const t=clamp(value);return t*t*(3-2*t); };
const TAU=Math.PI*2, mix=(a,b,t)=>a.map((v,i)=>v+(b[i]-v)*t);
export const modeLabel = mode => LABELS[mode.id] || mode.name || `模式 ${mode.id}`;
export function describeModes(records, ids=[]) {
  const result=new Map();
  for(const mode of records)if(Number.isInteger(Number(mode.id))&&Number(mode.id)>=0&&Number(mode.id)<=2147483647){
    const id=Number(mode.id);result.set(id,{...mode,id,label:modeLabel({...mode,id})});
  }
  for(const id of ids)if(!result.has(id))result.set(id,{id,name:null,label:modeLabel({id})});
  return [...result.values()].sort((a,b)=>a.id-b.id);
}
export function modeCaption(ids,options){
  if(!ids.length)return '全部模式';
  if(ids.length>2)return `已选 ${ids.length} 种模式`;
  return ids.map(id=>options.find(m=>m.id===id)?.label||modeLabel({id})).join('、');
}
export function advanceRelay(current, selected, elapsed, immediate=false){
  const target=new Set(selected),dt=Math.max(0,Math.min(80,elapsed));let changed=false;
  for(const id of target)if(!current.has(id))current.set(id,0);
  for(const [id,value] of current){
    const to=target.has(id)?1:0;
    const next=immediate?to:value<to?Math.min(to,value+dt/1250):Math.max(to,value-dt/1050);
    if(next!==value){current.set(id,next);changed=true;}
  }
  return changed;
}
export function orbitPoint(radius,angle,tilt=.6,rotation=-.2){
  const x=Math.cos(angle)*radius,y=Math.sin(angle)*radius*tilt;
  return [x*Math.cos(rotation)-y*Math.sin(rotation),x*Math.sin(rotation)+y*Math.cos(rotation)];
}
export function relayEdgePoint(edge,t){
  if(edge.arc){const a=edge.arc,p=orbitPoint(a.radius,a.start+(a.end-a.start)*t,a.tilt,a.rotation);return [p[0]+(a.center?.[0]||0),p[1]+(a.center?.[1]||0)];}
  return mix(edge.from,edge.to,t);
}
export function relayBounds(geometry,minimum=145){
  let x=minimum,y=minimum;
  for(const layer of geometry.layers){
    for(const n of layer.nodes){x=Math.max(x,Math.abs(n.point[0])+n.r*5);y=Math.max(y,Math.abs(n.point[1])+n.r*5);}
    for(const o of [...layer.orbits,...layer.edges.filter(e=>e.arc).map(e=>e.arc)]){
      if(o.opacity===0)continue;
      const rx=o.radius,ry=o.radius*o.tilt,c=Math.cos(o.rotation),s=Math.sin(o.rotation);
      x=Math.max(x,Math.abs(o.center?.[0]||0)+Math.hypot(rx*c,ry*s)+18);
      y=Math.max(y,Math.abs(o.center?.[1]||0)+Math.hypot(rx*s,ry*c)+18);
    }
  }
  for(const n of geometry.junctions||[]){x=Math.max(x,Math.abs(n.point[0])+n.r*5);y=Math.max(y,Math.abs(n.point[1])+n.r*5);}
  return {x,y};
}
export function relayViewportScale(width,height,geometry){
  const b=relayBounds(geometry),base=Math.min(width/510,height/380)*(1+geometry.density*.06);
  return Math.max(0,Math.min(base,Math.max(0,width/2-12)/b.x,Math.max(0,height/2-12)/b.y));
}
export function relayGeometry(weights,time=0){
  const get=id=>smooth(weights.get(id)||0),split=get(4),coop=get(3),layers=[],channels=[],junctions=[];
  const total=[...weights.values()].reduce((sum,value)=>sum+smooth(value),0),density=smooth((total-3)/3);
  // One invertible projection preserves the planar layout. Different ring
  // attitudes cannot be independently tilted without creating intersections.
  const spacing=.65+.35*density,tilt=.62,rotation=-.18,relayX=100+22*split,gap=.32;
  const project=point=>{const x=point[0]*spacing,y=point[1]*spacing*tilt;return [x*Math.cos(rotation)-y*Math.sin(rotation),x*Math.sin(rotation)+y*Math.cos(rotation)];};
  // Never renumber lanes when a module fades to zero during reverse animation.
  // Reserving its lane makes rapid unselect/reselect follow the exact same path.
  const unknown=[...weights.keys()].filter(id=>id<1||id>6),unknownLane=id=>unknown.indexOf(id);
  const trunk=Math.max(coop,split);
  if(trunk){
    for(const sign of [-1,1]){
      const end=project([sign*relayX,0]);
      channels.push({from:[0,0],to:end,phase:0,sync:true,alpha:trunk});
      junctions.push({point:end,r:3,alpha:trunk});
    }
  }
  for(const [id,value] of [...weights].sort(([a],[b])=>b-a)){
    const p=smooth(value);if(!p)continue;
    const layer={id,alpha:p,nodes:[],edges:[],orbits:[]};
    const node=(point,r=2.8,alpha=1)=>layer.nodes.push({point:project(point),r,alpha});
    const edge=(from,to,phase=0,sync=false)=>layer.edges.push({from:project(from),to:project(to),phase,sync});
    const local=(radius,angle,center=[0,0])=>[center[0]+Math.cos(angle)*radius,center[1]+Math.sin(angle)*radius];
    const ring=(radius,start=0,end=TAU,center=[0,0])=>layer.orbits.push({radius:radius*spacing,tilt,rotation,start,end,reveal:p,center:project(center)});
    const arc=(radius,start,end,phase=0)=>{
      const finish=start+(end-start)*p;
      edge(local(radius,start),local(radius,finish),phase);
      layer.edges.at(-1).arc={radius:radius*spacing,tilt,rotation,start,end:finish};
    };
    const circuit=(radius,count,phase)=>{
      for(let k=0;k<count;k++){const a=phase+k*TAU/count;node(local(radius,a),2.2);arc(radius,a,a+TAU/count,k/count);}
    };
    // Modules reveal ALONG their reserved lanes; radii never sweep across a
    // neighbour while assembling. The whole page may still scale uniformly.
    if(id===1){
      ring(76,gap,Math.PI-gap);ring(76,Math.PI+gap,TAU-gap);
      const angle=gap+(Math.PI-2*gap)*(.5-.5*Math.cos(time*.12))*p;
      node(local(76,angle),3.5);
    }
    else if(id===2){
      circuit(218,6,.25);
    }else if(id===3){
      for(const sign of [-1,1])for(const vertical of [-1,1]){
        const source=[sign*relayX,0],end=[sign*(relayX+54*p),vertical*62*p];
        node(end,3,smooth((p-.15)/.85));edge(source,end,0,true);
      }
    }else if(id===4){
      for(const sign of [-1,1]){
        // Top/bottom arcs leave ports open for both the core trunk and the
        // cooperative fan. These are real openings, never painted-over gaps.
        ring(22,1.08,2.06,[sign*relayX,0]);ring(22,Math.PI+1.08,Math.PI+2.06,[sign*relayX,0]);
      }
    }else if(id===5){
      circuit(316,12,.12);ring(332);
      for(let k=0;k<4;k++){
        const angle=k*TAU/4+.12,outer=local(316,angle),inner=local(316-22*p,angle);
        node(inner,1.8);edge(inner,outer,k/4);
      }
    }else{
      const count=id===6?8:4+(id%4),radius=id===6?268:382+unknownLane(id)*44,phase=.42;
      circuit(radius,count,phase);
      for(let k=0;k<count;k+=2){const angle=k*TAU/count+phase,outer=local(radius,angle),inner=local(radius-22*p,angle);node(inner,1.5);edge(outer,inner,k/count,true);}
    }
    layers.push(layer);
  }
  return {layers,channels,junctions,energy:Math.min(1,total),density};
}
