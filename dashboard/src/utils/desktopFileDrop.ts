/** CustomEvent the desktop shell dispatches after it has expanded dropped paths. */
export const DESKTOP_FILE_DROP_EVENT = "octop:desktop-file-drop";

export interface DesktopDropFileRef {
  name: string;
  url: string;
  type?: string;
  size?: number;
}

export interface DesktopFileDropDetail {
  files?: DesktopDropFileRef[];
  truncated?: boolean;
  max?: number;
}

/** Fetch loopback URLs the desktop shell minted for a drop and turn them into File objects. */
export async function filesFromDesktopDrop(
  detail: DesktopFileDropDetail | null | undefined,
): Promise<File[]> {
  const refs = detail?.files ?? [];
  const files: File[] = [];
  for (const item of refs) {
    if (!item?.url || !item.name) continue;
    const response = await fetch(item.url);
    if (!response.ok) {
      throw new Error(`desktop drop fetch failed: ${response.status}`);
    }
    const blob = await response.blob();
    files.push(
      new File([blob], item.name, { type: item.type || blob.type || "" }),
    );
  }
  return files;
}
