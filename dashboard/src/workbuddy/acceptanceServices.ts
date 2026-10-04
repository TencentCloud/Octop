/** Imported only by the independent development fixture entry. */
if (!import.meta.env.DEV)
  throw new Error("Acceptance services are development-only");

// The production composer reads limits and command metadata through Octop APIs.
// Keep those inputs deterministic and reject every other request, including writes.
window.fetch = async (input, init) => {
  const request = input instanceof Request ? input : null;
  const url = new URL(request?.url ?? String(input), window.location.href);
  const method = init?.method ?? request?.method ?? "GET";
  if (method === "GET" && url.pathname === "/api/settings/upload") {
    return Response.json({ max_upload_mb: 100, max_upload_bytes: 104857600 });
  }
  if (method === "GET" && url.pathname === "/api/slash/commands") {
    return Response.json({ origin: "ui", commands: [] });
  }
  throw new Error("Development fixture: business requests are disabled");
};
