/**
 * MBTISelector.test.tsx — the "n personalities, selected 「…」" toolbar line.
 *
 * What we cover:
 *   - an agent with no MBTI configured never renders empty quotes (#973)
 *   - a configured agent still shows code + localized name
 *   - a code the catalogue does not know falls back to the bare code
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));

vi.mock("../../../../context/AgentContext", () => ({
  useAgent: () => ({ refresh: vi.fn(), activeAgentId: "ag1" }),
}));

vi.mock("../../../../api", () => ({
  default: {
    listMBTITypes: vi.fn(),
    getCurrentMBTI: vi.fn(),
    applyMBTIType: vi.fn(),
  },
}));

vi.mock("./MBTITest", () => ({ default: () => null }));

import api from "../../../../api";
import type { MBTIType } from "../../../../api/types";
import MBTISelector from "./MBTISelector";

const INFJ: MBTIType = {
  code: "INFJ",
  name_zh: "提倡者",
  name_en: "Advocate",
  nickname_zh: "提倡者",
  summary_zh: "理想主义者",
  summary_en: "Idealist",
  descriptors_zh: "安静",
  descriptors_en: "Quiet",
  dimensions: { ei: ["I", 70], sn: ["N", 60], tf: ["F", 55], jp: ["J", 50] },
  behavior: {
    answer_style: "",
    casual_chat: "",
    conflict: "",
    creativity: "",
    emotion: "",
    planning: "",
    answer_style_zh: "",
    casual_chat_zh: "",
    conflict_zh: "",
    creativity_zh: "",
    emotion_zh: "",
    planning_zh: "",
  },
  color: "#888",
  symbol: "S",
};

const meta = (total: number) =>
  screen.findByText(new RegExp(`当前有（${total}）个人格`));

describe("<MBTISelector /> selection line", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listMBTITypes).mockResolvedValue([INFJ]);
  });

  it("says no personality was chosen instead of showing empty quotes (#973)", async () => {
    vi.mocked(api.getCurrentMBTI).mockResolvedValue({
      code: "",
      configured: false,
    });

    render(<MBTISelector agentId="ag1" />);

    expect(await meta(1)).toHaveTextContent("当前有（1）个人格，尚未选择人格");
    expect((await meta(1)).textContent).not.toContain("「」");
  });

  it("keeps showing code and name for a configured personality", async () => {
    vi.mocked(api.getCurrentMBTI).mockResolvedValue({
      code: "INFJ",
      configured: true,
    });

    render(<MBTISelector agentId="ag1" />);

    expect(await meta(1)).toHaveTextContent("已选中「INFJ 提倡者」");
  });

  it("falls back to the bare code when the catalogue lacks it", async () => {
    vi.mocked(api.listMBTITypes).mockResolvedValue([]);
    vi.mocked(api.getCurrentMBTI).mockResolvedValue({
      code: "ENTP",
      configured: true,
    });

    render(<MBTISelector agentId="ag1" showHeader={false} />);

    expect(await meta(0)).toHaveTextContent("已选中「ENTP」");
  });
});
