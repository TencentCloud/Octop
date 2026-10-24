import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../api/modules/createdSkills", () => ({
  createdSkillsApi: {
    list: vi.fn(),
    install: vi.fn(),
  },
}));

vi.mock("../../../../utils/showApiToast", () => ({ showApiError: vi.fn() }));

vi.mock("../../../../utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("react-i18next", () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});

import { createdSkillsApi } from "../../../../api/modules/createdSkills";
import CreatedSkillsTab from "./CreatedSkillsTab";

const listMock = vi.mocked(createdSkillsApi.list);
const installMock = vi.mocked(createdSkillsApi.install);

describe("<CreatedSkillsTab />", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue([
      {
        slug: "text-normalizer",
        name: "Text Normalizer",
        description: "Normalize text spacing.",
        artifact_type: "hybrid",
        revision: "a".repeat(64),
        published_at: "2026-10-16T00:00:00Z",
        installed: false,
        source: "created",
      },
    ]);
    installMock.mockResolvedValue({});
  });

  it("shows a builder-created skill and installs it", async () => {
    const user = userEvent.setup();
    render(<CreatedSkillsTab agentId="agent-1" />);

    expect(await screen.findByText("Text Normalizer")).toBeInTheDocument();
    expect(screen.getByText("skills.createdByBuilder")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /skills.install$/ }));

    await waitFor(() =>
      expect(installMock).toHaveBeenCalledWith(
        "agent-1",
        "text-normalizer",
        false,
      ),
    );
  });
});
