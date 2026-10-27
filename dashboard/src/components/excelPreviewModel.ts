import type { CSSProperties } from "react";
import type { Color, Style, Worksheet } from "exceljs";
import type { WorkSheet } from "xlsx";

export const EXCEL_MAX_ROWS = 500;
export const EXCEL_MAX_COLS = 40;

export interface PreviewCell {
  text: string;
  style: CSSProperties;
  rowSpan: number;
  colSpan: number;
  covered: boolean;
  formula?: string;
}

export interface PreviewSheet {
  name: string;
  columns: { label: string; width: number }[];
  rows: { number: number; height?: number; cells: PreviewCell[] }[];
  truncated: boolean;
}

export interface PreviewWorkbook {
  sheets: PreviewSheet[];
  media: { name: string; dataUrl: string }[];
}

function colorCss(
  color: (Partial<Color> & { tint?: number }) | undefined,
  theme: string[],
): string | undefined {
  const rgb =
    color?.argb?.slice(-6) ??
    (color?.theme !== undefined ? theme[color.theme] : undefined);
  if (!rgb || !/^[a-f\d]{6}$/i.test(rgb)) return undefined;
  const tint = Math.max(-1, Math.min(1, color?.tint ?? 0));
  const adjusted = [0, 2, 4].map((start) => {
    const channel = parseInt(rgb.slice(start, start + 2), 16);
    return Math.round(
      tint < 0 ? channel * (1 + tint) : channel + (255 - channel) * tint,
    )
      .toString(16)
      .padStart(2, "0");
  });
  return `#${adjusted.join("")}`;
}

function cellStyle(style: Partial<Style>, theme: string[]): CSSProperties {
  const { font, fill, alignment, border } = style;
  const result: CSSProperties = {
    color: colorCss(font?.color, theme) ?? "#000000",
    backgroundColor:
      fill?.type === "pattern" && fill.pattern === "solid"
        ? colorCss(fill.fgColor, theme) ?? "#ffffff"
        : "#ffffff",
    fontFamily: font?.name,
    fontSize: font?.size ? `${Math.min(200, font.size)}pt` : undefined,
    fontWeight: font?.bold ? "bold" : undefined,
    fontStyle: font?.italic ? "italic" : undefined,
    textDecoration:
      [font?.underline ? "underline" : "", font?.strike ? "line-through" : ""]
        .filter(Boolean)
        .join(" ") || undefined,
    textAlign:
      alignment?.horizontal === "centerContinuous"
        ? "center"
        : alignment?.horizontal === "distributed"
        ? "justify"
        : alignment?.horizontal === "fill"
        ? "left"
        : alignment?.horizontal,
    verticalAlign:
      alignment?.vertical === "middle"
        ? "middle"
        : alignment?.vertical === "distributed" ||
          alignment?.vertical === "justify"
        ? "middle"
        : alignment?.vertical ?? "bottom",
    whiteSpace: alignment?.wrapText ? "pre-wrap" : "pre",
  };
  const sides = ["top", "right", "bottom", "left"] as const;
  for (const side of sides) {
    const edge = border?.[side];
    if (!edge?.style) continue;
    const width =
      edge.style === "thick" ? 3 : edge.style.startsWith("medium") ? 2 : 1;
    const pattern =
      edge.style === "double"
        ? "double"
        : /dash/i.test(edge.style)
        ? "dashed"
        : edge.style === "dotted"
        ? "dotted"
        : "solid";
    const property = `border${side[0].toUpperCase()}${side.slice(1)}` as
      | "borderTop"
      | "borderRight"
      | "borderBottom"
      | "borderLeft";
    result[property] = `${pattern === "double" ? 3 : width}px ${pattern} ${
      colorCss(edge.color, theme) ?? "#000000"
    }`;
  }
  return result;
}

/** Keep leading blanks and row/column coordinates; clipping never shifts data. */
function buildSheet(
  name: string,
  sheet: WorkSheet,
  xlsx: typeof import("xlsx"),
  styled: Worksheet | undefined,
  theme: string[],
): PreviewSheet {
  const range = xlsx.utils.decode_range(sheet["!ref"] ?? "A1");
  const rowCount = Math.min(EXCEL_MAX_ROWS, range.e.r + 1);
  const colCount = Math.min(EXCEL_MAX_COLS, range.e.c + 1);
  const columns = Array.from({ length: colCount }, (_, col) => ({
    label: xlsx.utils.encode_col(col),
    width: Math.max(
      24,
      Math.min(
        1000,
        (styled?.getColumn(col + 1).width ?? sheet["!cols"]?.[col]?.wch ?? 12) *
          7 +
          5,
      ),
    ),
  }));
  const rows = Array.from({ length: rowCount }, (_, row) => ({
    number: row + 1,
    height: styled?.getRow(row + 1).height
      ? (styled.getRow(row + 1).height * 4) / 3
      : undefined,
    cells: Array.from({ length: colCount }, (_, col): PreviewCell => {
      const address = xlsx.utils.encode_cell({ r: row, c: col });
      const cell = sheet[address];
      const styledCell = styled?.getCell(row + 1, col + 1);
      const formula =
        styledCell?.formula && styledCell.result == null
          ? styledCell.formula
          : cell?.f && cell.v == null
          ? cell.f
          : undefined;
      const text = formula
        ? `=${formula}`
        : cell
        ? xlsx.utils.format_cell(cell)
        : "";
      return {
        text: /DISPIMG/i.test(text) ? "—" : text,
        formula,
        style: cellStyle(styledCell?.style ?? {}, theme),
        rowSpan: 1,
        colSpan: 1,
        covered: false,
      };
    }),
  }));
  for (const merge of sheet["!merges"] ?? []) {
    if (merge.s.r >= rowCount || merge.s.c >= colCount) continue;
    const endRow = Math.min(merge.e.r, rowCount - 1);
    const endCol = Math.min(merge.e.c, colCount - 1);
    const master = rows[merge.s.r].cells[merge.s.c];
    master.rowSpan = endRow - merge.s.r + 1;
    master.colSpan = endCol - merge.s.c + 1;
    for (let r = merge.s.r; r <= endRow; r++) {
      for (let c = merge.s.c; c <= endCol; c++) {
        if (r !== merge.s.r || c !== merge.s.c) rows[r].cells[c].covered = true;
      }
    }
  }
  return {
    name,
    columns,
    rows,
    truncated: range.e.r >= EXCEL_MAX_ROWS || range.e.c >= EXCEL_MAX_COLS,
  };
}

export async function parseExcelPreview(
  buf: ArrayBuffer,
  filename: string,
): Promise<PreviewWorkbook> {
  const xlsx = await import("xlsx");
  // Keep Excel dates as serial values: formatting must not shift with browser timezone.
  const raw = xlsx.read(buf, {
    type: "array",
    cellStyles: true,
    sheetStubs: true,
    sheetRows: EXCEL_MAX_ROWS,
  });
  let styled: import("exceljs").Workbook | undefined;
  let theme: string[] = [];
  const media: PreviewWorkbook["media"] = [];
  if (!/\.xls$/i.test(filename)) {
    const [{ default: ExcelJS }, { default: JSZip }] = await Promise.all([
      import("exceljs"),
      import("jszip"),
    ]);
    styled = new ExcelJS.Workbook();
    await styled.xlsx.load(buf);
    const zip = await JSZip.loadAsync(buf);
    const themeXml = await zip.file("xl/theme/theme1.xml")?.async("string");
    if (themeXml) {
      const xml = new DOMParser().parseFromString(themeXml, "application/xml");
      const scheme = xml.getElementsByTagNameNS("*", "clrScheme")[0];
      const palette = Array.from(scheme?.children ?? []).map((entry) => {
        const color = entry.firstElementChild;
        return (
          color?.getAttribute("lastClr") ?? color?.getAttribute("val") ?? ""
        );
      });
      // Spreadsheet theme indices start light/dark; clrScheme XML starts dark/light.
      theme = [
        palette[1],
        palette[0],
        palette[3],
        palette[2],
        ...palette.slice(4),
      ];
    }
    for (const path of Object.keys(zip.files)
      .filter((path) => path.startsWith("xl/media/"))
      .sort()) {
      const ext = path.split(".").pop()?.toLowerCase() ?? "";
      const mime = (
        {
          png: "png",
          jpg: "jpeg",
          jpeg: "jpeg",
          gif: "gif",
          webp: "webp",
          bmp: "bmp",
        } as Record<string, string>
      )[ext];
      if (!mime) continue;
      media.push({
        name: path.split("/").pop() ?? path,
        dataUrl: `data:image/${mime};base64,${await zip.files[path].async(
          "base64",
        )}`,
      });
    }
  }
  const sheets = raw.SheetNames.map((name) => {
    const sheet = raw.Sheets[name];
    const model = buildSheet(
      name,
      sheet,
      xlsx,
      styled?.getWorksheet(name),
      theme,
    );
    // SheetJS retains the original range here when sheetRows clips the parsed data.
    const full = sheet["!fullref"];
    if (
      typeof full === "string" &&
      xlsx.utils.decode_range(full).e.r >= EXCEL_MAX_ROWS
    )
      model.truncated = true;
    return model;
  });
  return { sheets, media };
}
