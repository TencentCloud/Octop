import { convertXls } from "./xls";
import { convertXlsx } from "./xlsx";
import type { ExcelFormat } from "./format";
import type { ExcelLimits } from "./model";

export function convertExcel(
  bytes: Uint8Array<ArrayBuffer>,
  format: ExcelFormat,
  limits: ExcelLimits,
) {
  if (format === "xls") {
    return Promise.resolve().then(() => convertXls(bytes, limits));
  }
  return convertXlsx(bytes, limits);
}
