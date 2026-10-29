const clamp=x=>Math.max(0,Math.min(1,x));
const smooth=x=>{const t=clamp(x);return t*t*(3-2*t);};
export function platformExitPhases(progress,mounted=true){
 const t=clamp(progress-1),openStart=mounted?.30:.04,openEnd=mounted?.44:.22,fallStart=openEnd;
 const fall=smooth((t-fallStart)/(.78-fallStart));
 return {flow:mounted?smooth((t-.02)/.26):0,aperture:smooth((t-openStart)/(openEnd-openStart)),
  lift:0,fall,depart:smooth(fall),
  reveal:smooth((t-.8)/.2),entry:smooth((t-.60)/.18),fallStart,
  stage:t===0?'platform':t<openStart&&mounted?'energy-return':t<fallStart?'aperture-opening':t<.78?'core-falling':t<.8?'core-landed':t<1?'constellations-revealing':'genre'};
}
export function platformGenreFrame(progress,height,platform,genre,{mounted=true,baseScale=1}={}){
 const phases=platformExitPhases(progress,mounted);
 // Opening is stationary. Once release begins, the camera follows the orb's
 // world-space fall; its delayed smooth follow gives one continuous descent.
 const distance=Math.max(96,height*.32,genre.y-platform.y+height*.18,baseScale*60+32);
 const cameraDistance=platform.y+distance-genre.y,cameraY=cameraDistance*phases.depart;
 const clearFraction=Math.min(.7,(baseScale*46+12)/distance);
 const horizontal=smooth((phases.fall-clearFraction)/(1-clearFraction));
 const core={x:platform.x+(genre.x-platform.x)*horizontal,y:platform.y+distance*phases.fall-cameraY};
 return {...phases,worldFallY:distance*phases.fall,cameraY,gather:1,base:1,platformY:-cameraY,
  platformOpacity:1-smooth((phases.depart-.72)/.28),genreY:(height+128)*(1-phases.entry),genreOpacity:phases.entry,
  sky:height*.75*phases.depart,nebula:smooth((progress-1-.5)/.5),dust:1-smooth((progress-1-.28)/.5),core};
}
export function platformGenreTail(progress,direction,strength,height,platform,genre,options){
 const frame=platformGenreFrame(progress,height,platform,genre,options);
 if(frame.fall<=0||frame.fall>=1)return {opacity:0,angle:0};
 const before=platformGenreFrame(progress-.0001,height,platform,genre,options).core;
 const after=platformGenreFrame(progress+.0001,height,platform,genre,options).core;
 const dx=(after.x-before.x)*direction,dy=(after.y-before.y)*direction;
 // The existing CSS trail points up at zero degrees.
 return {angle:Math.atan2(-dx,dy)*180/Math.PI,
  opacity:clamp(strength)*.65*smooth(frame.fall/.07)*smooth((1-frame.fall)/.07)};
}
