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
