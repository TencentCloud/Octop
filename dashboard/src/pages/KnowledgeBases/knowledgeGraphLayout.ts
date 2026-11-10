export interface LayoutNode {
  id: string;
}

export interface LayoutEdge {
  source: string;
  target: string;
}

export interface LayoutPoint {
  x: number;
  y: number;
}

export interface LayoutOptions {
  width: number;
  height: number;
  /** Space kept clear at every side so node labels stay inside the box. */
  margin?: number;
  iterations?: number;
}

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const GRAVITY = 0.6;
const MAX_STRETCH = 1.5;

/**
 * Place graph nodes with a force-directed (Fruchterman–Reingold) pass.
 *
 * The start positions are a fixed spiral rather than random, so the same
 * graph always draws the same way and a refresh does not reshuffle it.
 */
export function layoutGraph(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  options: LayoutOptions,
): Map<string, LayoutPoint> {
  const { width, height } = options;
  const margin = options.margin ?? 40;
  const iterations = options.iterations ?? 300;
  const positions = new Map<string, LayoutPoint>();
  if (nodes.length === 0) return positions;

  const centerX = width / 2;
  const centerY = height / 2;
  if (nodes.length === 1) {
    positions.set(nodes[0].id, { x: centerX, y: centerY });
    return positions;
  }

  const innerWidth = Math.max(width - margin * 2, 1);
  const innerHeight = Math.max(height - margin * 2, 1);
  const spread = Math.min(innerWidth, innerHeight) / 2;
  const xs = new Float64Array(nodes.length);
  const ys = new Float64Array(nodes.length);
  const indexOf = new Map<string, number>();
  nodes.forEach((node, index) => {
    indexOf.set(node.id, index);
    const radius = spread * Math.sqrt((index + 0.5) / nodes.length);
    xs[index] = centerX + radius * Math.cos(index * GOLDEN_ANGLE);
    ys[index] = centerY + radius * Math.sin(index * GOLDEN_ANGLE);
  });
  const links = edges
    .map((edge) => [indexOf.get(edge.source), indexOf.get(edge.target)])
    .filter(
      (pair): pair is [number, number] =>
        pair[0] !== undefined && pair[1] !== undefined && pair[0] !== pair[1],
    );

  if (links.length === 0) {
    // Nothing pulls unconnected nodes together, so the simulation would only
    // fling them to the corners. Keep the starting spiral, drawn in closer.
    nodes.forEach((node, index) => {
      positions.set(node.id, {
        x: centerX + (xs[index] - centerX) * 0.6,
        y: centerY + (ys[index] - centerY) * 0.6,
      });
    });
    return positions;
  }

  const ideal = Math.sqrt((innerWidth * innerHeight) / nodes.length);
  const dx = new Float64Array(nodes.length);
  const dy = new Float64Array(nodes.length);
  for (let step = 0; step < iterations; step += 1) {
    dx.fill(0);
    dy.fill(0);
    for (let a = 0; a < nodes.length; a += 1) {
      for (let b = a + 1; b < nodes.length; b += 1) {
        const offsetX = xs[a] - xs[b];
        const offsetY = ys[a] - ys[b];
        const distance = Math.max(Math.hypot(offsetX, offsetY), 0.01);
        const push = (ideal * ideal) / distance;
        dx[a] += (offsetX / distance) * push;
        dy[a] += (offsetY / distance) * push;
        dx[b] -= (offsetX / distance) * push;
        dy[b] -= (offsetY / distance) * push;
      }
    }
    for (const [a, b] of links) {
      const offsetX = xs[a] - xs[b];
      const offsetY = ys[a] - ys[b];
      const distance = Math.max(Math.hypot(offsetX, offsetY), 0.01);
      const pull = (distance * distance) / ideal;
      dx[a] -= (offsetX / distance) * pull;
      dy[a] -= (offsetY / distance) * pull;
      dx[b] += (offsetX / distance) * pull;
      dy[b] += (offsetY / distance) * pull;
    }
    // Cooling: large moves first, then settle.
    const limit = (spread / 4) * (1 - step / iterations) + 0.5;
    for (let index = 0; index < nodes.length; index += 1) {
      // A pull to the middle keeps unconnected nodes from drifting away for good.
      dx[index] += (centerX - xs[index]) * GRAVITY;
      dy[index] += (centerY - ys[index]) * GRAVITY;
      const move = Math.max(Math.hypot(dx[index], dy[index]), 0.01);
      const capped = Math.min(move, limit);
      xs[index] += (dx[index] / move) * capped;
      ys[index] += (dy[index] / move) * capped;
    }
  }

  // The simulation runs unbounded; fit its bounding box onto the drawing area.
  // Clamping inside the loop instead piles nodes up along the edges. Small graphs
  // are not blown up to the corners: the stretch is capped and the result centered.
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const spanX = Math.max(Math.max(...xs) - minX, 1);
  const spanY = Math.max(Math.max(...ys) - minY, 1);
  const scaleX = Math.min(innerWidth / spanX, MAX_STRETCH);
  const scaleY = Math.min(innerHeight / spanY, MAX_STRETCH);
  nodes.forEach((node, index) => {
    positions.set(node.id, {
      x: centerX + (xs[index] - minX - spanX / 2) * scaleX,
      y: centerY + (ys[index] - minY - spanY / 2) * scaleY,
    });
  });
  return positions;
}

/** Ids of the nodes one edge away from *id* (not including it). */
export function neighborIds(id: string, edges: LayoutEdge[]): Set<string> {
  const out = new Set<string>();
  for (const edge of edges) {
    if (edge.source === id) out.add(edge.target);
    else if (edge.target === id) out.add(edge.source);
  }
  return out;
}
