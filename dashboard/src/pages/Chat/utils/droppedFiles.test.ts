import { describe, expect, it } from "vitest";
import {
  dragHasFiles,
  filesFromSnapshot,
  MAX_CHAT_UPLOAD_FILES,
  snapshotDroppedEntries,
  type DropSnapshot,
} from "./droppedFiles";

function fileEntry(file: File, fullPath = `/${file.name}`): FileSystemEntry {
  return {
    isFile: true,
    isDirectory: false,
    name: file.name,
    fullPath,
    file(success: (next: File) => void) {
      success(file);
    },
  } as unknown as FileSystemFileEntry;
}

function directoryEntry(
  name: string,
  children: FileSystemEntry[],
  fullPath = `/${name}`,
): FileSystemEntry {
  return {
    isFile: false,
    isDirectory: true,
    name,
    fullPath,
    createReader() {
      let pending = children;
      return {
        readEntries(success: (entries: FileSystemEntry[]) => void) {
          const batch = pending;
          pending = [];
          success(batch);
        },
      };
    },
  } as unknown as FileSystemDirectoryEntry;
}

function dropSource(
  items: DataTransferItem[],
  files: File[] = [],
): DataTransfer {
  return { items, files } as unknown as DataTransfer;
}

describe("snapshotDroppedEntries", () => {
  it("keeps several loose files from one drop", () => {
    const first = new File(["a"], "a.txt", { type: "text/plain" });
    const second = new File(["b"], "b.md", { type: "text/markdown" });
    const snapshot = snapshotDroppedEntries(
      dropSource([
        {
          kind: "file",
          getAsFile: () => first,
        } as DataTransferItem,
        {
          kind: "file",
          getAsFile: () => second,
        } as DataTransferItem,
      ]),
    );

    expect(snapshot.hadFileItems).toBe(true);
    expect(snapshot.entries).toEqual([]);
    expect(snapshot.files.map((file) => file.name)).toEqual(["a.txt", "b.md"]);
  });

  it("walks a dropped folder instead of the empty directory placeholder", async () => {
    const readme = new File(["# hi"], "README.md", { type: "text/markdown" });
    const note = new File(["note"], "note.txt", { type: "text/plain" });
    const folder = directoryEntry("docs", [
      fileEntry(readme, "/docs/README.md"),
      directoryEntry(
        "nested",
        [fileEntry(note, "/docs/nested/note.txt")],
        "/docs/nested",
      ),
    ]);
    const snapshot = snapshotDroppedEntries(
      dropSource(
        [
          {
            kind: "file",
            webkitGetAsEntry: () => folder,
            getAsFile: () => new File([], "docs"),
          } as unknown as DataTransferItem,
        ],
        [new File([], "docs")],
      ),
    );

    expect(snapshot.files).toEqual([]);
    const collected = await filesFromSnapshot(snapshot);
    expect(collected.truncated).toBe(false);
    expect(collected.files.map((file) => file.name)).toEqual([
      "README.md",
      "note.txt",
    ]);
  });

  it("reports an empty folder as a file drop with no files", async () => {
    const snapshot = snapshotDroppedEntries(
      dropSource([
        {
          kind: "file",
          webkitGetAsEntry: () => directoryEntry("empty", []),
          getAsFile: () => null,
        } as unknown as DataTransferItem,
      ]),
    );

    expect(snapshot.hadFileItems).toBe(true);
    await expect(filesFromSnapshot(snapshot)).resolves.toEqual({
      files: [],
      truncated: false,
    });
  });

  it("keeps the first 500 files and reports the rest", async () => {
    const entries = Array.from({ length: MAX_CHAT_UPLOAD_FILES + 1 }, (_, i) =>
      fileEntry(new File(["x"], `f${i}.txt`)),
    );
    const collected = await filesFromSnapshot({
      entries,
      files: [],
      hadFileItems: true,
    });
    expect(collected.files).toHaveLength(MAX_CHAT_UPLOAD_FILES);
    expect(collected.truncated).toBe(true);
    expect(collected.files[0]?.name).toBe("f0.txt");
  });

  it("ignores non-file drags", () => {
    const snapshot = snapshotDroppedEntries(
      dropSource([
        { kind: "string", getAsFile: () => null } as DataTransferItem,
      ]),
    );
    expect(snapshot).toEqual<DropSnapshot>({
      entries: [],
      files: [],
      hadFileItems: false,
    });
  });
});

describe("dragHasFiles", () => {
  it("is true only when the drag carries files", () => {
    expect(dragHasFiles({ types: ["Files"] } as unknown as DataTransfer)).toBe(
      true,
    );
    expect(
      dragHasFiles({ types: ["text/plain"] } as unknown as DataTransfer),
    ).toBe(false);
    expect(dragHasFiles(null)).toBe(false);
  });
});
