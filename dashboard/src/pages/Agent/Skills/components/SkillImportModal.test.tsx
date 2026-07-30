import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JSZip from "jszip";

vi.mock("./parseSkillZip", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./parseSkillZip")>();
  return {
    ...actual,
    parseSkillZip: vi.fn(actual.parseSkillZip),
  };
});

import { parseSkillZip } from "./parseSkillZip";
import { SkillImportModal } from "./SkillImportModal";

const mockedParse = vi.mocked(parseSkillZip);

async function makeZipFile(
  tree: Record<string, string>,
  filename = "skills.zip",
): Promise<File> {
  const zip = new JSZip();
  for (const [path, content] of Object.entries(tree)) {
    zip.file(path, content);
  }
  const blob = await zip.generateAsync({ type: "blob" });
  return new File([blob], filename, { type: "application/zip" });
}

function setInputFiles(input: HTMLInputElement, files: File[]) {
  Object.defineProperty(input, "files", {
    configurable: true,
    value: files,
  });
  fireEvent.change(input);
}

async function switchToZipMode(user: ReturnType<typeof userEvent.setup>) {
  // antd Segmented radios use pointer-events:none on the input; click the label text.
  await user.click(screen.getByText("skills.importFromZip"));
}

describe("<SkillImportModal /> local zip import", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedParse.mockReset();
    mockedParse.mockImplementation(async (...args) => {
      const actual = await vi.importActual<typeof import("./parseSkillZip")>(
        "./parseSkillZip",
      );
      return actual.parseSkillZip(...args);
    });
  });

  it("imports a selected zip with overwrite flag", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onImportZip = vi.fn().mockResolvedValue({
      imported: 1,
      skipped: 0,
      failed: 0,
    });
    const zipFile = await makeZipFile({
      "demo/SKILL.md": "---\nname: demo\n---\n",
    });

    render(
      <SkillImportModal
        open
        importing={false}
        onClose={onClose}
        onImportUrl={vi.fn()}
        onImportZip={onImportZip}
      />,
    );

    await switchToZipMode(user);
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    setInputFiles(fileInput, [zipFile]);

    expect(screen.getByText("skills.zip")).toBeInTheDocument();

    await user.click(screen.getByText("skills.overwriteExisting"));
    await user.click(
      screen.getByRole("button", { name: "skills.importSkills" }),
    );

    await waitFor(() => {
      expect(onImportZip).toHaveBeenCalledTimes(1);
    });
    const [skills, options] = onImportZip.mock.calls[0];
    expect(options).toEqual({ overwrite: true });
    expect(skills).toHaveLength(1);
    expect(skills[0].slug).toBe("demo");
    expect(
      skills[0].files.some((f: { path: string }) => f.path === "SKILL.md"),
    ).toBe(true);
    expect(onClose).toHaveBeenCalled();
  });

  it("rejects non-zip files before parsing", async () => {
    const user = userEvent.setup();
    const onImportZip = vi.fn();
    const txt = new File(["hello"], "notes.txt", { type: "text/plain" });

    render(
      <SkillImportModal
        open
        importing={false}
        onClose={vi.fn()}
        onImportUrl={vi.fn()}
        onImportZip={onImportZip}
      />,
    );

    await switchToZipMode(user);
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    setInputFiles(fileInput, [txt]);

    expect(screen.getByText("skills.zipOnly")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "skills.importSkills" }),
    ).toBeDisabled();
    expect(onImportZip).not.toHaveBeenCalled();
  });

  it("shows parse errors from the zip parser", async () => {
    const user = userEvent.setup();
    mockedParse.mockRejectedValueOnce(new Error("ZIP_NO_SKILLS"));
    const onImportZip = vi.fn();
    const zipFile = await makeZipFile({ "docs/readme.md": "x" });

    render(
      <SkillImportModal
        open
        importing={false}
        onClose={vi.fn()}
        onImportUrl={vi.fn()}
        onImportZip={onImportZip}
      />,
    );

    await switchToZipMode(user);
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    setInputFiles(fileInput, [zipFile]);
    await user.click(
      screen.getByRole("button", { name: "skills.importSkills" }),
    );

    await waitFor(() => {
      expect(screen.getByText("skills.zipNoSkills")).toBeInTheDocument();
    });
    expect(onImportZip).not.toHaveBeenCalled();
  });

  it("requires a zip before confirming", async () => {
    const user = userEvent.setup();
    const onImportZip = vi.fn();

    render(
      <SkillImportModal
        open
        importing={false}
        onClose={vi.fn()}
        onImportUrl={vi.fn()}
        onImportZip={onImportZip}
      />,
    );

    await switchToZipMode(user);
    expect(
      screen.getByRole("button", { name: "skills.importSkills" }),
    ).toBeDisabled();

    const zipFile = await makeZipFile({
      "demo/SKILL.md": "---\nname: demo\n---\n",
    });
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    setInputFiles(fileInput, [zipFile]);
    await user.click(screen.getByText("skills.removeZip"));
    expect(
      screen.getByRole("button", { name: "skills.importSkills" }),
    ).toBeDisabled();
    expect(onImportZip).not.toHaveBeenCalled();
  });
});
