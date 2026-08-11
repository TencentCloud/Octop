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
  // Note: directories are intentionally NOT skipped — an empty directory (no
  // files underneath) must survive the import so it can be recreated.
  return SKIP_MARKERS.some((marker) => lower.includes(marker));
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

type ZipEntry = { zipPath: string; relPath: string; isDir: boolean };

/**
 * If every entry sits under one outer folder and that folder is not itself a
 * skill root, strip the wrapper so nested skill folders become top-level.
 */
function stripOuterWrapper(entries: ZipEntry[]): ZipEntry[] {
  const tops = new Set(
    entries.map((entry) => entry.relPath.split("/")[0] || "").filter(Boolean),
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
      isDir: entry.isDir,
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
  const rawEntries: ZipEntry[] = [];
  for (const [zipPath, zipObject] of Object.entries(zip.files)) {
    const relPath = normalizeZipPath(zipPath);
    if (!relPath || isSkippedPath(relPath)) continue;
    const isDir = Boolean(zipObject.dir) || relPath.endsWith("/");
    rawEntries.push({
      zipPath,
      relPath: isDir && !relPath.endsWith("/") ? `${relPath}/` : relPath,
      isDir,
    });
  }
  if (rawEntries.length === 0) {
    throw new Error("ZIP_EMPTY");
  }

  const entries = stripOuterWrapper(rawEntries);
  // A trailing "/" marks an empty directory entry; files carry their content.
  type GroupFile = { zipPath: string; path: string; isDir: boolean };
  const groups = new Map<string, GroupFile[]>();

  // Pass 1: group file entries by their top-level folder.
  for (const entry of entries) {
    if (entry.isDir) continue;
    if (!entry.relPath.includes("/")) {
      const list = groups.get("__root__") ?? [];
      list.push({ zipPath: entry.zipPath, path: entry.relPath, isDir: false });
      groups.set("__root__", list);
      continue;
    }
    const slash = entry.relPath.indexOf("/");
    const slug = entry.relPath.slice(0, slash);
    const path = entry.relPath.slice(slash + 1);
    if (!path) continue;
    const list = groups.get(slug) ?? [];
    list.push({ zipPath: entry.zipPath, path, isDir: false });
    groups.set(slug, list);
  }

  const isSkillGroup = (slug: string) =>
    groups.get(slug)?.some((item) => item.path === "SKILL.md") ?? false;
  const skillSlugs = new Set(
    [...groups.keys()].filter(
      (slug) => slug !== "__root__" && isSkillGroup(slug),
    ),
  );

  // Pass 2: attach EMPTY directories so they survive the import. JSZip (and
  // real zips) emit a dir entry for every folder — even ones that contain
  // files — so only folders with no files underneath actually need a marker.
  // A skill's own root folder is implied by the slug and must not be recreated.
  const fileRelPaths = entries
    .filter((entry) => !entry.isDir)
    .map((entry) => entry.relPath);
  const dirHasFiles = (dirRelPath: string): boolean => {
    const prefix = `${dirRelPath.replace(/\/$/, "")}/`;
    return fileRelPaths.some((p) => p.startsWith(prefix));
  };
  for (const entry of entries) {
    if (!entry.isDir) continue;
    if (dirHasFiles(entry.relPath)) continue;
    const parts = entry.relPath.split("/").filter(Boolean);
    if (parts.length === 0) continue;
    if (parts.length === 1) {
      if (skillSlugs.has(parts[0])) continue;
      const list = groups.get("__root__") ?? [];
      list.push({ zipPath: entry.zipPath, path: `${parts[0]}/`, isDir: true });
      groups.set("__root__", list);
      continue;
    }
    const slug = parts[0];
    const path = `${parts.slice(1).join("/")}/`;
    const list = groups.get(slug) ?? [];
    list.push({ zipPath: entry.zipPath, path, isDir: true });
    groups.set(slug, list);
  }

  // A root-level SKILL.md means the archive root is itself a skill. Subfolders
  // that do not contain their own SKILL.md are supporting files and directories
  // (scripts/, references/, images/, …) — keep them under the root skill
  // instead of dropping them, so nested directories survive the import.
  const rootGroup = groups.get("__root__");
  if (rootGroup?.some((item) => item.path === "SKILL.md")) {
    for (const [groupSlug, files] of groups) {
      if (groupSlug === "__root__") continue;
      if (files.some((item) => item.path === "SKILL.md")) continue;
      for (const item of files) {
        rootGroup.push({
          zipPath: item.zipPath,
          path: `${groupSlug}/${item.path}`,
          isDir: item.isDir,
        });
      }
    }
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
      if (item.isDir || item.path.endsWith("/")) {
        // Empty directory — no content, only the trailing-"/" path marker.
        parsedFiles.push({ path: item.path, contentBase64: "" });
        continue;
      }
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
