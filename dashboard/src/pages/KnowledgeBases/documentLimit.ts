export function effectiveDocumentLimit(
  maxDocuments: number | undefined,
  fallback: number,
): number {
  const limit = maxDocuments ?? fallback;
  return limit === 0 ? Number.POSITIVE_INFINITY : limit;
}
