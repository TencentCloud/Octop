import { describe, expect, it, beforeEach, vi } from "vitest";
import {
  createEvent,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ProjectMember } from "../../../api/modules/projects";
import TaskCreateModal from "./TaskCreateModal";

const getMock = vi.fn();
const createTaskMock = vi.fn();
const dispatchTaskMock = vi.fn();
const listMembersMock = vi.fn();
const listTagsMock = vi.fn();
const listFieldsMock = vi.fn();
const uploadMock = vi.fn();
const deleteAttachmentMock = vi.fn();

vi.mock("@/utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock("../../../api/modules/projects", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../../api/modules/projects")
  >();
  return {
    ...actual,
    projectsApi: {
      ...actual.projectsApi,
      get: (...args: unknown[]) => getMock(...args),
      createTask: (...args: unknown[]) => createTaskMock(...args),
      dispatchTask: (...args: unknown[]) => dispatchTaskMock(...args),
      listMembers: (...args: unknown[]) => listMembersMock(...args),
    },
  };
});

vi.mock("../../../api/modules/projectMetadata", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../../api/modules/projectMetadata")
  >();
  return {
    ...actual,
    projectMetadataApi: {
      ...actual.projectMetadataApi,
      listTags: (...args: unknown[]) => listTagsMock(...args),
      listCustomFields: (...args: unknown[]) => listFieldsMock(...args),
      uploadPendingAttachment: (...args: unknown[]) => uploadMock(...args),
      deleteAttachment: (...args: unknown[]) => deleteAttachmentMock(...args),
    },
  };
});

const MEMBERS: ProjectMember[] = [
  {
    subject_type: "agent",
    subject_id: "agent-a",
    user_id: null,
    role: "member",
    created_at: 1,
  },
  {
    subject_type: "user",
    subject_id: "7",
    user_id: 7,
    role: "owner",
    created_at: 1,
  },
];

const titleInput = () => screen.getByLabelText("projects.createTaskTitle");
const descriptionInput = () =>
  screen.getByLabelText("projects.createTaskDescription");
const submitButton = () =>
  screen.getByRole("button", { name: /projects\.createTaskSubmit/ });

/** Mounts the dialog and types `value` into the inline title. */
async function open(value: string) {
  const onClose = vi.fn();
  const onCreated = vi.fn();
  render(
    <TaskCreateModal
      open
      projectId="prj_1"
      tasks={[]}
      canEdit
      onClose={onClose}
      onCreated={onCreated}
    />,
  );
  const user = userEvent.setup();
  if (value) await user.type(titleInput(), value);
  return { user, onClose, onCreated };
}

describe("TaskCreateModal（R3 / AC-U-8）", () => {
  beforeEach(() => {
    getMock
      .mockReset()
      .mockResolvedValue({ project_id: "prj_1", name: "Apollo" });
    createTaskMock.mockReset().mockResolvedValue({ task_id: "tsk_1" });
    dispatchTaskMock.mockReset();
    listMembersMock.mockReset().mockResolvedValue(MEMBERS);
    listTagsMock
      .mockReset()
      .mockResolvedValue([
        { tag_id: "tag_1", name: "紧急", color: "", created_at: 1 },
      ]);
    listFieldsMock.mockReset().mockResolvedValue([
      {
        field_id: "fld_1",
        key: "note",
        label: "备注",
        type: "text",
        required: false,
        options: [],
        sort_order: 0,
        created_at: 1,
        updated_at: 1,
      },
    ]);
    uploadMock.mockReset();
    deleteAttachmentMock.mockReset().mockResolvedValue({ deleted: true });
  });

  it("AC-U-8: 面包屑 + 内联标题/描述 + 10 个元素 + ⌘↵ 提交按钮", async () => {
    const { user } = await open("");

    // 面包屑「<项目> › 手动创建」。
    expect(await screen.findByText("Apollo")).toBeInTheDocument();
    expect(
      screen.getByText("projects.createTaskBreadcrumb"),
    ).toBeInTheDocument();
    // 内联大标题（无 label 框）+ 内联描述。
    expect(titleInput()).toBeInTheDocument();
    expect(descriptionInput()).toBeInTheDocument();
    // chip 工具条：状态 / 优先级 / 分配 / 标签 / 项目 / ···更多。
    for (const key of [
      "chipStatus",
      "chipPriority",
      "chipAssignee",
      "chipTags",
      "chipProject",
      "chipMore",
    ]) {
      expect(
        screen.getByRole("button", { name: `projects.${key}` }),
      ).toBeInTheDocument();
    }
    // 「···更多」里：截止日期 / 开始日期 / 父任务 / 子任务 / 自定义字段。
    await user.click(screen.getByRole("button", { name: "projects.chipMore" }));
    await waitFor(() =>
      expect(
        screen.getAllByLabelText("projects.chipDueAt").length,
      ).toBeGreaterThan(0),
    );
    for (const key of ["chipDueAt", "chipStartAt", "chipParentTask"]) {
      expect(
        screen.getAllByLabelText(`projects.${key}`).length,
      ).toBeGreaterThan(0);
    }
    expect(screen.getAllByText("projects.chipSubtasks").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getAllByText("projects.chipCustomFields").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("备注")).toBeInTheDocument();
    // 附件 / 切换到智能体 / 继续创建 / 提交。
    expect(screen.getByLabelText("projects.attachFile")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "projects.switchToAgent" }),
    ).toBeInTheDocument();
    expect(screen.getByText("projects.createAndContinue")).toBeInTheDocument();
    expect(submitButton()).toBeInTheDocument();
  });

  it("S-5: IME 组合态按 ⌘/Ctrl+Enter 不提交且不 preventDefault；非组合态才提交", async () => {
    await open("中文任务");

    // 组合态：Enter 是「选词」，既不能提交也不能吞掉事件。
    const composing = createEvent.keyDown(titleInput(), {
      key: "Enter",
      metaKey: true,
      isComposing: true,
    });
    fireEvent(titleInput(), composing);
    expect(composing.defaultPrevented).toBe(false);
    expect(createTaskMock).not.toHaveBeenCalled();

    // 组合态下的裸 Enter（标题框）同样不提交。
    const composingPlain = createEvent.keyDown(titleInput(), {
      key: "Enter",
      isComposing: true,
    });
    fireEvent(titleInput(), composingPlain);
    expect(composingPlain.defaultPrevented).toBe(false);
    expect(createTaskMock).not.toHaveBeenCalled();

    // 对照：非组合态的 ⌘+Enter 提交（并 preventDefault）。
    const plain = createEvent.keyDown(titleInput(), {
      key: "Enter",
      metaKey: true,
    });
    fireEvent(titleInput(), plain);
    expect(plain.defaultPrevented).toBe(true);
    await waitFor(() => expect(createTaskMock).toHaveBeenCalledTimes(1));
  });

  it("S-5: 标题裸 Enter 提交；描述裸 Enter 换行不提交", async () => {
    await open("任务一");

    fireEvent.keyDown(descriptionInput(), { key: "Enter" });
    expect(createTaskMock).not.toHaveBeenCalled();

    fireEvent.keyDown(titleInput(), { key: "Enter" });
    await waitFor(() => expect(createTaskMock).toHaveBeenCalledTimes(1));
  });

  it("AC-U-7/AC-U-8: 一次请求携带目标列与全部已选项（无两段式）", async () => {
    const { user } = await open("任务一");

    await user.click(
      screen.getByRole("button", { name: "projects.chipStatus" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "projects.taskStatusDoing" }),
    );
    await user.click(screen.getByRole("button", { name: "projects.chipTags" }));
    await user.click(await screen.findByRole("button", { name: /紧急/ }));
    await user.click(
      screen.getByRole("button", { name: "projects.chipPriority" }),
    );
    await user.click(await screen.findByRole("button", { name: "2" }));

    await user.click(submitButton());

    await waitFor(() => expect(createTaskMock).toHaveBeenCalledTimes(1));
    const [projectId, body] = createTaskMock.mock.calls[0];
    expect(projectId).toBe("prj_1");
    expect(body).toMatchObject({
      title: "任务一",
      status: "doing",
      priority: 2,
      tags: ["tag_1"],
      custom_fields: {},
      attachment_ids: [],
      parent_id: null,
    });
    // 只发一次请求：没有「先建 todo 再 move」的第二段。
    expect(dispatchTaskMock).not.toHaveBeenCalled();
  });

  it("AC-U-21/S-4: 「继续创建」开启时提交后不关弹窗，清空 3 项、保留其余选择", async () => {
    const { user, onClose } = await open("任务一");
    await user.type(descriptionInput(), "描述");
    await user.click(
      screen.getByRole("button", { name: "projects.chipStatus" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "projects.taskStatusDoing" }),
    );
    await user.click(
      screen.getByRole("checkbox", { name: "projects.createAndContinue" }),
    );

    await user.click(submitButton());
    await waitFor(() => expect(createTaskMock).toHaveBeenCalledTimes(1));

    expect(onClose).not.toHaveBeenCalled();
    // 清空 title / description（due_at 未设置）。
    expect(titleInput()).toHaveValue("");
    expect(descriptionInput()).toHaveValue("");
    // 保留状态选择（chip 摘要仍是 doing）。
    expect(
      screen.getByRole("button", { name: "projects.chipStatus" }),
    ).toHaveTextContent("projects.taskStatusDoing");

    // 第二次提交仍带同一状态 → 证明「保留」生效。
    await user.type(titleInput(), "任务二");
    await user.click(submitButton());
    await waitFor(() => expect(createTaskMock).toHaveBeenCalledTimes(2));
    expect(createTaskMock.mock.calls[1][1].status).toBe("doing");
  });

  it("AC-U-21: 「继续创建」关闭时提交成功后关闭弹窗", async () => {
    const { user, onClose, onCreated } = await open("任务一");

    await user.click(submitButton());

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onCreated).toHaveBeenCalled();
  });

  it("FIND-3/§8.1: 「切换到智能体」只写 assignee，不发派单请求", async () => {
    const { user } = await open("任务一");
    const before = createTaskMock.mock.calls.length;

    await user.click(
      screen.getByRole("button", { name: "projects.switchToAgent" }),
    );
    await user.click(
      await screen.findByRole("button", { name: /agent:agent-a/ }),
    );

    // 选择智能体本身不发任何请求（任务尚不存在）。
    expect(createTaskMock.mock.calls.length).toBe(before);
    expect(dispatchTaskMock).not.toHaveBeenCalled();

    await user.click(submitButton());
    await waitFor(() => expect(createTaskMock).toHaveBeenCalledTimes(1));
    const body = createTaskMock.mock.calls[0][1];
    expect(body.assignee_type).toBe("agent");
    expect(body.assignee_id).toBe("agent-a");
    expect(dispatchTaskMock).not.toHaveBeenCalled();
  });

  it("AC-U-19/§7.5: 📎 先暂存上传；未提交就关闭则尽力删除暂存件且不阻塞关闭", async () => {
    const { user, onClose } = await open("任务一");
    uploadMock.mockResolvedValue({
      artifact_id: "art_1",
      name: "note.txt",
      size: 5,
      mime: "text/plain",
      created_at: 1,
      uploader: "tester",
      task_id: null,
    });

    const file = new File(["hello"], "note.txt", { type: "text/plain" });
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => expect(uploadMock).toHaveBeenCalledWith("prj_1", file));
    expect(await screen.findByText("note.txt")).toBeInTheDocument();

    await user.click(screen.getByLabelText("common.cancel"));
    await waitFor(() =>
      expect(deleteAttachmentMock).toHaveBeenCalledWith("prj_1", "art_1"),
    );
    expect(onClose).toHaveBeenCalled();
  });
});
