import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../../../api/modules/skillPackages", () => ({
  skillPackagesApi: {
    list: vi.fn(),
    listMounted: vi.fn(),
    get: vi.fn(),
    replaceMounted: vi.fn(),
    copyToWorkspace: vi.fn(),
  },
}));

vi.mock("../../../../context/AgentContext", () => ({
  useAgent: () => ({ agents: [{ agent_id: "a1", config: {} }] }),
}));

vi.mock("../../../Experts/components/agentBackendForm", () => ({
  supportsHostSkillPackagesFromConfig: () => true,
}));

vi.mock("../../../../utils/showApiToast", () => ({ showApiError: vi.fn() }));

vi.mock("@/utils/antdMessage", () => ({
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

// The shared setup builds a fresh ``t`` on every ``useTranslation`` call, which
// re-runs this component's ``useEffect([agentId, t])`` after each render and
// leaves the tree flipping between the spinner and the catalog. Pin one stable
// ``t`` so a click lands on a node that stays mounted.
vi.mock("react-i18next", () => {
  const t = (key: string) => key;
  return {
    useTranslation: () => ({
      t,
      i18n: { language: "zh", changeLanguage: () => Promise.resolve() },
    }),
    Trans: ({ children }: { children?: unknown }) => children,
  };
});

import { skillPackagesApi } from "../../../../api/modules/skillPackages";
import type {
  SkillPackage,
  SkillPackageDetail,
} from "../../../../api/types/skillPackage";
import SkillPackagesTab from "./SkillPackagesTab";

const listMock = vi.mocked(skillPackagesApi.list);
const listMountedMock = vi.mocked(skillPackagesApi.listMounted);
const getMock = vi.mocked(skillPackagesApi.get);

const ALPHA = "pkg-alpha";
const BETA = "pkg-beta";

function makePackage(id: string, name: string): SkillPackage {
  return {
    id,
    name,
    description: `${name} description`,
    created_by: "system",
    skill_count: 1,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

function makeDetail(
  id: string,
  name: string,
  slug: string,
): SkillPackageDetail {
  return {
    ...makePackage(id, name),
    skills: [
      {
        slug,
        name: slug,
        description: `${slug} description`,
        path: slug,
        kind: "package",
        package_id: id,
      },
    ],
  };
}

function renderTab() {
  return render(
    <SkillPackagesTab
      agentId="a1"
      skills={[]}
      fetchSkills={vi.fn().mockResolvedValue(undefined)}
      toggleEnabled={vi.fn().mockResolvedValue(true)}
    />,
  );
}

function alphaDetail() {
  return makeDetail(ALPHA, "Alpha Package", "alpha-skill");
}

/**
 * Hold the alpha fetch open so it can land after the beta fetch has answered,
 * which is the out-of-order response the request gate has to drop.
 */
function holdAlpha() {
  let resolveAlpha!: (value: SkillPackageDetail) => void;
  const alpha = new Promise<SkillPackageDetail>((resolve) => {
    resolveAlpha = resolve;
  });
  getMock.mockImplementation((packageId: string) =>
    packageId === ALPHA
      ? alpha
      : Promise.resolve(makeDetail(BETA, "Beta Package", "beta-skill")),
  );
  return async () => {
    await act(async () => {
      resolveAlpha(alphaDetail());
    });
  };
}

describe("<SkillPackagesTab /> detail request gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue([
      makePackage(ALPHA, "Alpha Package"),
      makePackage(BETA, "Beta Package"),
    ]);
    listMountedMock.mockResolvedValue({ package_ids: [] });
  });

  it("keeps the newest drawer when an earlier detail request resolves later", async () => {
    const user = userEvent.setup();
    const releaseAlpha = holdAlpha();
    renderTab();
    await screen.findByText("Alpha Package");

    const detailButtons = await screen.findAllByRole("button", {
      name: "common.viewDetail",
    });
    await user.click(detailButtons[0]);
    await user.click(detailButtons[1]);
    await waitFor(() =>
      expect(
        within(screen.getByRole("dialog")).getByText("Beta Package"),
      ).toBeInTheDocument(),
    );

    await releaseAlpha();

    const drawer = screen.getByRole("dialog");
    expect(within(drawer).getByText("Beta Package")).toBeInTheDocument();
    expect(within(drawer).queryByText("Alpha Package")).not.toBeInTheDocument();
  });

  it("keeps the newest copy modal when an earlier request resolves later", async () => {
    const user = userEvent.setup();
    const releaseAlpha = holdAlpha();
    renderTab();
    await screen.findByText("Alpha Package");

    const copyButtons = await screen.findAllByRole("button", {
      name: "skills.copySkills",
    });
    await user.click(copyButtons[0]);
    await user.click(copyButtons[1]);
    await waitFor(() =>
      expect(
        within(screen.getByRole("dialog")).getAllByText("beta-skill").length,
      ).toBeGreaterThan(0),
    );

    await releaseAlpha();

    const modal = screen.getByRole("dialog");
    expect(within(modal).getAllByText("beta-skill").length).toBeGreaterThan(0);
    expect(within(modal).queryAllByText("alpha-skill")).toHaveLength(0);
  });

  it("still opens the package that was requested on its own", async () => {
    const user = userEvent.setup();
    getMock.mockResolvedValue(alphaDetail());
    renderTab();
    await screen.findByText("Alpha Package");

    const detailButtons = await screen.findAllByRole("button", {
      name: "common.viewDetail",
    });
    await user.click(detailButtons[0]);

    await waitFor(() =>
      expect(
        within(screen.getByRole("dialog")).getByText("Alpha Package"),
      ).toBeInTheDocument(),
    );
  });
});
