import { createServer } from "node:net";

/**
 * Reserve a free loopback port from the OS, then release it for the child.
 *
 * Binding ``127.0.0.1:0`` asks the kernel for an ephemeral port; we close the
 * socket immediately so the Python child can bind it. There is a small TOCTOU
 * window (another process could steal the port), but the supervisor treats a
 * failed bind as a hard error and reports it rather than silently re-picking.
 */
export function reserveRandomPort(host = "127.0.0.1"): Promise<number> {
  return new Promise((resolvePromise, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, host, () => {
      const address = server.address();
      if (address === null || typeof address === "string") {
        server.close();
        reject(new Error("could not determine reserved port"));
        return;
      }
      const port = address.port;
      server.close((err) => {
        if (err) reject(err);
        else resolvePromise(port);
      });
    });
  });
}
