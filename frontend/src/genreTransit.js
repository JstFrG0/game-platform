const clamp=x=>Math.max(0,Math.min(1,x));
const smooth=x=>{const t=clamp(x);return t*t*(3-2*t);};
export {platformGenreFrame as genreTransitFrame} from './platformGenreTransit.js';

// Follow perceived screen movement, not the line between the orb's anchors.
// Downward navigation: year -> platform trails upper-left; platform -> genre
// trails upper-right. Reversing adds half a turn. The upward-pointing CSS
// gradient rotates around the orb, so negative angles point left.
export function filterCoreTrail(progress,direction,strength){
 const leg=progress<=1 ? {start:.32,end:.84,angle:-20} : progress<=2 ? {start:1.4,end:1.72,angle:20} : {start:2.32,end:2.76,angle:20};
 const angle=leg.angle+(direction<0 ? 180 : 0);
 if(progress<=leg.start || progress>=leg.end)return {opacity:0,angle};
 return {opacity:clamp(strength)*.65*smooth((progress-leg.start)/.032)*smooth((leg.end-progress)/.032),angle};
}
