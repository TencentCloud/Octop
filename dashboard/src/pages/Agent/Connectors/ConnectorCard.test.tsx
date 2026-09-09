/**
 * ConnectorCard.test.tsx — catalog card title ellipsis (issue #626 follow-up).
 *
 * What we cover:
 *   - catalog titles render via Typography ellipsis so a truncated name
 *     shows the full text on hover (same hook-class approach as
 *     ConnectorInstanceCard.test.tsx; jsdom cannot measure truncation)
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import type { ConnectorCatalogEntry } from "../../../api/modules/connectors";
import { ConnectorCard } from "./ConnectorCard";

const LONG_NAME =
  "一个名称特别长的内置连接器用于验证目录卡片标题截断与悬停提示";

function makeEntry(
  overrides: Partial<ConnectorCatalogEntry> = {},
): ConnectorCatalogEntry {
  return {
    kind: "notion",
    name: LONG_NAME,
    description: "desc",
    auth_kind: "oauth",
    doc_url: "",
    icon: "",
    color: "#8c8c8c",
    phase: "available",
    mcp_mode: "gateway",
    category: "knowledge",
    ...overrides,
  };
}

describe("<ConnectorCard />", () => {
  it("keeps long catalog names ellipsis-enabled so hover shows the full name", () => {
    render(<ConnectorCard entry={makeEntry()} onConfigure={() => undefined} />);

    const title = screen.getByText(LONG_NAME);
    expect(title.className).toContain("typography-ellipsis");
  });
});
