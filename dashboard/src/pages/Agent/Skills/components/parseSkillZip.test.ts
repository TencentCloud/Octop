import { describe, expect, it } from "vitest";
import JSZip from "jszip";
import { parseSkillZip } from "./parseSkillZip";

async function zipFromTree(
  tree: Record<string, string | Uint8Array>,
  filename = "skills.zip",
): Promise<File> {
  const zip = new JSZip();
  for (const [path, content] of Object.entries(tree)) {
    zip.file(path, content);
  }
  const blob = await zip.generateAsync({ type: "blob" });
  return new File([blob], filename, { type: "application/zip" });
}

function decodeBase64(value: string): string {
  return atob(value);
}

describe("parseSkillZip", () => {
  it("parses one folder per skill and keeps sibling files", async () => {
    const file = await zipFromTree({
      "writer/SKILL.md": "---\nname: writer\ndescription: x\n---\n",
      "writer/notes.txt": "hi",
      "reader/SKILL.md": "---\nname: reader\ndescription: y\n---\n",
    });

    const skills = await parseSkillZip(file);
    expect(skills.map((skill) => skill.slug).sort()).toEqual([
      "reader",
      "writer",
    ]);
    const writer = skills.find((skill) => skill.slug === "writer");
    expect(writer?.files.map((item) => item.path).sort()).toEqual([
      "SKILL.md",
      "notes.txt",
    ]);
    expect(
      decodeBase64(
        writer?.files.find((item) => item.path === "notes.txt")?.contentBase64 ??
          "",
      ),
    ).toBe("hi");
  });

  it("strips a single outer wrapper folder", async () => {
    const file = await zipFromTree({
      "bundle/alpha/SKILL.md": "---\nname: alpha\ndescription: a\n---\n",
      "bundle/beta/SKILL.md": "---\nname: beta\ndescription: b\n---\n",
    });

    const skills = await parseSkillZip(file);
    expect(skills.map((skill) => skill.slug).sort()).toEqual(["alpha", "beta"]);
  });

  it("does not strip wrapper when the wrapper itself is a skill", async () => {
    const file = await zipFromTree({
      "bundle/SKILL.md": "---\nname: bundle\n---\n",
      "bundle/nested/extra.txt": "x",
    });

    const skills = await parseSkillZip(file);
    expect(skills).toHaveLength(1);
    expect(skills[0].slug).toBe("bundle");
    expect(skills[0].files.map((item) => item.path).sort()).toEqual([
      "SKILL.md",
      "nested/extra.txt",
    ]);
  });

  it("treats a root-level SKILL.md as one skill using the zip filename", async () => {
    const file = await zipFromTree(
      {
        "SKILL.md": "---\nname: solo\n---\n",
        "util.py": "print(1)\n",
      },
      "my-cool-skill.zip",
    );

    const skills = await parseSkillZip(file);
    expect(skills).toHaveLength(1);
    expect(skills[0].slug).toBe("my-cool-skill");
    expect(skills[0].files.map((item) => item.path).sort()).toEqual([
      "SKILL.md",
      "util.py",
    ]);
  });

  it("does not attach sibling folders to a root-level skill", async () => {
    // Nested folders without their own SKILL.md are ignored; only root files
    // belong to the root skill group.
    const file = await zipFromTree(
      {
        "SKILL.md": "---\nname: solo\n---\n",
        "helpers/util.py": "print(1)\n",
      },
      "solo.zip",
    );

    const skills = await parseSkillZip(file);
    expect(skills).toHaveLength(1);
    expect(skills[0].slug).toBe("solo");
    expect(skills[0].files.map((item) => item.path)).toEqual(["SKILL.md"]);
  });

  it("prefers rootSlugFallback for root-level skills", async () => {
    const file = await zipFromTree(
      { "SKILL.md": "---\nname: solo\n---\n" },
      "archive.zip",
    );

    const skills = await parseSkillZip(file, { rootSlugFallback: "custom-slug" });
    expect(skills).toHaveLength(1);
    expect(skills[0].slug).toBe("custom-slug");
  });

  it("skips macOS metadata and folders without SKILL.md", async () => {
    const file = await zipFromTree({
      "good/SKILL.md": "---\nname: good\n---\n",
      "good/.DS_Store": "junk",
      "__MACOSX/good/._SKILL.md": "meta",
      "docs/readme.md": "not a skill",
    });

    const skills = await parseSkillZip(file);
    expect(skills.map((skill) => skill.slug)).toEqual(["good"]);
    expect(skills[0].files.map((item) => item.path)).toEqual(["SKILL.md"]);
  });

  it("skips invalid top-level slug folders", async () => {
    const file = await zipFromTree({
      ".hidden/SKILL.md": "---\nname: hidden\n---\n",
      "valid/SKILL.md": "---\nname: valid\n---\n",
    });

    const skills = await parseSkillZip(file);
    expect(skills.map((skill) => skill.slug)).toEqual(["valid"]);
  });

  it("rejects empty archives", async () => {
    const file = await zipFromTree({});
    await expect(parseSkillZip(file)).rejects.toThrow("ZIP_EMPTY");
  });

  it("rejects archives with only metadata", async () => {
    const file = await zipFromTree({
      "__MACOSX/foo": "x",
      ".DS_Store": "y",
    });
    await expect(parseSkillZip(file)).rejects.toThrow("ZIP_EMPTY");
  });

  it("rejects archives without any SKILL.md", async () => {
    const file = await zipFromTree({
      "alpha/readme.md": "no skill",
      "beta/notes.txt": "still no",
    });
    await expect(parseSkillZip(file)).rejects.toThrow("ZIP_NO_SKILLS");
  });

  it("rejects oversized zip files", async () => {
    const file = new File([new Uint8Array(8)], "huge.zip", {
      type: "application/zip",
    });
    Object.defineProperty(file, "size", { value: 65 * 1024 * 1024 });
    await expect(parseSkillZip(file)).rejects.toThrow("ZIP_TOO_LARGE");
  });

  it("encodes binary sibling files as base64", async () => {
    const bytes = new Uint8Array([0, 1, 2, 255]);
    const file = await zipFromTree({
      "bin/SKILL.md": "---\nname: bin\n---\n",
      "bin/data.bin": bytes,
    });

    const skills = await parseSkillZip(file);
    const encoded =
      skills[0].files.find((item) => item.path === "data.bin")?.contentBase64 ??
      "";
    expect(Uint8Array.from(atob(encoded), (ch) => ch.charCodeAt(0))).toEqual(
      bytes,
    );
  });
});
