export const YEAR_LEAVES = .44;
export const PLATFORM_ENTERS = .50;
export const CORE_CONTACT = .84;
const clamp = value => Math.max(0, Math.min(1, value));
export const smooth = value => { const t=clamp(value);return t*t*(3-2*t); };

export function descentFrame(progress, height, year, platform) {
  const p=clamp(progress), travel=height+Math.max(128,height*.12);
  const rise=smooth((p-PLATFORM_ENTERS)/(CORE_CONTACT-PLATFORM_ENTERS));
  const settle=smooth((p-CORE_CONTACT)/(1-CORE_CONTACT));
  const landingHeight=Math.max(48,height*.055,year.y+36-platform.y);
  const platformY=p<PLATFORM_ENTERS ? travel : p<CORE_CONTACT
    ? travel+(landingHeight-travel)*rise : landingHeight*(1-settle);
  const core=p<PLATFORM_ENTERS ? {...year} : p<CORE_CONTACT
    ? {x:year.x+(platform.x-year.x)*rise,y:year.y+(platform.y+landingHeight-year.y)*rise}
    : {x:platform.x,y:platform.y+platformY};
  const contact=clamp((p-CORE_CONTACT)/(1-CORE_CONTACT));
  const flash=contact>0 && contact<.52 ? Math.sin(Math.PI*contact/.52)**2 : 0;
  return {yearY:p<=.32 ? 0 : -travel*smooth((p-.32)/(YEAR_LEAVES-.32)),platformY,core,contact,flash,
    ambient:smooth((p-PLATFORM_ENTERS)/(1-PLATFORM_ENTERS)),
    stage:p<YEAR_LEAVES ? 'year-leaving' : p<PLATFORM_ENTERS ? 'core-only' : p<CORE_CONTACT ? 'platform-rising' : p<1 ? 'docking' : 'platform',
  };
}

// Generate two vertical screens once. Newly exposed rows have distinct positions;
// reverse scrolling reveals the exact old rows rather than reseeding them.
export function descentStars(width,height,random=Math.random) {
  const columns=Math.max(5,Math.round(Math.sqrt(width*height/14000*width/height)));
  const rows=Math.max(5,Math.ceil(height/width*columns));
  return Array.from({length:columns*(rows*2+1)},(_,i)=>({
    left:`${(i%columns+.2+random()*.6)/columns*100}%`,
    top:`calc(${(Math.floor(i/columns)+.2+random()*.6)/rows*100}% - var(--sky-travel))`,
    '--size':`${.7+random()*1.2}px`,'--peak':.18+random()*.4,
    '--life':`${14+random()*12}s`,'--delay':`${random()*5}s`,
  }));
}

export function landingParticles(contact) {
  // The SVG base outline, in its 120 × 94 viewBox. Positions are relative to
  // its light socket (60, 39), so zooming the tree scales the entire effect.
  const rim=[[60,12],[108,38],[108,55],[60,82],[12,55],[12,38]];
  return Array.from({length:36},(_,i)=>{
    const edge=i%6, fraction=(Math.floor(i/6)+.5)/6;
    const a=rim[edge], b=rim[(edge+1)%rim.length];
    const origin={x:a[0]+(b[0]-a[0])*fraction-60,y:a[1]+(b[1]-a[1])*fraction-39};
    // Outward normal of this edge: every spark starts at the rim, never at
    // the central orb. A little tangent spread keeps the burst organic.
    const length=Math.hypot(b[0]-a[0],b[1]-a[1]);
    const nx=(b[1]-a[1])/length, ny=-(b[0]-a[0])/length;
    const delay=(i%5)*.018, t=clamp((contact-delay)/(1-delay));
    const distance=(12+(i*7)%17)*(1-(1-t)**2), drift=((i%3)-1)*3*t;
    return {x:origin.x+nx*distance-ny*drift,y:origin.y+ny*distance+nx*drift,
      opacity:contact<=0 || contact>=1 ? 0 : Math.sin(Math.PI*t)**.55*(1-t)*1.2,
      size:1.1+(i%4)*.3,
    };
  });
}
