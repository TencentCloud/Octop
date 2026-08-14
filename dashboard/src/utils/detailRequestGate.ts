/** Invalidate in-flight detail fetches after delete / re-select. */
export function createDetailRequestGate() {
  let latestRequest = 0;

  return {
    begin: () => {
      latestRequest += 1;
      return latestRequest;
    },
    isCurrent: (requestId: number) => requestId === latestRequest,
  };
}
