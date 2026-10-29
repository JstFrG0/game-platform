// Screen-facing rectangles in independent radial sectors. Existing branches are immutable.
export const HUB = { width: 182, height: 56 };
export const LEAF = { width: 156, height: 56 };
export const ROOT = { x: 0, y: 0, width: 116, height: 108 };
export const radians = degrees => degrees * Math.PI / 180;
export const angleDistance = (a, b) => Math.abs(((a - b + 540) % 360) - 180);
const normalize = angle => ((angle + 180) % 360 + 360) % 360 - 180;
export function overlaps(a, b, gap = 18) {
  return Math.abs(a.x - b.x) < (a.width + b.width) / 2 + gap &&
    Math.abs(a.y - b.y) < (a.height + b.height) / 2 + gap;
}
export function branchRects(branch) {
  return [{ ...branch.hub, ...HUB }, ...branch.leaves.map(leaf => ({ ...leaf, ...LEAF }))];
}
export function treeBounds(branches, extra = []) {
  const rects = [ROOT, ...branches.flatMap(branchRects), ...extra];
  return {
    left: Math.min(...rects.map(r => r.x - r.width / 2)), right: Math.max(...rects.map(r => r.x + r.width / 2)),
    top: Math.min(...rects.map(r => r.y - r.height / 2)), bottom: Math.max(...rects.map(r => r.y + r.height / 2)),
  };
}
export function createBranch(family, platforms, preferred, existing = []) {
  let angle = normalize(preferred), best = -Infinity;
  // Pick the nearest available direction; never rotate other branches to make space.
  const candidates = [angle];
  for (let distance = 1; distance <= 180; distance++) candidates.push(normalize(angle + distance), normalize(angle - distance));
  for (const candidate of candidates) {
    const separation = Math.min(180, ...existing.map(branch => angleDistance(branch.angle, candidate)));
    if (separation >= 36) { angle = candidate; break; }
    if (separation > best) { best = separation; angle = candidate; }
  }
  const theta = radians(angle), axis = { x: Math.cos(theta), y: Math.sin(theta) }, across = { x: -axis.y, y: axis.x };
  const occupied = [ROOT, ...existing.flatMap(branchRects)];
  const point = (distance, offset = 0) => ({ x: axis.x * distance + across.x * offset, y: axis.y * distance + across.y * offset });
  function place(distance, offset, size) {
    let location = point(distance, offset);
    while (occupied.some(rect => overlaps({ ...location, ...size }, rect))) {
      distance += 24; location = point(distance, offset);
    }
    occupied.push({ ...location, ...size });
    return { ...location, distance };
  }
  const hub = place(214, 0, HUB);
  const perpendicularStep = (LEAF.width + 24) * Math.abs(axis.y) + (LEAF.height + 24) * Math.abs(axis.x);
  const forwardStep = (LEAF.width + 28) * Math.abs(axis.x) + (LEAF.height + 28) * Math.abs(axis.y);
  const leaves = platforms.map((platform, i) => {
    const layer = Math.floor(i / 3), count = Math.min(3, platforms.length - layer * 3);
    const offset = (i % 3 - (count - 1) / 2) * perpendicularStep;
    // Constrain every twig to its own cone; neighbouring brands stay distinct.
    const radius = Math.max(hub.distance + 124 + layer * forwardStep, Math.abs(offset) / Math.tan(radians(18)));
    return { id: platform.id, ...place(radius, offset, LEAF) };
  });
  return { family, angle, hub, leaves };
}
export function trunkPath(branch) {
  const { x, y } = branch.hub;
  return `M 0 0 C ${x * .28 - y * .015} ${y * .28 + x * .015} ${x * .7 + y * .015} ${y * .7 - x * .015} ${x} ${y}`;
}
export function twigPath(branch, leaf) {
  const { x, y } = branch.hub, theta = radians(branch.angle);
  const reach = Math.hypot(leaf.x - x, leaf.y - y) * .44;
  return `M ${x} ${y} C ${x + Math.cos(theta) * reach} ${y + Math.sin(theta) * reach} ${leaf.x * .85 + x * .15} ${leaf.y * .85 + y * .15} ${leaf.x} ${leaf.y}`;
}
