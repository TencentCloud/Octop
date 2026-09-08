import { describe, expect, it } from "vitest";

import {
  consumePendingAttachKnowledgeBaseId,
  peekPendingAttachKnowledgeBaseId,
  setPendingAttachKnowledgeBaseId,
} from "./pendingAttachKnowledgeBase";

describe("pendingAttachKnowledgeBase", () => {
  it("stores and consumes a knowledge-base id once", () => {
    setPendingAttachKnowledgeBaseId(" kb-1 ");
    expect(peekPendingAttachKnowledgeBaseId()).toBe("kb-1");
    expect(consumePendingAttachKnowledgeBaseId()).toBe("kb-1");
    expect(consumePendingAttachKnowledgeBaseId()).toBe("");
  });
});
