// Adapted from DeepSeek Harness (MIT). See public/third-party-deepseek-excel.txt.
/** Locale-independent spreadsheet parser failure categories. */
export class ExcelPreviewError extends Error {
  readonly code: "invalid" | "tooLarge" | "timeout" | "encoding";

  /** @param code - User-actionable parser failure. */
  constructor(
    code: "invalid" | "tooLarge" | "timeout" | "encoding",
    options?: ErrorOptions,
  ) {
    super(code, options);
    this.code = code;
    this.name = "ExcelPreviewError";
  }
}
