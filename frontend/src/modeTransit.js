import {smooth} from './modeRelay.js';
export function modeTransitFrame(progress,height,genre,mode){
  const t=Math.max(0,Math.min(1,progress-2)),travel=smooth((t-.32)/.44);
  return {gather:1-smooth(t/.3),genreY:-(height+128)*smooth((t-.28)/.3),genreOpacity:1-smooth((t-.28)/.3),
    modeY:(height+128)*(1-smooth((t-.58)/.18)),modeOpacity:smooth((t-.58)/.18),reveal:smooth((t-.84)/.16),scan:t>.76&&t<.90?(t-.76)/.14:0,
    sky:height*.75*smooth((t-.28)/.72),nebula:smooth((t-.58)/.42),
    core:{x:genre.x+(mode.x-genre.x)*travel,y:genre.y+(mode.y-genre.y)*travel}};
}
