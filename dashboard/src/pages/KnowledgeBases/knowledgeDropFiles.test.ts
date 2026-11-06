import { describe, expect, it } from "vitest";
import { filesFromKnowledgeDrop } from "./knowledgeDropFiles";

function fileEntry(file: File): FileSystemEntry {
  return {
    isFile: true,
    isDirectory: false,
    name: file.name,
    fullPath: `/${file.name}`,
    file(success: (next: File) => void) {
      success(file);
    },
  } as unknown as FileSystemFileEntry;
}

function directoryEntry(
  name: string,
  batches: FileSystemEntry[][],
): FileSystemEntry {
  return {
    isFile: false,
    isDirectory: true,
    name,
    fullPath: `/${name}`,
    createReader() {
      let index = 0;
      return {
        readEntries(success: (entries: FileSystemEntry[]) => void) {
          const batch = batches[index] ?? [];
          index += 1;
          success(batch);
        },
      };
    },
  } as unknown as FileSystemDirectoryEntry;
}

function dropped(
  items: Partial<DataTransferItem>[],
  files: File[] = [],
): DataTransfer {
  return { items, files } as unknown as DataTransfer;
}

describe("filesFromKnowledgeDrop", () => {
  it("falls back to the original file list when entries are unavailable", async () => {
    const note = new File(["note"], "note.txt", { type: "text/plain" });
    const files = await filesFromKnowledgeDrop(
      dropped(
        [{ kind: "file", getAsFile: () => note } as DataTransferItem],
        [note],
      ),
    );
    expect(files).toEqual([note]);
    expect(files[0]?.webkitRelativePath ?? "").toBe("");
  });

  it("reads every directory batch and keeps nested relative paths", async () => {
    const readme = new File(["# hi"], "README.md", { type: "text/markdown" });
    const note = new File(["note"], "a.txt", { type: "text/plain" });
    const extra = new File(["more"], "b.txt", { type: "text/plain" });
    const folder = directoryEntry("资料", [
      [fileEntry(readme)],
      [directoryEntry("层级", [[fileEntry(note)], []]), fileEntry(extra)],
      [],
    ]);
    const files = await filesFromKnowledgeDrop(
      dropped([
        {
          kind: "file",
          webkitGetAsEntry: () => folder,
          getAsFile: () => new File([], "资料"),
        } as unknown as DataTransferItem,
      ]),
    );
    expect(files.map((file) => file.webkitRelativePath)).toEqual([
      "资料/README.md",
      "资料/层级/a.txt",
      "资料/b.txt",
    ]);
    expect(files.map((file) => file.name)).toEqual([
      "README.md",
      "a.txt",
      "b.txt",
    ]);
  });

  it("keeps loose files beside a dropped folder", async () => {
    const nested = new File(["a"], "a.txt", { type: "text/plain" });
    const loose = new File(["b"], "b.txt", { type: "text/plain" });
    const files = await filesFromKnowledgeDrop(
      dropped([
        {
          kind: "file",
          webkitGetAsEntry: () => fileEntry(loose),
          getAsFile: () => loose,
        } as unknown as DataTransferItem,
        {
          kind: "file",
          webkitGetAsEntry: () =>
            directoryEntry("docs", [[fileEntry(nested)], []]),
          getAsFile: () => new File([], "docs"),
        } as unknown as DataTransferItem,
      ]),
    );
    expect(files.map((file) => file.webkitRelativePath || file.name)).toEqual([
      "b.txt",
      "docs/a.txt",
    ]);
  });

  it("drops an empty folder without uploading a placeholder", async () => {
    const files = await filesFromKnowledgeDrop(
      dropped(
        [
          {
            kind: "file",
            webkitGetAsEntry: () => directoryEntry("empty", [[]]),
            getAsFile: () => new File([], "empty"),
          } as unknown as DataTransferItem,
        ],
        [new File([], "empty")],
      ),
    );
    expect(files).toEqual([]);
  });
});
