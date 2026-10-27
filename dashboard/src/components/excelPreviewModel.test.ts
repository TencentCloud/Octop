import { describe, expect, it } from "vitest";
import ExcelJS from "exceljs";
import * as XLSX from "xlsx";
import { parseExcelPreview } from "./excelPreviewModel";

describe("Excel artifact preview", () => {
  it("preserves coordinates, merged titles, styles, number formats and formula results", async () => {
    const book = new ExcelJS.Workbook();
    const sheet = book.addWorksheet("执行方案");
    sheet.mergeCells("B2:D2");
    sheet.getCell("B2").value = "客户分层方案";
    sheet.getCell("B2").font = {
      bold: true,
      size: 16,
      color: { argb: "FFFFFFFF" },
    };
    sheet.getCell("B2").fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: "FF4472C4" },
    };
    sheet.getCell("B2").alignment = {
      horizontal: "center",
      vertical: "middle",
      wrapText: true,
    };
    sheet.getCell("B2").border = {
      bottom: { style: "thin", color: { argb: "FF000000" } },
    };
    sheet.getColumn(2).width = 30;
    sheet.getRow(2).height = 36;
    sheet.getCell("B3").value = 0.125;
    sheet.getCell("B3").numFmt = "0.0%";
    sheet.getCell("C3").value = { formula: "1+2", result: 3 };
    sheet.getCell("D3").value = { formula: "SUM(B3:C3)" };
    sheet.getCell("B4").value = new Date("2026-10-27T00:00:00Z");
    sheet.getCell("B4").numFmt = "yyyy-mm-dd";
    sheet.getCell("C4").value = '<img src=x onerror="alert(1)">';
    book.addWorksheet("空表");
    const parsed = await parseExcelPreview(
      (await book.xlsx.writeBuffer()) as ArrayBuffer,
      "plan.xlsx",
    );
    expect(parsed.sheets.map((sheet) => sheet.name)).toEqual([
      "执行方案",
      "空表",
    ]);
    const result = parsed.sheets[0];
    expect(result.rows[0].cells[0].text).toBe("");
    const title = result.rows[1].cells[1];
    expect(title).toMatchObject({
      text: "客户分层方案",
      colSpan: 3,
      rowSpan: 1,
      style: {
        backgroundColor: "#4472c4",
        color: "#ffffff",
        fontWeight: "bold",
        textAlign: "center",
        whiteSpace: "pre-wrap",
        borderBottom: "1px solid #000000",
      },
    });
    expect(result.rows[1].cells[2].covered).toBe(true);
    expect(result.columns[1].width).toBe(215);
    expect(result.rows[1].height).toBe(48);
    expect(result.rows[2].cells.map((cell) => cell.text)).toEqual([
      "",
      "12.5%",
      "3",
      "=SUM(B3:C3)",
    ]);
    expect(result.rows[2].cells[3].formula).toBe("SUM(B3:C3)");
    expect(result.rows[3].cells[1].text).toBe("2026-10-27");
    expect(result.rows[3].cells[2].text).toContain("<img");
  });

  it("resolves workbook theme colors, clips merges and preserves the image gallery", async () => {
    const book = new ExcelJS.Workbook();
    const sheet = book.addWorksheet("大表");
    sheet.getCell("A1").value = "主题色";
    sheet.getCell("A1").font = { color: { theme: 4 } };
    sheet.getCell("B1").value = "默认字体";
    sheet.getCell("B1").font = { color: { theme: 1 } };
    sheet.mergeCells("AM499:AP502");
    sheet.getCell("AM499").value = "跨边界";
    const image = book.addImage({
      base64:
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==",
      extension: "png",
    });
    sheet.addImage(image, "A2:B3");
    const parsed = await parseExcelPreview(
      (await book.xlsx.writeBuffer()) as ArrayBuffer,
      "plan.xlsx",
    );
    const result = parsed.sheets[0];
    expect(result.rows).toHaveLength(500);
    expect(result.columns).toHaveLength(40);
    expect(result.truncated).toBe(true);
    expect(result.rows[498].cells[38]).toMatchObject({
      text: "跨边界",
      rowSpan: 2,
      colSpan: 2,
    });
    expect(result.rows[499].cells[39].covered).toBe(true);
    expect(result.rows[0].cells[0].style.color).toMatch(/^#[a-f\d]{6}$/);
    expect(result.rows[0].cells[0].style.color).not.toBe("#000000");
    expect(result.rows[0].cells[1].style.color).toBe("#000000");
    expect(parsed.media[0].dataUrl).toMatch(/^data:image\/png;base64,/);
  });

  it("continues reading legacy XLS files and rejects corrupt workbooks", async () => {
    const book = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(
      book,
      XLSX.utils.aoa_to_sheet([
        ["客户", "金额"],
        ["S级", 2000],
      ]),
      "名单",
    );
    const result = await parseExcelPreview(
      XLSX.write(book, { type: "array", bookType: "xls" }),
      "legacy.xls",
    );
    expect(result.sheets[0].rows[1].cells.map((cell) => cell.text)).toEqual([
      "S级",
      "2000",
    ]);
    await expect(
      parseExcelPreview(new ArrayBuffer(0), "bad.xlsx"),
    ).rejects.toThrow();
  });
});
