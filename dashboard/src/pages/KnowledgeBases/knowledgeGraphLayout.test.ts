import { describe, expect, it } from "vitest";

import { layoutGraph, neighborIds } from "./knowledgeGraphLayout";

const box = { width: 800, height: 600, margin: 40 };

describe("layoutGraph", () => {
  it("returns no positions for an empty graph", () => {
    expect(layoutGraph([], [], box).size).toBe(0);
  });

  it("centers a single node", () => {
    expect(layoutGraph([{ id: "a" }], [], box).get("a")).toEqual({
      x: 400,
      y: 300,
    });
  });

  it("keeps every node inside the margins and apart from the others", () => {
    const nodes = Array.from({ length: 40 }, (_, index) => ({
      id: `n${index}`,
    }));
    const edges = nodes
      .slice(1)
      .map((node, index) => ({ source: nodes[index % 5].id, target: node.id }));

    const points = [...layoutGraph(nodes, edges, box).values()];

    expect(points).toHaveLength(40);
    for (const point of points) {
      expect(point.x).toBeGreaterThanOrEqual(40);
      expect(point.x).toBeLessThanOrEqual(760);
      expect(point.y).toBeGreaterThanOrEqual(40);
      expect(point.y).toBeLessThanOrEqual(560);
    }
    for (let a = 0; a < points.length; a += 1) {
      for (let b = a + 1; b < points.length; b += 1) {
        const gap = Math.hypot(
          points[a].x - points[b].x,
          points[a].y - points[b].y,
        );
        expect(gap).toBeGreaterThan(8);
      }
    }
  });

  it("draws connected nodes closer together than unconnected ones", () => {
    const nodes = ["a", "b", "c", "d"].map((id) => ({ id }));
    const points = layoutGraph(nodes, [{ source: "a", target: "b" }], box);
    const distance = (first: string, second: string) =>
      Math.hypot(
        points.get(first)!.x - points.get(second)!.x,
        points.get(first)!.y - points.get(second)!.y,
      );

    expect(distance("a", "b")).toBeLessThan(distance("c", "d"));
  });

  it("keeps unconnected nodes near the middle instead of the corners", () => {
    const points = [
      ...layoutGraph([{ id: "a" }, { id: "b" }], [], box).values(),
    ];

    for (const point of points) {
      expect(Math.abs(point.x - 400)).toBeLessThan(200);
      expect(Math.abs(point.y - 300)).toBeLessThan(200);
    }
    expect(
      Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y),
    ).toBeGreaterThan(60);
  });

  it("gives the same layout every time", () => {
    const nodes = ["a", "b", "c"].map((id) => ({ id }));
    const edges = [{ source: "a", target: "b" }];

    expect([...layoutGraph(nodes, edges, box)]).toEqual([
      ...layoutGraph(nodes, edges, box),
    ]);
  });

  it("ignores edges to nodes that are not drawn", () => {
    const points = layoutGraph(
      [{ id: "a" }, { id: "b" }],
      [{ source: "a", target: "missing" }],
      box,
    );

    expect(points.size).toBe(2);
    expect(Number.isFinite(points.get("a")!.x)).toBe(true);
  });
});

describe("neighborIds", () => {
  it("returns the other end of each edge touching the node", () => {
    const edges = [
      { source: "a", target: "b" },
      { source: "c", target: "a" },
      { source: "b", target: "c" },
    ];

    expect([...neighborIds("a", edges)].sort()).toEqual(["b", "c"]);
    expect(neighborIds("z", edges).size).toBe(0);
  });
});
