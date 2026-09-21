import type { NamedFileContent } from "./expertFileGroups";

export interface ComposerFileOverride {
  name: string;
  content: string;
}

export interface ComposerFilePatch {
  file_overrides: ComposerFileOverride[];
  omit_files: string[];
}

export function diffComposerFiles(
  original: NamedFileContent[],
  current: NamedFileContent[],
): ComposerFilePatch {
  const origMap = new Map(original.map((file) => [file.name, file.content]));
  const currMap = new Map(current.map((file) => [file.name, file.content]));
  const file_overrides: ComposerFileOverride[] = [];
  const omit_files: string[] = [];
  for (const [name, content] of currMap) {
    if (origMap.get(name) !== content) {
      file_overrides.push({ name, content });
    }
  }
  for (const name of origMap.keys()) {
    if (!currMap.has(name)) omit_files.push(name);
  }
  return { file_overrides, omit_files };
}

export function upsertComposerFile(
  files: NamedFileContent[],
  next: NamedFileContent,
): NamedFileContent[] {
  const idx = files.findIndex((file) => file.name === next.name);
  if (idx < 0) return [...files, next];
  return files.map((file, i) => (i === idx ? next : file));
}

const DEFAULT_PROMPT_FILES = ["AGENTS.md"];

/** Ensure create-time editors always expose the core prompt files. */
export function ensurePromptFiles(
  files: NamedFileContent[],
): NamedFileContent[] {
  const names = new Set(files.map((file) => file.name));
  const missing = DEFAULT_PROMPT_FILES.filter((name) => !names.has(name)).map(
    (name) => ({ name, content: "" }),
  );
  return missing.length ? [...files, ...missing] : files;
}

export function removeComposerSkill(
  files: NamedFileContent[],
  skillSlug: string,
): NamedFileContent[] {
  const prefix = `skills/${skillSlug}/`;
  return files.filter((file) => !file.name.startsWith(prefix));
}

export function removeComposerSubagent(
  files: NamedFileContent[],
  slug: string,
): NamedFileContent[] {
  return files.filter((file) => file.name !== `agents/${slug}.md`);
}
