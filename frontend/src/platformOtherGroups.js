import { overlaps, LEAF } from './platformTreeLayout.js';

export const OTHER_PAGE_SIZE = 6;
const categories = [
  { key: 'classic', name: '经典平台', pattern: /sega|dreamcast|saturn|mega drive|genesis|atari|amiga|commodore|\bc64\b|\bmsx\b|zx spectrum|amstrad|\bdos\b|pc-98|pc-88|3do|neo geo|intellivision|coleco|vectrex|turbografx|pc engine|wonderswan|jaguar|lynx|odyssey|fairchild|apple ii|bbc micro|acorn|archimedes|sharp x|fm towns|trs-80|ti-99|virtual boy|game gear/i },
  { key: 'vr', name: 'VR 设备', pattern: /quest|oculus|vive|steamvr|mixed reality|\bvr\b|virtual reality|daydream|pico/i },
  { key: 'browser', name: '浏览器', pattern: /browser|webgl|html5|web browser/i },
  { key: 'devices', name: '其他设备', pattern: null },
];
export function otherCategories(platforms) {
  const groups = categories.map(category => ({ key: category.key, name: category.name, id: `other:${category.key}`, platforms: [] }));
  for (const platform of platforms) {
    const index = categories.findIndex(category => !category.pattern || category.pattern.test(platform.name || ''));
    groups[index].platforms.push(platform);
  }
  return groups.filter(group => group.platforms.length);
}
export function createOtherCluster(anchor, platforms, preferred, occupied) {
  const width = 330, rows = Math.ceil(platforms.length / 2), height = 62 + rows * 56 + Math.max(0, rows - 1) * 18;
  const candidates = [];
  for (const distance of [260, 340, 420, 500]) for (let offset = 0; offset <= 180; offset += 20) {
    for (const sign of offset ? [1, -1] : [1]) {
      const theta = (preferred + offset * sign) * Math.PI / 180;
      candidates.push({ x: anchor.x + Math.cos(theta) * distance, y: anchor.y + Math.sin(theta) * distance, width, height, score: distance + offset * 1.3 });
    }
  }
  candidates.sort((a,b) => a.score - b.score);
  let box = candidates.find(candidate => occupied.every(rect => !overlaps(candidate, rect)));
  if (!box) {
    // Finite fallback for a crowded canvas: reserve one compact panel outside existing bounds.
    box = { x: Math.max(0, ...occupied.map(rect => rect.x + rect.width / 2)) + width / 2 + 24, y: anchor.y, width, height };
  }
  const header = { x: box.x, y: box.y - height / 2 + 22, width, height: 44 };
  const leaves = platforms.map((platform,i) => ({ id: platform.id, x: box.x-width/2+LEAF.width/2+(i%2)*174, y: box.y-height/2+62+LEAF.height/2+Math.floor(i/2)*74 }));
  return { box, header, leaves, rects: [box] };
}
export function clusterPath(from, to) {
  return `M ${from.x} ${from.y} C ${from.x} ${(from.y+to.y)/2} ${to.x} ${(from.y+to.y)/2} ${to.x} ${to.y}`;
}
