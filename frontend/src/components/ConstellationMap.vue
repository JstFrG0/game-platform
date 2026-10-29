<script setup>
import {computed,inject,nextTick,onBeforeUnmount,ref,watch} from 'vue';
import {filterSpaceKey,layoutPoint} from '../filterSpace.js';
import {constellationNodes,constellationBurst,constellationDrift,constellationSparks} from '../genreConstellations.js';
import {genreTransitFrame} from '../genreTransit.js';
import {modeTransitFrame} from '../modeTransit.js';
import {startConstellationSignal,constellationSignalFrame,advanceConstellationSignals,constellationFlareSparks,flareSparkFrame} from '../constellationSignal.js';
import {genreGatherPhase,readGatherRoutes,drawGather,clearEffect} from '../genreModeEffects.js';
const props=defineProps({genres:Array,selected:Array,query:String,active:Boolean,disabled:Boolean,initial:Boolean});
const emit=defineEmits(['choose']),space=inject(filterSpaceKey),viewport=ref(null),view=ref({x:0,y:0,zoom:1}),dragging=ref(false),entrance=ref(1);
const motion=window.matchMedia('(prefers-reduced-motion: reduce)'),sky={x:0,y:0};
const reduced=ref(motion.matches);
const paused=ref(false),hidden=ref(document.hidden);
const bounds=ref({width:0,height:0});
const signals=ref({});let signalTime=null;
const gatherCanvas=ref(null),gatherAvailable=ref(true);
let gatherRoutes=null,gatherPaint=null,gatherPrevious=2,gatherDirection=1,gatherDrawn=false;
let gesture=null,suppressedUntil=0,frame=0,target=null,previous=0,camera=false,observer,entranceStart=null,entranceElapsed=0;
const nodes=computed(()=>constellationNodes(props.genres||[],bounds.value).map(n=>({...n,drift:constellationDrift(n.id),sparks:constellationSparks(n),flareSparks:constellationFlareSparks(n)})));
const signalFrames=computed(()=>Object.fromEntries(nodes.value.filter(n=>signals.value[n.id]).map(n=>[n.id,constellationSignalFrame(signals.value[n.id],n)])));
const visuallySelected=n=>signalFrames.value[n.id]?.active??props.selected.includes(n.id);
const flights=computed(()=>nodes.value.flatMap(n=>{const f=signalFrames.value[n.id]?.flight;return f?[{id:n.id,...f}]:[];}));
const flightStyle=f=>({transform:`translate(${f.x}px,${f.y}px) rotate(${f.angle}deg)`,opacity:f.opacity,'--tail-scale':f.length/38});
const flareSparks=n=>n.flareSparks.map(s=>({...s,...flareSparkFrame(s,signalFrames.value[n.id]?.burst||0)}));
const matches=n=>!props.query?.trim()||`${n.name} ${n.label}`.toLocaleLowerCase().includes(props.query.trim().toLocaleLowerCase());
const visible=computed(()=>nodes.value.filter(matches));
const blocked=computed(()=>props.disabled||entrance.value<1);
const exitPhase=computed(()=>{const phase=genreGatherPhase(space.state.progress);return {...phase,active:phase.active&&!reduced.value&&gatherAvailable.value};});
const exitStyle=computed(()=>exitPhase.value.active?{'--exit-handoff':exitPhase.value.handoff,'--exit-lines':exitPhase.value.lines,'--exit-labels':exitPhase.value.labels,'--exit-dust':exitPhase.value.dust}:undefined);
const reveal=computed(()=>Math.min(entrance.value,genreTransitFrame(space.state.progress,0,{x:0,y:0},{x:0,y:0}).reveal)*(gatherAvailable.value?1:modeTransitFrame(space.state.progress,0,{x:0,y:0},{x:0,y:0}).gather));
const resting=computed(()=>props.active&&!props.disabled&&reveal.value===1&&!reduced.value);
const worldStyle=computed(()=>({transform:`translate(${view.value.x}px,${view.value.y}px) scale(${view.value.zoom})`,'--reveal':reveal.value,
 '--burst-flash':reduced.value?0:Math.sin(Math.PI*Math.min(1,reveal.value/.38))**2,'--burst-ring':.15+reveal.value*2.8}));
const nodeStyle=n=>{const b=constellationBurst(n,reveal.value,reduced.value);return {
 '--node-x':`${b.x}px`,'--node-y':`${b.y}px`,'--card-width':`${n.width}px`,'--card-height':`${n.height}px`,'--depth':n.depth,
 '--launch-scale':b.scale,'--node-opacity':b.opacity,'--label-opacity':b.labelOpacity,'--node-yaw':`${b.yaw}deg`,'--node-roll':`${b.roll}deg`,
 '--drift-duration':`${n.drift.duration}s`,'--drift-delay':`${n.drift.delay}s`,'--drift-x':`${n.drift.x}px`,'--drift-y':`${n.drift.y}px`,
 '--drift-yaw':`${n.drift.yaw}deg`,'--drift-roll':`${n.drift.roll}deg`,'--signal-boost':signalFrames.value[n.id]?.boost||0};};
const sparkStyle=s=>({'--spark-x':`${s.dx}px`,'--spark-y':`${s.dy}px`,'--spark-duration':`${s.duration}ms`,'--spark-delay':`${s.delay}ms`,
 '--dust-x':`${s.swayX}px`,'--dust-y':`${s.swayY}px`,'--dust-duration':`${s.driftDuration}ms`,'--dust-delay':`${s.duration+s.delay}ms`});
function stop(){cancelAnimationFrame(frame);frame=0;target=null;camera=false;}
function assign(next){if(camera){sky.x+=next.x-view.value.x;sky.y+=next.y-view.value.y;}view.value=next;}
function tick(now){frame=0;if(!target)return;const dt=Math.max(0,Math.min(48,now-previous));previous=now;const a=1-Math.exp(-dt/(camera?38:70)),v=view.value;
 const next=Object.fromEntries(['x','y','zoom'].map(k=>[k,v[k]+(target[k]-v[k])*a]));
 if(Math.hypot(next.x-target.x,next.y-target.y)<.1&&Math.abs(next.zoom-target.zoom)<.0001){assign(target);target=null;camera=false;return;}
 assign(next);frame=requestAnimationFrame(tick);
}
function move(next,pan=false,animate=true){if(motion.matches||!animate){stop();camera=pan;assign(next);camera=false;return;}target=next;camera=pan;if(!frame){previous=performance.now();frame=requestAnimationFrame(tick);}}
function home(animate=false){if(viewport.value)move({x:viewport.value.clientWidth/2,y:(viewport.value.clientHeight-64)/2,zoom:1},false,animate);}
function fit(){if(!viewport.value||!nodes.value.length)return home(true);const list=nodes.value,minX=Math.min(0,...list.map(n=>n.x-n.width/2-8)),maxX=Math.max(0,...list.map(n=>n.x+n.width/2+8)),minY=Math.min(0,...list.map(n=>n.y-n.height/2-8)),maxY=Math.max(0,...list.map(n=>n.y+n.height/2+8));
 const w=viewport.value.clientWidth,h=viewport.value.clientHeight-64,z=Math.max(.4,Math.min(1,(w-70)/(maxX-minX),(h-30)/(maxY-minY)));move({x:w/2-(minX+maxX)/2*z,y:h/2-(minY+maxY)/2*z,zoom:z});}
function zoom(factor){const v=target||view.value,w=viewport.value.clientWidth/2,h=viewport.value.clientHeight/2,z=Math.max(.4,Math.min(1.4,v.zoom*factor)),ratio=z/v.zoom;move({x:w-(w-v.x)*ratio,y:h-(h-v.y)*ratio,zoom:z});}
function ensureVisible(n){if(!n||!viewport.value)return;const v=view.value,x=v.x+n.x*v.zoom,y=v.y+n.y*v.zoom,mx=(n.width/2+12)*v.zoom,my=(n.height/2+12)*v.zoom;
 if(x<mx||x>viewport.value.clientWidth-mx||y<my||y>viewport.value.clientHeight-64-my)move({...v,x:viewport.value.clientWidth/2-n.x*v.zoom,y:(viewport.value.clientHeight-64)/2-n.y*v.zoom});}
function cancel(){const old=gesture;gesture=null;dragging.value=false;if(old?.active)suppressedUntil=performance.now()+350;if(old?.element.hasPointerCapture(old.pointer))old.element.releasePointerCapture(old.pointer);}
function settleSignals(){if(Object.keys(signals.value).length)signals.value={};signalTime=null;}
function captureGather(){
 if(!viewport.value)return;
 gatherRoutes=readGatherRoutes(viewport.value,{x:view.value.x,y:view.value.y});gatherPaint=null;
 if(gatherCanvas.value)gatherCanvas.value.dataset.gatherCount=String(gatherRoutes.length);
}
function paintGather(){
 const progress=space.state.progress;
 if(progress!==gatherPrevious){gatherDirection=progress>gatherPrevious?1:-1;gatherPrevious=progress;}
 if(!props.active||!exitPhase.value.active){
  if(gatherDrawn){clearEffect(gatherCanvas.value);gatherDrawn=false;}
  gatherPaint=null;return;
 }
 if(document.hidden)return;
 if(gatherPaint===progress)return;
 if(!gatherRoutes)captureGather();
 if(!gatherCanvas.value?.clientWidth)return;
 gatherAvailable.value=drawGather(gatherCanvas.value,gatherRoutes||[],progress,gatherDirection,window.devicePixelRatio||1);
 gatherDrawn=true;gatherPaint=progress;
}
function freeze(){
 cancel();stop();settleSignals();
 if(space.state.progress===2)captureGather();
 else if(space.state.progress===3){gatherRoutes=null;gatherPaint=null;}
 gatherPrevious=space.state.progress;
}
function startPan(e){if(blocked.value||e.button!==0||gesture)return;stop();gesture={pointer:e.pointerId,element:e.target.closest('button')||e.currentTarget,x:e.clientX,y:e.clientY,view:{...view.value},active:false};gesture.element.setPointerCapture(e.pointerId);}
function moving(e){if(!gesture||gesture.pointer!==e.pointerId)return;const dx=e.clientX-gesture.x,dy=e.clientY-gesture.y;if(!gesture.active&&Math.hypot(dx,dy)<5)return;e.preventDefault();gesture.active=true;dragging.value=true;move({...gesture.view,x:gesture.view.x+dx,y:gesture.view.y+dy},true);}
function endPan(e){if(gesture?.pointer===e.pointerId){moving(e);cancel();}}
function choose(n,e){if(blocked.value||(e.detail>0&&performance.now()<suppressedUntil))return;emit('choose',n.id,!props.selected.includes(n.id));}
function keys(n,e){if(!['ArrowLeft','ArrowRight'].includes(e.key)||e.ctrlKey||e.metaKey||e.altKey||blocked.value)return;e.preventDefault();const d=e.key==='ArrowRight'?1:-1;
 const candidate=visible.value.filter(item=>d*(item.x-n.x)>1).sort((a,b)=>(Math.abs(a.y-n.y)*2+Math.abs(a.x-n.x))-(Math.abs(b.y-n.y)*2+Math.abs(b.x-n.x)))[0];
 if(candidate)viewport.value.querySelector(`[data-genre="${candidate.id}"]`)?.focus({preventScroll:true});}
function paint(now){
 paintGather();
 if(!props.active||props.disabled||document.hidden){entranceStart=null;signalTime=null;return;}
 if(motion.matches){entrance.value=1;settleSignals();return;}
 if(entrance.value<1){entranceStart??=now;entranceElapsed+=Math.max(0,Math.min(120,now-entranceStart));entranceStart=now;const t=Math.min(1,entranceElapsed/1050);entrance.value=t*t*(3-2*t);}
 if(paused.value){signalTime=null;return;}
 if(Object.keys(signals.value).length){const dt=signalTime===null?0:now-signalTime;signals.value=advanceConstellationSignals(signals.value,dt);}
 signalTime=now;
}
function visibilityChanged(){entranceStart=null;signalTime=null;hidden.value=document.hidden;}
function changedMotion(){reduced.value=motion.matches;gatherRoutes=null;gatherPaint=null;if(motion.matches){clearEffect(gatherCanvas.value);entrance.value=1;settleSignals();if(target){const final=target;assign(final);stop();}}}
watch(()=>props.selected,(next,old)=>{
 if(!old||!props.active||props.disabled||motion.matches){settleSignals();return;}
 const before=new Set(old),after=new Set(next),updates={...signals.value};
 for(const n of nodes.value)if(before.has(n.id)!==after.has(n.id)){
  if(paused.value)delete updates[n.id];else updates[n.id]=startConstellationSignal(n,after.has(n.id));
 }
 signals.value=updates;
},{flush:'sync'});
watch(()=>props.active,async active=>{freeze();gatherRoutes=null;gatherPaint=null;if(!active)return;entrance.value=props.initial&&!motion.matches?0:1;entranceStart=null;entranceElapsed=0;await nextTick();home();},{immediate:true});
watch(()=>props.query,()=>{if(props.query?.trim())ensureVisible(visible.value[0]);});
watch(()=>props.disabled,disabled=>{if(disabled)freeze();});
nextTick(()=>{if(viewport.value){observer=new ResizeObserver(()=>{freeze();bounds.value={width:viewport.value.clientWidth,height:Math.max(1,viewport.value.clientHeight-64)};home();gatherRoutes=null;gatherPaint=null;nextTick(()=>{if(exitPhase.value.active){captureGather();paintGather();}});});observer.observe(viewport.value);}});
motion.addEventListener('change',changedMotion);document.addEventListener('visibilitychange',visibilityChanged);
defineExpose({freeze,paint,busy:()=>entrance.value<1,core:()=>layoutPoint(viewport.value,view.value.x,view.value.y),panOffset:()=>({...sky}),focusBase:()=>viewport.value?.focus({preventScroll:true})});
onBeforeUnmount(()=>{freeze();observer?.disconnect();motion.removeEventListener('change',changedMotion);document.removeEventListener('visibilitychange',visibilityChanged);});
</script>
<template>
 <div class="constellation-map" :class="{'is-resting':resting,'is-idle-paused':paused||hidden||dragging,'is-page-hidden':hidden,'is-mode-transit':exitPhase.active}" :style="exitStyle">
  <div ref="viewport" class="constellation-viewport" tabindex="-1" role="group" aria-label="玩法类型星图，可拖动浏览，点击星座多选" :class="{'is-dragging':dragging}" @pointerdown="startPan" @pointermove="moving" @pointerup="endPan" @pointercancel="freeze" @lostpointercapture="gesture && freeze()">
   <div class="constellation-world" :style="worldStyle">
    <span class="constellation-burst-glow" aria-hidden="true"></span>
    <button v-for="n in nodes" :key="n.id" type="button" role="checkbox" class="constellation-node" :data-genre="n.id" :data-signal="signalFrames[n.id]?.phase||'idle'" :class="{selected:visuallySelected(n),'is-picked':selected.includes(n.id),'is-dimmed':!matches(n)}" :style="nodeStyle(n)" :aria-checked="selected.includes(n.id)" :aria-label="n.label" :title="n.name" :disabled="blocked || (!selected.includes(n.id) && selected.length>=100) || (!matches(n) && !selected.includes(n.id))" @click="choose(n,$event)" @keydown="keys(n,$event)" @focus="($event.target.ownerDocument.documentElement.hasAttribute('data-keyboard-focus')) && ensureVisible(n)">
     <span class="constellation-art" aria-hidden="true"><span class="constellation-float"><span class="constellation-aura"></span><svg viewBox="0 0 210 112"><path class="constellation-thread" :d="n.path" pathLength="1"/><g v-for="(point,i) in n.points" :key="i" class="constellation-point"><circle class="star-haze" :cx="point.x" :cy="point.y" :r="point.r*3.3"/><circle class="star-halo" :cx="point.x" :cy="point.y" :r="point.r*2"/><circle :cx="point.x" :cy="point.y" :r="point.r"/></g><Transition name="constellation-dust"><g v-if="active&&visuallySelected(n)" class="constellation-selection-particles"><g v-for="spark in n.sparks" :key="spark.key" :data-dust="spark.key" :transform="`translate(${spark.x} ${spark.y})`" :style="sparkStyle(spark)"><g class="constellation-dust-launch"><circle class="constellation-spark" cx="0" cy="0" :r="spark.radius"/></g></g></g></Transition><g v-if="signalFrames[n.id]?.phase==='flare'" class="constellation-flare-particles"><circle v-for="spark in flareSparks(n)" :key="spark.key" :cx="spark.x" :cy="spark.y" :r="spark.radius" :opacity="spark.opacity"/></g></svg></span></span>
     <span class="constellation-label" :title="n.label">{{n.label}}</span>
    </button>
    <span v-for="flight in flights" :key="flight.id" class="constellation-signal" :data-signal-flight="flight.id" :style="flightStyle(flight)" aria-hidden="true"><i class="constellation-signal-tail"></i><i class="constellation-signal-head"></i></span>
    <span class="genre-center" aria-hidden="true"></span>
   </div>
   <canvas v-show="exitPhase.active" ref="gatherCanvas" class="constellation-gather" aria-hidden="true"></canvas>
   <p v-if="!visible.length" class="genre-no-matches" role="status">没有匹配的玩法类型</p>
  </div>
  <div class="genre-view-controls" aria-label="星图视图"><button class="genre-motion-toggle" type="button" :disabled="blocked||reduced" :aria-pressed="paused" :aria-label="paused?'恢复星座漂浮':'暂停星座漂浮'" :title="reduced?'已遵循系统减少动态效果设置':paused?'恢复星座漂浮':'暂停星座漂浮'" @click="paused=!paused"><svg viewBox="0 0 20 20" aria-hidden="true"><path v-if="paused||reduced" d="m7 4 9 6-9 6Z" fill="currentColor"/><path v-else d="M6 4v12M14 4v12" fill="none" stroke="currentColor" stroke-width="2"/></svg></button><button type="button" :disabled="blocked" aria-label="缩小星图" @click="zoom(.85)">−</button><button type="button" :disabled="blocked" aria-label="放大星图" @click="zoom(1.18)">+</button><button type="button" :disabled="blocked" @click="fit">适应</button></div>
 </div>
</template>
<style scoped>
.constellation-map{position:relative;flex:1;min-width:0;min-height:0}.constellation-viewport{position:absolute;inset:0;overflow:hidden;touch-action:none;cursor:grab;mask-image:linear-gradient(transparent,#000 3%,#000 94%,transparent)}.constellation-viewport.is-dragging,.constellation-viewport.is-dragging button{cursor:grabbing}.constellation-world{position:absolute;left:0;top:0;transform-origin:0 0}
.constellation-gather{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:2}
.is-mode-transit .constellation-point{opacity:calc(1 - var(--exit-handoff))}
.is-mode-transit .constellation-thread{opacity:calc(.38 * var(--exit-lines));transition:none}
.is-mode-transit .constellation-node.selected .constellation-thread{opacity:calc(.78 * var(--exit-lines))}
.is-mode-transit .constellation-label{opacity:var(--exit-labels)}
.is-mode-transit .constellation-selection-particles,.is-mode-transit .constellation-node.selected .constellation-aura{opacity:var(--exit-dust);transition:none}
.is-mode-transit .constellation-float{animation:constellation-idle var(--drift-duration) ease-in-out var(--drift-delay) infinite both;animation-play-state:paused}
.constellation-node{position:absolute;left:0;top:0;width:var(--card-width);height:var(--card-height);padding:0;border:0;border-radius:30%;background:transparent!important;box-shadow:none!important;cursor:pointer;color:#9aa9c5;touch-action:none;transform:translate(var(--node-x),var(--node-y)) translate(-50%,-50%) scale(var(--launch-scale));opacity:var(--node-opacity);transition:color 220ms}
.constellation-node:disabled{cursor:default;opacity:var(--node-opacity)}.constellation-node.is-dimmed:not(.is-picked){opacity:calc(var(--node-opacity) * .09)}
.constellation-art{position:relative;display:block;width:100%;height:calc(var(--card-width) * .54);pointer-events:none}
.constellation-float{position:absolute;inset:0;transform:translate3d(0,0,0);transform-origin:center}
.is-resting .constellation-float{animation:constellation-idle var(--drift-duration) ease-in-out var(--drift-delay) infinite both}
.is-idle-paused .constellation-float,.constellation-node:hover .constellation-float,.constellation-node:focus-visible .constellation-float,.constellation-node.is-dimmed:not(.selected) .constellation-float{animation-play-state:paused}
.constellation-aura{position:absolute;left:50%;top:50%;width:96%;height:86%;border-radius:50%;pointer-events:none;background:radial-gradient(ellipse,#90b8ff16,transparent 70%);opacity:0;transform:translate(-50%,-50%) scale(.86);transition:opacity 420ms,transform 650ms ease}
.constellation-aura::after{content:'';position:absolute;inset:12% 6%;border:1px solid transparent;border-top-color:#a9cfff30;border-bottom-color:#8aafff18;border-radius:50%;transform:rotate(-14deg)}
.constellation-node.selected .constellation-aura{opacity:1;transform:translate(-50%,-50%) scale(calc(1 + var(--signal-boost) * .26));background:radial-gradient(ellipse,rgb(144 184 255 / calc(.086 + var(--signal-boost) * .07)),transparent 70%)}
.constellation-art svg{position:absolute;left:50%;top:50%;display:block;width:80%;height:auto;overflow:visible;transform:translate(-50%,-50%) perspective(650px) rotateY(var(--node-yaw)) rotateZ(var(--node-roll)) scale(var(--depth));transform-origin:center}
.constellation-node circle{fill:#b3c7ed;transition:fill 240ms,opacity 300ms}.constellation-node .star-haze{opacity:.04}.constellation-node .star-halo{opacity:.08}.constellation-node.selected .star-haze{opacity:calc(.10 + var(--signal-boost) * .09)}.constellation-node.selected .star-halo{opacity:calc(.23 + var(--signal-boost) * .14)}
.constellation-thread{fill:none;stroke:#7d94bf;stroke-width:1;opacity:.38;transition:opacity 220ms,stroke 220ms}.constellation-node:hover:not(:disabled),.constellation-node.selected{color:#d2dff9}.constellation-node:hover:not(:disabled) .constellation-thread{opacity:.7}.constellation-node.selected .constellation-thread{stroke:#b2c6ef;opacity:.78}.constellation-node.selected circle{fill:#e1e8ff}
.constellation-label{display:flex;justify-content:center;align-items:center;margin:5px 0 0;padding:0 4px;font-size:15px;line-height:1.35;white-space:nowrap;opacity:var(--label-opacity);transform:none;overflow:hidden;text-overflow:ellipsis}
.constellation-node.selected .constellation-float{filter:brightness(calc(1 + var(--signal-boost) * .22))}
.constellation-node.selected .constellation-thread{opacity:calc(.78 + var(--signal-boost) * .16)}
.constellation-node .constellation-flare-particles circle{fill:#c8dfff;transition:none;pointer-events:none}
.constellation-signal{position:absolute;left:0;top:0;width:0;height:0;pointer-events:none;z-index:1}
.constellation-signal-head{position:absolute;left:-2.5px;top:-2.5px;width:5px;height:5px;border-radius:50%;background:#e1eeff;box-shadow:0 0 5px #bcdcffb3,0 0 13px #87b5ff50}
.constellation-signal-tail{position:absolute;right:1px;top:-4px;width:38px;height:8px;border-radius:50%;background:linear-gradient(90deg,transparent,#a9ceff09 28%,#bcdcff55 92%,#d4e8ff80);transform:scaleX(var(--tail-scale));transform-origin:right center}
.constellation-selection-particles{pointer-events:none;opacity:1}
.constellation-dust-launch{transform:translate(var(--spark-x),var(--spark-y));opacity:.65;animation:constellation-dust-emerge var(--spark-duration) cubic-bezier(.16,.6,.3,1) var(--spark-delay) both}
.constellation-node .constellation-spark{fill:#d4e7ff;pointer-events:none;transform-box:fill-box;transform-origin:center;transform:translate(0,0);opacity:.65;transition:none;animation:constellation-dust-drift var(--dust-duration) ease-in-out var(--dust-delay) infinite both}
.constellation-map:not(.is-resting) .constellation-dust-launch,.constellation-map:not(.is-resting) .constellation-spark,.is-page-hidden .constellation-dust-launch,.is-idle-paused .constellation-dust-launch,.is-idle-paused .constellation-spark,.constellation-node:hover .constellation-spark,.constellation-node:focus-visible .constellation-spark,.constellation-node.is-dimmed:not(.selected) .constellation-spark{animation-play-state:paused}
.constellation-dust-enter-active,.constellation-dust-leave-active{transition:opacity 360ms ease}
.constellation-dust-enter-from,.constellation-dust-leave-to{opacity:0}
@keyframes constellation-dust-emerge{0%{opacity:0;transform:translate(0,0)}100%{opacity:.65;transform:translate(var(--spark-x),var(--spark-y))}}
@keyframes constellation-dust-drift{0%,100%{opacity:.65;transform:translate(0,0) scale(.85)}35%{opacity:.95;transform:translate(var(--dust-x),var(--dust-y)) scale(1)}70%{opacity:.7;transform:translate(calc(var(--dust-x) * -.5),calc(var(--dust-y) * .4)) scale(.8)}}
.constellation-burst-glow{position:absolute;left:0;top:0;width:90px;height:90px;border-radius:50%;pointer-events:none;background:radial-gradient(circle,#bcdcff38,transparent 67%);box-shadow:inset 0 0 0 1px #a2c7fa22;opacity:var(--burst-flash);transform:translate(-50%,-50%) scale(var(--burst-ring))}
.genre-center{position:absolute;left:0;top:0;width:10px;height:10px;transform:translate(-50%,-50%);border-radius:50%;background:#d4e7ff;box-shadow:0 0 8px #abd3ffbb,0 0 28px #8c8ee955;pointer-events:none}.genre-no-matches{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);margin:32px 0;color:#9ba6c0;font-size:14px;pointer-events:none}
.genre-view-controls{position:absolute;right:12px;bottom:12px;display:flex;gap:6px}.genre-view-controls button{min-width:44px;height:44px;padding:0 12px;background:#121522dd;border-color:#30364c;color:#afbfda}
.genre-motion-toggle{display:grid;place-items:center}.genre-motion-toggle svg{width:17px;height:17px}
@keyframes constellation-idle{0%,100%{transform:translate3d(0,0,0) rotateY(0deg) rotateZ(0deg)}25%{transform:translate3d(var(--drift-x),var(--drift-y),0) rotateY(var(--drift-yaw)) rotateZ(var(--drift-roll))}50%{transform:translate3d(calc(var(--drift-x) * -.55),calc(var(--drift-y) * .35),0) rotateY(calc(var(--drift-yaw) * -.65)) rotateZ(calc(var(--drift-roll) * -.55))}75%{transform:translate3d(calc(var(--drift-x) * .4),calc(var(--drift-y) * -.8),0) rotateY(calc(var(--drift-yaw) * .45)) rotateZ(calc(var(--drift-roll) * .6))}}
@media(max-width:760px){.constellation-label{font-size:16px}.genre-view-controls{right:4px;bottom:4px}}
@media(prefers-reduced-motion:reduce){.constellation-float,.constellation-dust-launch,.constellation-spark{animation:none!important}.constellation-node,.constellation-node circle,.constellation-thread,.constellation-aura,.constellation-dust-enter-active,.constellation-dust-leave-active{transition:none}}
@media(forced-colors:active){.constellation-aura,.constellation-selection-particles,.constellation-flare-particles,.constellation-signal{display:none}.constellation-node.selected .constellation-label{color:Highlight;text-decoration:underline double;text-underline-offset:4px}.constellation-thread{stroke:CanvasText}.constellation-node circle{fill:CanvasText}}
</style>
