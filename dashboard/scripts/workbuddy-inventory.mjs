// Keep review evidence when regenerating derived static inventories.
export function preserveOperationAcceptance(operations, previous) {
  const key = (item) => `${item.module}:${item.symbol}:${item.operation}`;
  const byKey = new Map(previous.map((item) => [key(item), item]));
  return operations.map((item) => {
    const old = byKey.get(key(item));
    if (!old) return item;
    if (old.apiSha256 !== item.apiSha256) {
      if (old.verification && old.verification !== "pending")
        return {
          ...item,
          previousAcceptance: old.previousAcceptance ?? {
            verification: old.verification,
            acceptance: old.acceptance,
          },
          verification: "pending-contract-review",
        };
      return item;
    }
    return {
      ...item,
      verification: old.verification ?? item.verification,
      ...(old.acceptance ? { acceptance: old.acceptance } : {}),
      ...(old.previousAcceptance
        ? { previousAcceptance: old.previousAcceptance }
        : {}),
    };
  });
}

export function preserveComponentAcceptance(components, previous) {
  const byKey = new Map(previous.map((item) => [item.original, item]));
  return components.map((item) => {
    const old = byKey.get(item.original);
    if (!old || old.sourceFingerprint !== item.sourceFingerprint) return item;
    return {
      ...item,
      visualVerification: old.visualVerification ?? item.visualVerification,
      ...(old.acceptance ? { acceptance: old.acceptance } : {}),
    };
  });
}
