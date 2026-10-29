// Stable seeds keep the same dust field when a transition pauses or reverses.
const smooth = value => { const t=Math.max(0,Math.min(1,value));return t*t*(3-2*t); };
export const platformDustStrength = progress => smooth((progress-.18)/.82);
export const platformDustReveal = milliseconds => smooth(milliseconds/1800);
const seeds = Array.from({length:104},(_,i) => {
  const random = offset => {const x=Math.sin((i+1)*127.1+offset*311.7)*43758.5453;return x-Math.floor(x);};
  return { angle:random(1)*Math.PI*2, distance:Math.sqrt(random(2)), speed:.006+random(3)*.009,
    phase:random(4)*Math.PI*2, period:11+random(5)*15, size:.45+random(6)*.8, lane:i%3 };
});
export function samplePlatformDust({width,height,time=0,reduced=false}) {
  const radius=Math.min(360,width*.34,height*.4), elapsed=reduced ? 0 : time/1000;
  return seeds.slice(0,width<600 ? 64 : 104).map(seed => {
    const a=seed.angle+elapsed*seed.speed, r=24+seed.distance*radius;
    const x=Math.cos(a)*r, y=Math.sin(a)*r*(.27+seed.lane*.07)+(seed.lane-1)*13;
    const depth=(Math.sin(a)+1)/2, pulse=reduced ? .65 : .46+.54*(.5+.5*Math.sin(elapsed*Math.PI*2/seed.period+seed.phase));
    return { x:x*.974+y*.225, y:-x*.225+y*.974,
      alpha:(.13+.19*depth)*pulse, size:seed.size*(.7+depth*.4) };
  });
}
export function drawPlatformStardust(canvas,{width,height,x,y,progress,time,reduced=false,ratio=1}) {
  if (!canvas || width<=0 || height<=0) return;
  const ctx=canvas.getContext('2d');if(!ctx)return;
  const dpr=Math.max(1,Math.min(2,ratio));
  const w=Math.round(width*dpr),h=Math.round(height*dpr);
  if(canvas.width!==w || canvas.height!==h) {canvas.width=w;canvas.height=h;}
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
  const amount=platformDustStrength(progress)*(reduced ? 1 : platformDustReveal(time));
  if(amount===0)return;
  const radius=Math.min(390,width*.38,height*.44);
  ctx.save();ctx.translate(x,y);ctx.globalAlpha=amount;
  const halo=ctx.createRadialGradient(0,0,12,0,0,radius);
  halo.addColorStop(0,'rgba(31,74,125,.035)');halo.addColorStop(.45,'rgba(22,57,102,.10)');halo.addColorStop(1,'rgba(8,23,47,0)');
  ctx.fillStyle=halo;ctx.fillRect(-radius,-radius,radius*2,radius*2);
  // Broad, faint curved strands echo the tree wiring without drawing hard rings.
  ctx.rotate(-.22);
  for(let lane=0;lane<3;lane++) {
    const r=radius*(.56+lane*.16), cy=(lane-1)*15;
    ctx.beginPath();ctx.moveTo(-r,cy+25);
    ctx.bezierCurveTo(-r*.5,cy-r*.25,r*.48,cy-r*.25,r,cy-22);
    ctx.strokeStyle='rgba(68,114,173,.025)';ctx.lineWidth=12-lane*2;ctx.stroke();
    ctx.strokeStyle='rgba(92,147,207,.055)';ctx.lineWidth=.6;ctx.stroke();
  }
  ctx.rotate(.22);
  for(const particle of samplePlatformDust({width,height,time,reduced})) {
    ctx.globalAlpha=amount*particle.alpha;
    ctx.fillStyle='#76a9dd';ctx.beginPath();ctx.arc(particle.x,particle.y,particle.size,0,Math.PI*2);ctx.fill();
    if(particle.size>.9) {
      ctx.globalAlpha=amount*particle.alpha*.1;ctx.beginPath();ctx.arc(particle.x,particle.y,particle.size*3.3,0,Math.PI*2);ctx.fill();
    }
  }
  ctx.restore();
}
