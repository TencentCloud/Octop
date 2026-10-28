import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";

/** SHA-256 of a file, streamed so large portable zips never hit memory. */
export function sha256File(filePath: string): Promise<string> {
  return new Promise((resolvePromise, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(filePath);
    stream.on("error", reject);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("end", () => resolvePromise(hash.digest("hex")));
  });
}

/** Constant-time compare of two hex digests (avoid timing side channels). */
export function digestsEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a.toLowerCase(), "hex");
  const bufB = Buffer.from(b.toLowerCase(), "hex");
  if (bufA.length !== bufB.length) return false;
  return createHash("sha256").update(bufA).digest().equals(createHash("sha256").update(bufB).digest());
}
