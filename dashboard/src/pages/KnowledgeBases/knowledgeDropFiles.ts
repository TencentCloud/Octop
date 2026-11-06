/**
 * Expand a drop onto the existing knowledge-base upload path.
 * Directory entries become files whose ``webkitRelativePath`` matches a
 * folder-picker selection, including the dropped folder name and nested
 * segments. When the entry API is missing, the original ``FileList`` is used.
 */

type PlannedDrop =
  | { kind: "entry"; entry: FileSystemEntry }
  | { kind: "file"; file: File };

function readEntryFile(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => {
    entry.file(resolve, reject);
  });
}

/** ``readEntries`` returns one batch per call and signals the end with ``[]``. */
function readAllDirectoryEntries(
  reader: FileSystemDirectoryReader,
): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => {
    const all: FileSystemEntry[] = [];
    const readBatch = () => {
      reader.readEntries((batch) => {
        if (batch.length === 0) {
          resolve(all);
          return;
        }
        all.push(...batch);
        readBatch();
      }, reject);
    };
    readBatch();
  });
}

function withRelativePath(file: File, relativePath: string): File {
  if (!relativePath || file.webkitRelativePath === relativePath) return file;
  const define = (target: File) => {
    Object.defineProperty(target, "webkitRelativePath", {
      configurable: true,
      value: relativePath,
    });
    return target.webkitRelativePath === relativePath;
  };
  try {
    if (define(file)) return file;
  } catch {
    // The original File keeps a non-configurable empty webkitRelativePath.
  }
  const copy = new File([file], file.name, {
    type: file.type,
    lastModified: file.lastModified,
  });
  define(copy);
  return copy;
}

async function collectEntry(
  entry: FileSystemEntry,
  prefix: string,
  out: File[],
): Promise<void> {
  if (!entry.name || entry.name === "." || entry.name === "..") return;
  const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
  if (entry.isFile) {
    const file = await readEntryFile(entry as FileSystemFileEntry);
    out.push(withRelativePath(file, relative));
    return;
  }
  if (!entry.isDirectory) return;
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  const children = await readAllDirectoryEntries(reader);
  for (const child of children) {
    await collectEntry(child, relative, out);
  }
}

function plainFiles(dataTransfer: DataTransfer): File[] {
  return Array.from(dataTransfer.files ?? []);
}

/**
 * Read drop items synchronously, then walk directories. Callers must invoke
 * this before the drop event finishes so ``DataTransferItem`` stays readable.
 */
export async function filesFromKnowledgeDrop(
  dataTransfer: DataTransfer | null,
): Promise<File[]> {
  if (!dataTransfer) return [];
  const items = dataTransfer.items;
  if (!items || items.length === 0) return plainFiles(dataTransfer);

  const planned: PlannedDrop[] = [];
  let canReadEntries = false;
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    if (!item || item.kind !== "file") continue;
    if (typeof item.webkitGetAsEntry !== "function") {
      const file = item.getAsFile();
      if (file) planned.push({ kind: "file", file });
      continue;
    }
    canReadEntries = true;
    let entry: FileSystemEntry | null = null;
    try {
      entry = item.webkitGetAsEntry();
    } catch {
      entry = null;
    }
    if (entry) {
      planned.push({ kind: "entry", entry });
      continue;
    }
    const file = item.getAsFile();
    if (file) planned.push({ kind: "file", file });
  }

  if (!canReadEntries || planned.length === 0) return plainFiles(dataTransfer);

  const files: File[] = [];
  for (const item of planned) {
    if (item.kind === "file") {
      files.push(item.file);
      continue;
    }
    await collectEntry(item.entry, "", files);
  }
  return files;
}
