/**
 * Compile-time pin on the two `verify` shapes, which are **deliberately different**:
 *
 * - draft (write path): one command — `pipeline.py · _DRAFT_STR_KEYS` projects it with
 *   `str(...).strip()`, so an array would be stored verbatim as the string `"[]"` and the
 *   row's `verify[]` would end up as `["[]"]` (`run_service._verify_list`).
 * - row (read path): `string[]` — a JSON array column.
 *
 * Nothing runs: the assertions live in the type layer, so a regression that widens the
 * draft back to `string[]` fails `tsc` / this file rather than silently producing dirty
 * `verify` rows. The runtime `expect` only gives this file a body for the runner.
 */

import { expect, it } from "vitest";

import type {
  PlanTaskDraft,
  TaskNodeWire,
} from "../../../api/modules/teamRuns";

/** Idempotent structural identity — the strict form of `A extends B && B extends A`. */
type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B
  ? 1
  : 2
  ? true
  : false;

/** Fails to compile (TS2344) unless `A` and `B` are exactly the same type. */
type Assert<T extends true> = T;

/** Exported so `noUnusedLocals` stays satisfied while the check still binds. */
export type PlanTaskDraftVerifyIsScalar = Assert<
  Equal<PlanTaskDraft["verify"], string>
>;

/** The row-side shape is the counter-direction and must stay an array. */
export type TaskNodeWireVerifyIsArray = Assert<
  Equal<TaskNodeWire["verify"], string[]>
>;

it("pins the draft `verify` shape to the backend's scalar contract", () => {
  const blank: PlanTaskDraft = {
    id: "",
    owner: "",
    title: "",
    kind: "",
    spec: "",
    acceptance: [],
    inScope: [],
    verify: "",
    dependsOn: [],
    status: "todo",
    attempt: 0,
    round: 1,
    verdict: null,
  };

  // The draft value the editor submits must be a string, never a list — sending `[]` is
  // exactly the defect this file guards.
  expect(typeof blank.verify).toBe("string");
  expect(Array.isArray(blank.verify)).toBe(false);
});
