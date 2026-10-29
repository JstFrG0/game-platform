const clamp = value => Math.max(0,Math.min(1,value));
const smooth = value => { const t=clamp(value);return t*t*(3-2*t); };

// A leg changes only after leaving a complete endpoint. Reversing halfway
// rewinds that same leg, so the distinct return ordering never jumps a frame.
export function transitLeg(current,progress,next) {
  if (progress===0 && next>0) return 'depart';
  if (progress===1 && next<1) return 'return';
  return current;
}

export function yearTransitFrame(progress,leg='depart') {
  const p=clamp(progress), returning=leg==='return';
  const radius=returning ? 1-smooth((p-.18)/.12) : 1-smooth(p/.10);
  const powder=returning ? smooth(p/.16) : smooth((p-.08)/.22);
  const shift=smooth((p-.32)/.12);
  return {radius,labelOpacity:smooth(radius/.24),powder,returning,
    powderActive:powder>0 && powder<1,
    meshVisible:1-powder,shift,sky:smooth((p-.32)/.68),
    stage:p>=.5 ? 'platform-transfer' : p>.44 ? 'core-only' : p>.32 ? 'year-travel'
      : returning ? p>.30 ? 'core-settled' : p>.18 ? 'extend-years' : p>.16 ? 'years-ready' : 'rebuild-sphere'
      : p<.08 ? 'collect-years' : p<.30 ? 'dissolve-sphere' : 'dust-cleared',
  };
}
