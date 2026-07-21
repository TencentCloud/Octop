/**
 * CandidatesReview.test.tsx — pending Candidate inbox.
 *
 * What we cover:
 *   - mount → listCandidates without a status filter (All) by default
 *   - row renders title + verbatim_quote + subject_name
 *   - clicking the promote button opens the Popconfirm, confirming
 *     fires promoteCandidate and re-loads the list
 *   - clicking the reject button opens the Modal, submitting calls
 *     rejectCandidate with the reason and re-loads the list
 *   - empty state
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  listCandidatesResp,
  makeCandidate,
  promoteResp,
  rejectResp,
} from "../../../test/memoryFixtures";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    listCandidates: vi.fn(),
    promoteCandidate: vi.fn(),
    rejectCandidate: vi.fn(),
  },
}));

import { memoryDashboardApi } from "../../../api/modules/memoryDashboard";
import CandidatesReview from "./CandidatesReview";

const api = vi.mocked(memoryDashboardApi, true);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("<CandidatesReview />", () => {
  it("loads all candidates by default and renders title + quote", async () => {
    api.listCandidates.mockResolvedValue(
      listCandidatesResp([
        makeCandidate({
          id: "cand-1",
          title: "咖啡偏好",
          verbatim_quote: "我每天必须喝美式",
          subject_name: "用户",
        }),
      ]),
    );

    render(<CandidatesReview agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(screen.getByText("咖啡偏好")).toBeInTheDocument();
    });

    expect(api.listCandidates).toHaveBeenCalledWith("ZYWZTD", {
      offset: 0,
      limit: 20,
    });
    // verbatim quote and subject_name render in the meta line
    expect(screen.getByText(/每天必须喝美式/)).toBeInTheDocument();
  });

  it("promotes a candidate via Popconfirm and re-loads", async () => {
    api.listCandidates.mockResolvedValue(
      listCandidatesResp([makeCandidate({ id: "cand-1", title: "咖啡偏好" })]),
    );
    api.promoteCandidate.mockResolvedValue(promoteResp());

    const user = userEvent.setup();
    render(<CandidatesReview agentId="ZYWZTD" />);

    await waitFor(() =>
      expect(screen.getByText("咖啡偏好")).toBeInTheDocument(),
    );

    const promoteBtn = screen.getByRole("button", { name: /采\s*纳/ });
    await user.click(promoteBtn);

    // Popconfirm okText and inline action text are both the same label; antd may add spacing, so match loosely.
    const allRecord = await screen.findAllByRole("button", {
      name: /采\s*纳/,
    });
    const confirmBtn = allRecord[allRecord.length - 1];
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(api.promoteCandidate).toHaveBeenCalledWith("ZYWZTD", "cand-1");
    });
    // listCandidates was called twice: initial + reload after promote
    await waitFor(() => {
      expect(api.listCandidates).toHaveBeenCalledTimes(2);
    });
  });

  it("rejects a candidate with a typed reason via Modal", async () => {
    api.listCandidates.mockResolvedValue(
      listCandidatesResp([makeCandidate({ id: "cand-1", title: "可疑事实" })]),
    );
    api.rejectCandidate.mockResolvedValue(rejectResp());

    const user = userEvent.setup();
    render(<CandidatesReview agentId="ZYWZTD" />);

    await waitFor(() =>
      expect(screen.getByText("可疑事实")).toBeInTheDocument(),
    );

    const rejectBtn = screen.getByRole("button", { name: /忽\s*略/ });
    await user.click(rejectBtn);

    await waitFor(() => {
      expect(screen.getByText("忽略这条草稿")).toBeInTheDocument();
    });

    const textarea = screen.getByPlaceholderText(/原因可选/);
    await user.type(textarea, "重复信息");

    const okBtn = screen.getByRole("button", { name: /确认忽略/ });
    await user.click(okBtn);

    await waitFor(() => {
      expect(api.rejectCandidate).toHaveBeenCalledWith("ZYWZTD", "cand-1", {
        reason: "重复信息",
      });
    });
    await waitFor(() => {
      expect(api.listCandidates).toHaveBeenCalledTimes(2);
    });
  });

  it("renders the empty placeholder when no candidates match", async () => {
    api.listCandidates.mockResolvedValue(listCandidatesResp([]));
    render(<CandidatesReview agentId="ZYWZTD" />);
    await waitFor(() => expect(api.listCandidates).toHaveBeenCalled());
    expect(screen.getByText("暂无记忆内容")).toBeInTheDocument();
  });

  it("disables promote/reject buttons for already-decided candidates", async () => {
    api.listCandidates.mockResolvedValue(
      listCandidatesResp([
        makeCandidate({
          id: "cand-1",
          title: "已升级的候选",
          status: "promoted",
          decided_at: "2026-06-29T10:00:00Z",
          decided_by: "user",
        }),
      ]),
    );

    render(<CandidatesReview agentId="ZYWZTD" />);
    await waitFor(() =>
      expect(screen.getByText("已升级的候选")).toBeInTheDocument(),
    );

    const promoteBtn = screen.getByRole("button", { name: /采\s*纳/ });
    const rejectBtn = screen.getByRole("button", { name: /忽\s*略/ });
    expect(promoteBtn).toBeDisabled();
    expect(rejectBtn).toBeDisabled();
  });
});
