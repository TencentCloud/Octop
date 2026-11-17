import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../hooks/sseHelpers";
import {
  fileChangeChipLabel,
  lineChangeStats,
  summarizeTurnFileChanges,
} from "./turnFileChanges";

function tool(partial: {
  id?: string;
  name: string;
  arguments: Record<string, unknown> | string;
  output?: string;
  status?: ChatMessage["status"];
  errorCode?: string;
  editedFiles?: string[];
}): ChatMessage {
  return {
    id: partial.id ?? partial.name,
    role: "assistant",
    content: "",
    timestamp: 1,
    status: partial.status ?? "done",
    editedFiles: partial.editedFiles,
    toolData: {
      name: partial.name,
      arguments:
        typeof partial.arguments === "string"
          ? partial.arguments
          : JSON.stringify(partial.arguments),
      output: partial.output,
      errorCode: partial.errorCode,
    },
  };
}

describe("fileChangeChipLabel", () => {
  it("keeps the parent directory so same names stay distinct", () => {
    expect(fileChangeChipLabel("src/components/index.ts")).toBe(
      "components/index.ts",
    );
    expect(fileChangeChipLabel("app.py")).toBe("app.py");
  });
});

describe("lineChangeStats", () => {
  it("counts only the lines that differ inside a hunk", () => {
    expect(lineChangeStats("keep\nremove\n", "keep\nadd\n")).toEqual({
      additions: 1,
      deletions: 1,
    });
  });

  it("counts a new file body as additions", () => {
    expect(lineChangeStats("", "a\nb\n")).toEqual({
      additions: 2,
      deletions: 0,
    });
  });
});

describe("summarizeTurnFileChanges", () => {
  it("sums write and edit hunks across files", () => {
    const summary = summarizeTurnFileChanges([
      tool({
        name: "write_file",
        arguments: { file_path: "src/new.py", content: "a\nb\n" },
        output: "Updated file src/new.py",
      }),
      tool({
        name: "edit_file",
        arguments: {
          file_path: "src/old.py",
          old_string: "keep\nremove",
          new_string: "keep\nadd",
        },
        output:
          "Successfully replaced 1 instance(s) of the string in 'src/old.py'",
      }),
    ]);
    expect(summary.files.map((file) => file.displayPath)).toEqual([
      "src/new.py",
      "src/old.py",
    ]);
    expect(summary.additions).toBe(3);
    expect(summary.deletions).toBe(1);
    expect(summary.files[1]).toMatchObject({ additions: 1, deletions: 1 });
  });

  it("merges an absolute agent path with the workspace-relative edit", () => {
    const summary = summarizeTurnFileChanges(
      [
        tool({
          name: "write_file",
          arguments: {
            file_path: "/home/wally/.octop/agents/main/src/a.py",
            content: "one\n",
          },
        }),
        tool({
          name: "edit_file",
          arguments: {
            file_path: "src/a.py",
            old_string: "one",
            new_string: "two",
          },
          output:
            "Successfully replaced 1 instance(s) of the string in 'src/a.py'",
        }),
      ],
      "main",
    );
    expect(summary.files).toHaveLength(1);
    expect(summary.files[0]?.displayPath).toBe("src/a.py");
    expect(summary.files[0]?.openPath).toBe(
      "/home/wally/.octop/agents/main/src/a.py",
    );
    expect(summary.additions).toBe(1);
    expect(summary.deletions).toBe(0);
  });

  it("folds a later edit into the earlier replacement", () => {
    const summary = summarizeTurnFileChanges([
      tool({
        name: "edit_file",
        arguments: {
          file_path: "src/a.py",
          old_string: "alpha",
          new_string: "alpha beta",
        },
      }),
      tool({
        name: "edit_file",
        arguments: {
          file_path: "src/a.py",
          old_string: "beta",
          new_string: "gamma",
        },
      }),
    ]);
    expect(summary).toMatchObject({ additions: 1, deletions: 1 });
  });

  it("lets a later write replace earlier hunk totals for that file", () => {
    const summary = summarizeTurnFileChanges([
      tool({
        name: "edit_file",
        arguments: {
          file_path: "note.md",
          old_string: "a\nb",
          new_string: "a",
        },
      }),
      tool({
        name: "write_file",
        arguments: { file_path: "note.md", content: "z\n" },
      }),
    ]);
    expect(summary.files[0]).toMatchObject({ additions: 1, deletions: 0 });
  });

  it("multiplies a replace-all hunk by the reported occurrences", () => {
    const summary = summarizeTurnFileChanges([
      tool({
        name: "edit_file",
        arguments: {
          file_path: "src/a.py",
          old_string: "foo",
          new_string: "bar",
          replace_all: true,
        },
        output:
          "Successfully replaced 3 instance(s) of the string in 'src/a.py'",
      }),
    ]);
    expect(summary).toMatchObject({ additions: 3, deletions: 3 });
  });

  it("drops a failed edit and keeps a path that has no patch body", () => {
    const summary = summarizeTurnFileChanges([
      tool({
        name: "edit_file",
        arguments: {
          file_path: "missing.py",
          old_string: "a",
          new_string: "b",
        },
        output: "Error: File 'missing.py' not found",
        status: "error",
        errorCode: "tool_error",
      }),
      tool({
        id: "answer",
        name: "write_file",
        arguments: {},
        editedFiles: ["notes/plan.md"],
      }),
    ]);
    expect(summary.files.map((file) => file.displayPath)).toEqual([
      "notes/plan.md",
    ]);
    expect(summary.measured).toBe(false);
  });

  it("names the file still being edited from a partial tool call", () => {
    const summary = summarizeTurnFileChanges([
      tool({
        name: "edit_file",
        arguments: '{"file_path": "src/app.py", "old_string": "hel',
        status: "streaming",
      }),
    ]);
    expect(summary.activePath).toBe("src/app.py");
    expect(summary.files[0]?.pending).toBe(true);
    expect(summary.measured).toBe(false);
  });
});
