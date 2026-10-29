const clamp = value => Math.max(0,Math.min(1,value));
const parsed = new WeakMap(), compiled = new WeakMap(), frames = new WeakMap();
const hash = n => { const x=Math.sin(n*127.1+311.7)*43758.5453;return x-Math.floor(x); };
export const powderCut = amount => 1.3*clamp(amount)-.15;
const ripple = x => Math.sin(x*.047)*.007+Math.sin(x*.11+1.1)*.003;

export function sampleWireMesh(paths) {
  if (parsed.has(paths)) return parsed.get(paths);
  const points=[];
  for (let j=0;j<paths.length;j++) {
    const values=paths[j].d.match(/-?\d+(?:\.\d+)?/g)?.map(Number) ?? [];
    for(let i=0;i+1<values.length;i+=4) {
      const index=points.length, random=hash(index+13*j);
      points.push({x:values[i],y:values[i+1],
        dx:(values[i]-200)/184*7+(random-.5)*22,
        dy:8+hash(index+19)*22,size:.4+hash(index+29)*.5,
        alpha:(paths[j].back ? .48 : .85)*(.55+random*.35)});
    }
  }
  parsed.set(paths,points);return points;
}

export function powderParticles(points,amount,returning=false) {
  const cut=powderCut(amount);
  return points.map(point => {
    const height=point.y/400-ripple(point.x);
    const t=returning ? (height+.18-cut)/.18 : (cut-height)/.18;
    const life=clamp(t), drift=returning ? 1-life : life;
    return {x:point.x+point.dx*drift,y:point.y+point.dy*drift,size:point.size,
      opacity:t<=0 || t>=1 ? 0 : Math.sin(Math.PI*life)**.7*point.alpha};
  });
}

function boundary(context,cut) {
  context.beginPath();context.moveTo(0,440);context.lineTo(400,440);
  for(let x=400;x>=0;x-=8)context.lineTo(x,(cut+ripple(x))*400);
  context.closePath();
}

// No clock or random reseeding: every particle and the material boundary are
// functions of the shared scroll progress, including paused/rewound frames.
export function drawSpherePowder(canvas,{paths,amount,returning,size,ratio=1,reduced=false}) {
  if (!canvas) return false;
  const context=canvas.getContext('2d');if(!context)return false;
  const active=!reduced && amount>0 && amount<1;
  const previous=frames.get(canvas);
  if (!active) {
    if(previous?.active)context.clearRect(0,0,canvas.width,canvas.height);
    frames.set(canvas,{active:false});return false;
  }
  const pixels=Math.max(1,Math.round(size*Math.min(2,Math.max(1,ratio))));
  if (previous?.active && previous.paths===paths && previous.amount===amount &&
      previous.returning===returning && canvas.width===pixels) return true;
  if(canvas.width!==pixels || canvas.height!==pixels){canvas.width=pixels;canvas.height=pixels;}
  context.setTransform(pixels/400,0,0,pixels/400,0,0);context.clearRect(0,0,400,400);
  const cut=powderCut(amount);
  context.save();boundary(context,cut);context.clip();context.lineWidth=.65;
  if(!compiled.has(paths))compiled.set(paths,paths.map(path=>new Path2D(path.d)));
  for(const [index,path] of paths.entries()){
    context.globalAlpha=path.axis ? (path.back ? .1 : .36) : (path.back ? .055 : .2);
    context.strokeStyle=path.axis?'#aecdf4':'#99bae3';context.stroke(compiled.get(paths)[index]);
  }
  context.restore();context.globalAlpha=1;
  // A thin, low-opacity haze gives the moving boundary a little volume.
  context.save();context.beginPath();context.arc(200,200,184,0,Math.PI*2);context.clip();
  const y=cut*400, fog=context.createLinearGradient(0,y-15,0,y+25);
  fog.addColorStop(0,'#91beff00');fog.addColorStop(.4,'#91beff0c');fog.addColorStop(1,'#91beff00');
  context.fillStyle=fog;context.fillRect(0,y-15,400,40);context.restore();
  const particles=powderParticles(sampleWireMesh(paths),amount,returning);
  for (const particle of particles) {
    if(particle.opacity<=0)continue;
    context.globalAlpha=particle.opacity*.12;context.fillStyle='#8dbbff';
    context.beginPath();context.arc(particle.x,particle.y,particle.size*2.8,0,Math.PI*2);context.fill();
    context.globalAlpha=particle.opacity;context.fillStyle='#c1dbff';
    context.beginPath();context.arc(particle.x,particle.y,particle.size,0,Math.PI*2);context.fill();
  }
  context.globalAlpha=1;frames.set(canvas,{active:true,paths,amount,returning});return true;
}
