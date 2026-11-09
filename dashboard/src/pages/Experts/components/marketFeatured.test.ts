import { describe, expect, it } from "vitest";
import { MARKET_SCENE_FEATURED, visibleMarketExperts } from "./marketFeatured";

const items = [
  { id: "ops", scene: "tech", featured: true },
  { id: "shop", scene: "ecommerce", featured: false },
  { id: "writer", scene: "content-creation" },
];

describe("visibleMarketExperts", () => {
  it("defaults the featured pill to shipped templates", () => {
    expect(
      visibleMarketExperts(items, MARKET_SCENE_FEATURED, false).map(
        (item) => item.id,
      ),
    ).toEqual(["ops"]);
  });

  it("keeps every card on All and while searching", () => {
    expect(visibleMarketExperts(items, "", false)).toHaveLength(3);
    expect(
      visibleMarketExperts(items, MARKET_SCENE_FEATURED, true),
    ).toHaveLength(3);
  });

  it("still filters a normal scene", () => {
    expect(
      visibleMarketExperts(items, "ecommerce", false).map((item) => item.id),
    ).toEqual(["shop"]);
  });
});
