// Original 120 × 94 base SVG coordinates; the socket is (60,39).
export const BASE_OUTLINE_PATH='m60 12 48 26v17L60 82 12 55V38z';
export const BASE_APERTURE_PATH='M0 -9 17 0 0 9 -17 0Z';
const outline=[[60,12],[108,38],[108,55],[60,82],[12,55],[12,38]];
const clamp=x=>Math.max(0,Math.min(1,x));
const disk=Array.from({length:256},(_,i)=>{const r=Math.sqrt((i+.5)/256),a=i*Math.PI*(3-Math.sqrt(5));return {x:Math.cos(a)*r,y:Math.sin(a)*r};});
function inPolygon(x,y,points){let inside=false;for(let i=0,j=points.length-1;i<points.length;j=i++){
 const a=points[i],b=points[j];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])inside=!inside;
 }return inside;
}
export function baseBlocksPoint(point,base,scale,aperture){
 if(scale<=0)return false;const x=(point.x-base.x)/scale,y=(point.y-base.y)/scale;
 const hole=aperture>0&&Math.abs(x)/(17*aperture)+Math.abs(y)/(9*aperture)<1;
 return inPolygon(x+60,y+39,outline)&&!hole;
}
function inRect(p,r){return p.x>=r.x&&p.x<=r.x+r.width&&p.y>=r.y&&p.y<=r.y+r.height;}
export function tagBlocksPoint(point,tag,clip){
 if(clip&&!inRect(point,clip))return false;if(!inRect(point,tag))return false;
 const r=Math.min(tag.radius||0,tag.width/2,tag.height/2),cx=Math.max(tag.x+r,Math.min(tag.x+tag.width-r,point.x)),cy=Math.max(tag.y+r,Math.min(tag.y+tag.height-r,point.y));
 return (point.x-cx)**2+(point.y-cy)**2<=r*r+1e-9;
}
export function coreVisibleFraction(core,base,scale,aperture,groups=[],radius=5){
 let count=0;
 for(const p of disk){const q={x:core.x+p.x*radius,y:core.y+p.y*radius};
  if(baseBlocksPoint(q,base,scale,aperture)||groups.some(g=>g.tags.some(t=>tagBlocksPoint(q,t,g.clip))))continue;count++;
 }
 return count/disk.length;
}
export function platformCoreOcclusion(progress,frame,platform,scale,groups=[]){
 const active=progress>1&&progress<2&&frame.fall>0&&frame.fall<1&&frame.platformOpacity>0;
 if(!active)return {active:false,visible:1,groups:[],base:{x:platform.x,y:platform.y},scale,aperture:0,phase:'clear'};
 const shift=frame.platformY,base={x:platform.x,y:platform.y+shift};
 const shifted=groups.map(g=>({clip:g.clip?{...g.clip,y:g.clip.y+shift}:null,tags:g.tags.map(t=>({...t,y:t.y+shift}))}));
 const fraction=coreVisibleFraction(frame.core,base,scale,frame.aperture,shifted),opacity=frame.platformOpacity;
 const visible=1-(1-fraction)*opacity;
 const depth=frame.core.y-base.y;
 return {active:true,visible,opacity,groups:shifted,base,scale,aperture:frame.aperture,
  phase:visible===0?'hidden':visible===1?'clear':depth<24*scale?'entering':'emerging'};
}
export function readPlatformTagLayout(shell){
 if(!shell)return [];
 const transform=getComputedStyle(shell).transform,matrix=transform==='none'?null:new DOMMatrixReadOnly(transform),shiftX=matrix?.m41||0,shiftY=matrix?.m42||0;
 const rect=node=>{const r=node.getBoundingClientRect();return {x:r.x-shiftX,y:r.y-shiftY,width:r.width,height:r.height};};
 return [['.tree-viewport','.tree-hub,.tree-leaf,.tree-subgroup,.other-detail-header'],['.tree-palette','.brand-module']].flatMap(([clipSelector,tagSelector])=>{
  const container=shell.querySelector(clipSelector);if(!container)return [];const clip=rect(container);
  const tags=[...container.querySelectorAll(tagSelector)].flatMap(node=>{
   const face=node.querySelector('.leaf-face')||node,r=rect(face);if(r.width<=0||r.height<=0)return [];
   const radius=parseFloat(getComputedStyle(face).borderTopLeftRadius)||0;
   return [{...r,radius:radius*(face.offsetWidth?r.width/face.offsetWidth:1)}];
  });return [{clip,tags}];
 });
}
export function wireApertureMaskBounds(bounds){return {x:bounds.left-40,y:bounds.top-40,width:bounds.right-bounds.left+80,height:bounds.bottom-bounds.top+80};}
export const wireApertureTransform=aperture=>`translate(0 ${4/15}) scale(${29/30*clamp(aperture)})`;
