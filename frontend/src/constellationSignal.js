// One bounded timeline per constellation. The filter draft never waits for it.
const clamp=t=>Math.max(0,Math.min(1,t));
const smooth=t=>{t=clamp(t);return t*t*(3-2*t);};
export const signalTarget=node=>({x:node.x,y:node.y-15}); // Artwork centre; the label occupies the bottom 30px.
export function startConstellationSignal(node,selected){
 const point=signalTarget(node);
 return {selected,elapsed:0,flightMs:Math.max(640,Math.min(920,540+Math.hypot(point.x,point.y)*.55))};
}
export function constellationSignalFrame(signal,node){
 const delay=signal.selected?0:100,travel=signal.elapsed-delay,t=clamp(travel/signal.flightMs);
 const landed=signal.selected&&travel>=signal.flightMs;
 const burst=landed?clamp((travel-signal.flightMs)/1440):0;
 const point=signalTarget(node),direction=signal.selected?1:-1,u=smooth(t),position=signal.selected?u:1-u;
 const speed=Math.sin(Math.PI*t);
 return {active:landed,phase:landed?'flare':signal.selected?'outbound':'return',burst,
  boost:landed?smooth(burst/.14)*(1-smooth((burst-.14)/.86)):0,
  flight:travel>=0&&travel<signal.flightMs?{
   x:point.x*position,y:point.y*position,
   angle:Math.atan2(point.y*direction,point.x*direction)*180/Math.PI,
   length:38*Math.max(0,speed)**.6,opacity:smooth(t/.06)*smooth((1-t)/.09)
  }:null};
}
export function advanceConstellationSignals(signals,dt){
 const next={};
 for(const [id,signal] of Object.entries(signals)){
  const elapsed=signal.elapsed+Math.max(0,Math.min(48,dt));
  if(elapsed<signal.flightMs+(signal.selected?1440:100))next[id]={...signal,elapsed};
 }
 return next;
}
export function constellationFlareSparks(node){
 const points=node.points||[];if(!points.length)return [];
 const xs=points.map(p=>p.x),ys=points.map(p=>p.y),cx=(Math.min(...xs)+Math.max(...xs))/2,cy=(Math.min(...ys)+Math.max(...ys))/2;
 const rx=(Math.max(...xs)-Math.min(...xs))/2+30,ry=(Math.max(...ys)-Math.min(...ys))/2+22;
 return Array.from({length:18},(_,i)=>{
  const angle=i*Math.PI*(3-Math.sqrt(5))+node.id*1.37,r=.78+.62*Math.sqrt((i+.5)/18);
  return {key:i,cx,cy,dx:Math.cos(angle)*rx*r,dy:Math.sin(angle)*ry*r,radius:.55+(i%5)*.12};
 });
}
export function flareSparkFrame(spark,progress){
 const t=clamp(progress),distance=1-(1-t)**3;
 return {x:spark.cx+spark.dx*distance,y:spark.cy+spark.dy*distance,
  opacity:smooth(t/.12)*(1-smooth((t-.38)/.62))*.58};
}
