import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UsageStats, visibleStatCount, type UsageStatItem } from "./UsageStats";

const getComputedStyle = window.getComputedStyle;

beforeAll(() => {
  vi.spyOn(window, "getComputedStyle").mockImplementation((element) =>
    getComputedStyle(element),
  );
});

afterAll(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const ITEMS: UsageStatItem[] = [
  { key: "total", label: "总 tokens", value: "2,788,473" },
  { key: "input", label: "输入", value: "2,764,158" },
  { key: "output", label: "输出", value: "24,315" },
  { key: "cacheRead", label: "缓存输入", value: "2,097,826" },
  { key: "cacheHit", label: "缓存命中率", value: "76.0%" },
  { key: "turns", label: "对话轮数", value: 15 },
  { key: "avg", label: "均值/轮", value: "185,898" },
];

describe("visibleStatCount", () => {
  it("fits all seven cards on a wide row", () => {
    expect(visibleStatCount(1400, 7)).toBe(7);
  });

  it("keeps a single row and reserves the overflow control on a slightly narrow display", () => {
    const visible = visibleStatCount(900, 7);
    expect(visible).toBeGreaterThanOrEqual(1);
    expect(visible).toBeLessThan(7);
  });
});

describe("UsageStats", () => {
  it("shows every metric in one row on a wide display", () => {
    render(<UsageStats items={ITEMS} width={1400} />);

    expect(screen.getByText("总 tokens")).toBeInTheDocument();
    expect(screen.getByText("均值/轮")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "common.viewMore" }),
    ).not.toBeInTheDocument();
  });

  it("stays on one row and opens leftover metrics from the overflow icon", async () => {
    const user = userEvent.setup();
    render(<UsageStats items={ITEMS} width={900} />);

    expect(screen.getByText("总 tokens")).toBeInTheDocument();
    expect(screen.queryByText("均值/轮")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "common.viewMore" }));

    expect(await screen.findByText("均值/轮")).toBeInTheDocument();
    expect(screen.getByText("185,898")).toBeInTheDocument();
  });

  it("does not hide metrics behind overflow on mobile", () => {
    render(<UsageStats items={ITEMS} width={900} overflowEnabled={false} />);

    expect(screen.getByText("总 tokens")).toBeInTheDocument();
    expect(screen.getByText("均值/轮")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "common.viewMore" }),
    ).not.toBeInTheDocument();
  });
});
