export const AVATAR_MAX_BYTES = 5 * 1024 * 1024;
export const AVATAR_ACCEPT = "image/png,image/jpeg,image/webp,image/gif";

export function validateAvatarFile(
  file: File,
  t: (key: string) => string,
): string | null {
  if (file.size > AVATAR_MAX_BYTES) {
    return t("experts.avatarTooLarge");
  }
  const type = (file.type || "").split(";")[0].trim().toLowerCase();
  if (
    type &&
    type !== "application/octet-stream" &&
    !AVATAR_ACCEPT.split(",").includes(type)
  ) {
    return t("experts.avatarBadType");
  }
  return null;
}

export function pickImageFile(): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = AVATAR_ACCEPT;
    input.addEventListener("change", () => resolve(input.files?.[0] ?? null), {
      once: true,
    });
    input.click();
  });
}
