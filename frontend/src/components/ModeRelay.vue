<script setup>
import { filterMotion } from '../filterMotion.js';
import {computed,inject,nextTick,onBeforeUnmount,ref,watch} from 'vue';
import {filterSpaceKey,layoutPoint} from '../filterSpace.js';
import {advanceRelay} from '../modeRelay.js';
import {drawModeMark,drawRelay} from '../modeRelayCanvas.js';
import {modeTransitFrame} from '../modeTransit.js';
import {drawModeScan,clearEffect} from '../genreModeEffects.js';
const props=defineProps({modes:Array,selected:Array,active:Boolean,disabled:Boolean,initial:Boolean});
const emit=defineEmits(['choose']),space=inject(filterSpaceKey,null),stage=ref(null),canvas=ref(null),paused=ref(false),unavailable=ref(false),entrance=ref(1);
const motion=filterMotion,reduced=ref(motion.matches),marks=new Map(),weights=new Map();
const scanCanvas=ref(null),scan=computed(()=>reduced.value?0:space?modeTransitFrame(space.state.progress,0,{x:0,y:0},{x:0,y:0}).scan:0);
let observer,dirty=true,previous=null,time=0,localFrame=0;
const left=computed(()=>props.modes.slice(0,Math.ceil(props.modes.length/2))),right=computed(()=>props.modes.slice(Math.ceil(props.modes.length/2)));
const reveal=computed(()=>Math.min(entrance.value,space?modeTransitFrame(space.state.progress,0,{x:0,y:0},{x:0,y:0}).reveal:1));
const visible=()=>!space||modeTransitFrame(space.state.progress,0,{x:0,y:0},{x:0,y:0}).modeOpacity>0;
const blocked=computed(()=>props.disabled||entrance.value<1);
function choose(mode){if(!blocked.value)emit('choose',mode.id,!props.selected.includes(mode.id));}
function focusBase(){(stage.value?.querySelector('button:not(:disabled)')||stage.value)?.focus({preventScroll:true});}
function freeze(){previous=null;}
function paint(now=performance.now()){
  if(!props.active||document.hidden||!visible()){previous=null;return;}
  const dt=previous===null?0:Math.max(0,Math.min(80,now-previous));previous=now;
  if(entrance.value<1){entrance.value=reduced.value?1:Math.min(1,entrance.value+dt/1050);dirty=true;}
  const animated=!paused.value&&!reduced.value&&!props.disabled&&entrance.value===1;
  if(animated)time+=dt/1000;
  const changing=advanceRelay(weights,props.selected,dt,reduced.value||paused.value);
  if(!dirty&&!changing&&!animated)return;
  dirty=false;
  try{
    drawRelay(canvas.value,weights,{time,reveal:reveal.value,animated:!reduced.value});
    if(scan.value>0)drawModeScan(scanCanvas.value,space.state.progress,window.devicePixelRatio||1);else clearEffect(scanCanvas.value);
    for(const mode of props.modes)drawModeMark(marks.get(mode.id),mode.id,props.selected.includes(mode.id));
  }catch{unavailable.value=true;}
}
function tick(now){paint(now);if(props.active&&!space)localFrame=requestAnimationFrame(tick);}
function motionChanged(){
  const restore=stage.value?.contains(document.activeElement)&&document.activeElement?.classList.contains('mode-motion-toggle');
  reduced.value=motion.matches;if(reduced.value)entrance.value=1;dirty=true;
  if(restore&&reduced.value)nextTick(focusBase);
}
watch(()=>props.selected.join(','),()=>{dirty=true;});
watch(()=>props.modes,()=>{dirty=true;},{deep:true});
watch(reveal,()=>{dirty=true;});
watch(scan,()=>{dirty=true;});
watch(()=>props.disabled,()=>{previous=null;dirty=true;});
watch(paused,()=>{previous=null;dirty=true;});
watch(()=>props.active,async active=>{
  cancelAnimationFrame(localFrame);previous=null;
  if(!active){weights.clear();entrance.value=1;return;}
  weights.clear();for(const mode of props.modes)weights.set(mode.id,props.selected.includes(mode.id)?1:0);
  for(const id of props.selected)if(!weights.has(id))weights.set(id,1);
  entrance.value=props.initial&&!reduced.value?0:1;time=0;dirty=true;unavailable.value=false;
  await nextTick();if(!props.active)return;
  if(!space)localFrame=requestAnimationFrame(tick);
},{immediate:true});
nextTick(()=>{if(stage.value){observer=new ResizeObserver(()=>{dirty=true;previous=null;});observer.observe(stage.value);}});
motion.addEventListener('change',motionChanged);document.addEventListener('visibilitychange',freeze);
defineExpose({paint,freeze,core:()=>layoutPoint(canvas.value),busy:()=>entrance.value<1,focusBase});
onBeforeUnmount(()=>{cancelAnimationFrame(localFrame);observer?.disconnect();motion.removeEventListener('change',motionChanged);document.removeEventListener('visibilitychange',freeze);marks.clear();});
</script>
<template>
 <div ref="stage" class="mode-relay" tabindex="-1" role="group" aria-label="游玩模式通信星阵，点击选项多选" :data-reveal="reveal.toFixed(4)">
  <div class="mode-options mode-left" aria-label="游玩模式">
   <button v-for="mode in left" :key="mode.id" type="button" class="mode-option" :data-mode="mode.id" :aria-pressed="selected.includes(mode.id)" :aria-label="mode.label" :title="mode.name||mode.label" :disabled="blocked" @click="choose(mode)"><canvas :ref="el=>el?marks.set(mode.id,el):marks.delete(mode.id)" aria-hidden="true"></canvas><span>{{mode.label}}</span></button>
  </div>
  <div class="mode-stage"><canvas ref="canvas" class="mode-array" role="img" :aria-label="`共同核心通信阵列，${selected.length?'已选择 '+selected.length+' 种模式':'全部模式'}`"></canvas><canvas ref="scanCanvas" class="mode-scan" aria-hidden="true"></canvas><span class="mode-center" aria-hidden="true"></span></div>
  <div class="mode-options mode-right" aria-label="更多游玩模式">
   <button v-for="mode in right" :key="mode.id" type="button" class="mode-option" :data-mode="mode.id" :aria-pressed="selected.includes(mode.id)" :aria-label="mode.label" :title="mode.name||mode.label" :disabled="blocked" @click="choose(mode)"><canvas :ref="el=>el?marks.set(mode.id,el):marks.delete(mode.id)" aria-hidden="true"></canvas><span>{{mode.label}}</span></button>
  </div>
  <p v-if="!modes.length" class="mode-empty" role="status">暂无游玩模式标签</p>
  <p v-if="unavailable" class="mode-empty" role="status">星阵暂时无法显示，仍可选择模式。</p>
  <button type="button" class="mode-motion-toggle" :disabled="blocked||reduced" :aria-pressed="paused" @click="paused=!paused">{{paused?'恢复动态':'暂停动态'}}</button>
 </div>
</template>
<style scoped>
.mode-relay{position:relative;display:grid;grid-template-columns:140px minmax(0,1fr) 140px;gap:12px;flex:1;min-width:0;min-height:0;padding-bottom:44px;user-select:none}
.mode-options{display:flex;flex-direction:column;justify-content:space-evenly;gap:8px;min-height:0;overflow:auto;overscroll-behavior:contain;scrollbar-width:thin}
.mode-option{position:relative;display:flex;flex-direction:column;align-items:center;flex:none;width:100%;min-width:0;min-height:104px;padding:6px 0 14px;background:transparent!important;border:0;border-radius:10px;color:#9db1cc}
.mode-option canvas{display:block;width:124px;max-width:100%;height:72px;pointer-events:none}.mode-option span{max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:15px;line-height:24px;letter-spacing:.1em}
.mode-option:hover:not(:disabled),.mode-option[aria-pressed=true]{color:#d3e8ff}.mode-option[aria-pressed=true] span{text-shadow:0 0 12px #7fbaff42}.mode-option[aria-pressed=true]::after{content:'';position:absolute;left:calc(50% - 10px);bottom:5px;width:20px;height:1px;background:#a8d3ff99;box-shadow:0 0 8px #75afff65}
.mode-stage{position:relative;min-width:0;min-height:0}.mode-array{display:block;width:100%;height:100%}.mode-center{position:absolute;left:50%;top:50%;width:10px;height:10px;transform:translate(-50%,-50%);border-radius:50%;background:#d4e7ff;box-shadow:0 0 8px #abd3ffbb,0 0 28px #75a8e955;pointer-events:none}
.mode-scan{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.mode-motion-toggle{position:absolute;right:0;bottom:0;min-height:40px;padding:6px 12px;background:transparent;border-color:transparent;color:#8fa7c4;font-size:13px}.mode-empty{position:absolute;left:50%;top:65%;transform:translateX(-50%);text-align:center;color:#9db1cc;font-size:14px;pointer-events:none}
@media(max-width:700px){.mode-relay{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:minmax(110px,1fr) auto;gap:4px 12px}.mode-stage{grid-column:1/-1;grid-row:1}.mode-options{grid-row:2;max-height:190px;gap:0}.mode-option{flex-direction:row;justify-content:center;gap:8px;min-height:60px;padding:4px 2px 8px}.mode-option canvas{width:68px;min-width:0;height:48px}.mode-option span{font-size:14px;letter-spacing:0}.mode-option[aria-pressed=true]::after{bottom:2px}.mode-empty{top:35%}}
@media(forced-colors:active){.mode-option[aria-pressed=true] span{color:Highlight;text-decoration:underline double;text-underline-offset:4px}}
</style>
