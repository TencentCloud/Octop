import ExcelJS from "exceljs";
import { expect, it } from "vitest";
import { convertXlsx } from "./excelPreview/xlsx";

it("retains workbook fills, merges and stored formula values in the grid model", async () => {
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("Summary");
  sheet.mergeCells("A1:B2");
  sheet.getCell("A1").value = "Quarterly report";
  sheet.getCell("A1").fill = {
    type: "pattern",
    pattern: "solid",
    fgColor: { argb: "FFFFCC00" },
  };
  sheet.getCell("C4").value = { formula: "1+2", result: 3 };
  const data = await workbook.xlsx.writeBuffer();
  const preview = await convertXlsx(new Uint8Array(data), {
    maxBytes: 16 * 1024 * 1024,
    maxCells: 250_000,
    timeoutMs: 15_000,
  });
  expect(preview.sheets[0].config?.merge?.["0_0"]).toMatchObject({
    rs: 2,
    cs: 2,
  });
  expect(preview.sheets[0].celldata).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        r: 0,
        c: 0,
        v: expect.objectContaining({ bg: "#FFCC00" }),
      }),
      expect.objectContaining({
        r: 3,
        c: 2,
        v: expect.objectContaining({ v: 3, f: "=1+2" }),
      }),
    ]),
  );
});
