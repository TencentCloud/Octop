import { requestBlobMeta } from "../api/request";

export interface OfficePdfPreview {
  blob: Blob;
  digest?: string;
  missingFonts: string[];
}

export function parseOfficePdfMeta(headers: Headers): {
  digest?: string;
  missingFonts: string[];
} {
  const digest = headers.get("X-Octop-Office-Preview-Digest") || undefined;
  const fontsHeader = headers.get("X-Octop-Office-Missing-Fonts") || "";
  return {
    digest,
    missingFonts: fontsHeader
      .split(",")
      .map((item) => {
        const token = item.trim();
        if (!token) return "";
        try {
          return decodeURIComponent(token);
        } catch {
          return token;
        }
      })
      .filter(Boolean),
  };
}

export async function fetchOfficePdf(
  path: string,
  onProgress?: (loaded: number, total: number) => void,
  signal?: AbortSignal,
): Promise<OfficePdfPreview> {
  const { blob, headers } = await requestBlobMeta(path, { signal }, onProgress);
  const pdfBlob =
    blob.type === "application/pdf"
      ? blob
      : new Blob([blob], { type: "application/pdf" });
  return { blob: pdfBlob, ...parseOfficePdfMeta(headers) };
}
