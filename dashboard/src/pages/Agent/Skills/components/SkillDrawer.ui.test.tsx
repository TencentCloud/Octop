import { Form } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SkillDrawer, type SkillFormValues } from "./SkillDrawer";
import type { SkillDetail } from "../useSkills";

const translation = vi.hoisted(() => ({ t: (key: string) => key }));
vi.mock("react-i18next", () => ({ useTranslation: () => translation }));
vi.mock("../../../../workbuddy/variant", () => ({ WORKBUDDY_UI: true }));
vi.mock("../../../../components/PdfDocumentPreview", () => ({
  default: () => null,
}));

const skill: SkillDetail = {
  slug: "round2-skill",
  name: "round2-skill",
  description: "Original trigger description",
  enabled: true,
  kind: "workspace",
  frontmatter: {
    name: "round2-skill",
    description: "Original trigger description",
  },
  body: "Original instructions",
  raw: "---\nname: round2-skill\ndescription: Original trigger description\n---\nOriginal instructions",
};

function SkillEditor({
  submit,
  readOnly = false,
}: {
  submit: (values: SkillFormValues) => void;
  readOnly?: boolean;
}) {
  const [form] = Form.useForm<SkillFormValues>();
  return (
    <SkillDrawer
      open
      form={form}
      editingSkill={skill}
      onClose={() => {}}
      onSubmit={submit}
      readOnly={readOnly}
    />
  );
}

describe("skill detail in the production WorkBuddy display", () => {
  it("saves the existing SKILL.md document without changing its stable name", async () => {
    const submit = vi.fn();
    render(<SkillEditor submit={submit} />);
    await userEvent.click(
      screen.getByRole("button", { name: "skills.editSkill" }),
    );
    const description = screen.getByPlaceholderText(
      "skills.descriptionPlaceholder",
    );
    await userEvent.clear(description);
    await userEvent.type(description, "Revised trigger description");
    const body = screen.getByPlaceholderText("skills.bodyPlaceholder");
    await userEvent.clear(body);
    await userEvent.type(body, "Revised instructions");
    await userEvent.click(
      screen.getByRole("button", { name: "skills.saveSkill" }),
    );
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    expect(submit.mock.calls[0][0]).toMatchObject({
      name: skill.slug,
      description: "Revised trigger description",
      body: "Revised instructions",
      content: expect.stringContaining("name: round2-skill"),
    });
  });

  it("cancels local edits and restores the stored document without saving", async () => {
    const submit = vi.fn();
    render(<SkillEditor submit={submit} />);
    await userEvent.click(
      screen.getByRole("button", { name: "skills.editSkill" }),
    );
    const description = screen.getByPlaceholderText(
      "skills.descriptionPlaceholder",
    );
    await userEvent.clear(description);
    await userEvent.type(description, "Unsaved change");
    await userEvent.click(
      screen.getByRole("button", { name: "common.cancel" }),
    );
    expect(screen.getByText(skill.description)).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Unsaved change")).toBeNull();
    expect(
      screen.getByRole("button", { name: "skills.editSkill" }),
    ).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });

  it("keeps shared/read-only skills non-editable in the new dialog", () => {
    render(<SkillEditor submit={vi.fn()} readOnly />);
    expect(
      screen.queryByRole("button", { name: "skills.editSkill" }),
    ).toBeNull();
    expect(screen.getByText(skill.description)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});
