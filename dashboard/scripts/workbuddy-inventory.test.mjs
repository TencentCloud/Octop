import { test } from "node:test";
import assert from "node:assert/strict";
import {
  preserveOperationAcceptance,
  preserveComponentAcceptance,
} from "./workbuddy-inventory.mjs";

const operation = {
  module: "cron.ts",
  symbol: "cronApi",
  operation: "create",
  apiSha256: "same",
  line: 20,
  consumers: [],
  verification: "pending",
};
test("regeneration retains accepted evidence while refreshing derived call sites", () => {
  const previous = {
    ...operation,
    line: 10,
    verification: "passed",
    acceptance: {
      cases: ["cron-create-refresh"],
      evidence: "evidence/real-browser.json",
    },
  };
  assert.deepEqual(preserveOperationAcceptance([operation], [previous])[0], {
    ...operation,
    verification: "passed",
    acceptance: previous.acceptance,
  });
});
test("a changed API invalidates acceptance without discarding previous evidence", () => {
  const previous = {
    ...operation,
    apiSha256: "old",
    verification: "passed",
    acceptance: { cases: ["cron-create-refresh"] },
  };
  const next = preserveOperationAcceptance([operation], [previous])[0];
  assert.equal(next.verification, "pending-contract-review");
  assert.deepEqual(next.previousAcceptance.acceptance, previous.acceptance);
  assert.equal(next.acceptance, undefined);
  assert.deepEqual(
    preserveOperationAcceptance([operation], [next])[0].previousAcceptance,
    next.previousAcceptance,
  );
});
test("source rendering acceptance follows only the frozen matching baseline", () => {
  const component = {
    original: "home.tsx",
    sourceFingerprint: "556",
    visualVerification: "pending-original-render",
  };
  const previous = {
    ...component,
    visualVerification: "passed",
    acceptance: { viewport: "1440x900" },
  };
  assert.equal(
    preserveComponentAcceptance([component], [previous])[0].visualVerification,
    "passed",
  );
  assert.equal(
    preserveComponentAcceptance(
      [{ ...component, sourceFingerprint: "different" }],
      [previous],
    )[0].visualVerification,
    "pending-original-render",
  );
});
