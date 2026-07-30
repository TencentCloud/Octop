import JSZip from "jszip";

export type ParsedZipSkillFile = {
  path: string;
  contentBase64: string;
};

export type ParsedZipSkill = {
  slug: string;
  files: ParsedZipSkillFile[];
};

const SKIP_MARKERS = ["__macosx/", ".ds_store"];
const MAX_ZIP_BYTES = 64 * 1024 * 1024;

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function isSkippedPath(path: string): boolean {
  const lower = path.toLowerCase().replace(/\\/g, "/");
  return (
    SKIP_MARKERS.some((marker) => lower.includes(marker)) ||
    lower.endsWith("/")
  );
}

function normalizeZipPath(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\.\//, "").replace(/^\/+/, "");
}

function validateSlug(slug: string): string | null {
  const normalized = slug.trim();
  if (
    !normalized ||
    normalized.startsWith(".") ||
    normalized.includes("/") ||
    normalized.includes("\\") ||
    normalized.includes("\0")
  ) {
    return null;
  }
  return normalized;
}

function fallbackSlugFromFilename(filename: string): string {
  const base = filename.replace(/\.zip$/i, "").trim() || "imported-skill";
  return base.replace(/[\\/]+/g, "-");
}

/**
 * If every file sits under one outer folder and that folder is not itself a
 * skill root, strip the wrapper so nested skill folders become top-level.
 */
function stripOuterWrapper(
  entries: Array<{ zipPath: string; relPath: string }>,
): Array<{ zipPath: string; relPath: string }> {
  const tops = new Set(
    entries
      .map((entry) => entry.relPath.split("/")[0] || "")
      .filter(Boolean),
  );
  if (tops.size !== 1) return entries;
  const wrapper = [...tops][0];
  const wrapperIsSkill = entries.some(
    (entry) => entry.relPath === `${wrapper}/SKILL.md`,
  );
  if (wrapperIsSkill) return entries;

  const nested = entries
    .filter((entry) => entry.relPath.startsWith(`${wrapper}/`))
    .map((entry) => ({
      zipPath: entry.zipPath,
      relPath: entry.relPath.slice(wrapper.length + 1),
    }))
    .filter((entry) => entry.relPath.length > 0);
  return nested.length > 0 ? nested : entries;
}

export async function parseSkillZip(
  file: File,
  options?: { rootSlugFallback?: string },
): Promise<ParsedZipSkill[]> {
  if (file.size > MAX_ZIP_BYTES) {
    throw new Error("ZIP_TOO_LARGE");
  }

  const zip = await JSZip.loadAsync(file);
  const rawEntries: Array<{ zipPath: string; relPath: string }> = [];
  for (const [zipPath, zipObject] of Object.entries(zip.files)) {
    if (zipObject.dir) continue;
    const relPath = normalizeZipPath(zipPath);
    if (!relPath || isSkippedPath(relPath)) continue;
    rawEntries.push({ zipPath, relPath });
  }
  if (rawEntries.length === 0) {
    throw new Error("ZIP_EMPTY");
  }

  const entries = stripOuterWrapper(rawEntries);
  const groups = new Map<string, Array<{ zipPath: string; path: string }>>();

  for (const entry of entries) {
    if (!entry.relPath.includes("/")) {
      const list = groups.get("__root__") ?? [];
      list.push({ zipPath: entry.zipPath, path: entry.relPath });
      groups.set("__root__", list);
      continue;
    }
    const slash = entry.relPath.indexOf("/");
    const slug = entry.relPath.slice(0, slash);
    const path = entry.relPath.slice(slash + 1);
    if (!path) continue;
    const list = groups.get(slug) ?? [];
    list.push({ zipPath: entry.zipPath, path });
    groups.set(slug, list);
  }

  const skills: ParsedZipSkill[] = [];
  for (const [groupSlug, files] of groups) {
    if (!files.some((item) => item.path === "SKILL.md")) continue;

    const slug =
      groupSlug === "__root__"
        ? validateSlug(
            options?.rootSlugFallback || fallbackSlugFromFilename(file.name),
          )
        : validateSlug(groupSlug);
    if (!slug) continue;

    const parsedFiles: ParsedZipSkillFile[] = [];
    for (const item of files) {
      const zipFile = zip.file(item.zipPath);
      if (!zipFile) continue;
      const bytes = await zipFile.async("uint8array");
      parsedFiles.push({
        path: item.path,
        contentBase64: bytesToBase64(bytes),
      });
    }
    if (!parsedFiles.some((item) => item.path === "SKILL.md")) continue;
    skills.push({ slug, files: parsedFiles });
  }

  if (skills.length === 0) {
    throw new Error("ZIP_NO_SKILLS");
  }
  return skills;
}
