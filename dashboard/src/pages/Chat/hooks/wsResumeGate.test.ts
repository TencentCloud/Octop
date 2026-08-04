import { describe, expect, it } from "vitest";
import {
  MAX_STREAM_RESUME_ATTEMPTS,
  STREAM_STALE_WITHOUT_SOCKET_MS,
  historySuggestsActiveTurn,
  shouldBlockHistoryRefresh,
  shouldEmitStreamResumeNotice,
  shouldForceSealStream,
  shouldProbeActiveTurn,
  shouldResumeStreamAfterClose,
} from "./wsResumeGate";

describe("shouldResumeStreamAfterClose", () => {
  it("resumes on unexpected close while streaming", () => {
    expect(
      shouldResumeStreamAfterClose({
        intentionalClose: false,
        isStreaming: true,
        threadId: "tid-1",
      }),
    ).toBe(true);
  });

  it("does not resume on intentional close (done / cancel)", () => {
    expect(
      shouldResumeStreamAfterClose({
        intentionalClose: true,
        isStreaming: true,
        threadId: "tid-1",
      }),
    ).toBe(false);
  });

  it("does not resume when not streaming", () => {
    expect(
      shouldResumeStreamAfterClose({
        intentionalClose: false,
        isStreaming: false,
        threadId: "tid-1",
      }),
    ).toBe(false);
  });

  it("does not resume without a real thread id", () => {
    expect(
      shouldResumeStreamAfterClose({
        intentionalClose: false,
        isStreaming: true,
        threadId: "__empty__",
      }),
    ).toBe(false);
  });

  it("stops resuming after max attempts", () => {
    expect(
      shouldResumeStreamAfterClose({
        intentionalClose: false,
        isStreaming: true,
        threadId: "tid-1",
        attempt: MAX_STREAM_RESUME_ATTEMPTS,
      }),
    ).toBe(false);
    expect(
      shouldResumeStreamAfterClose({
        intentionalClose: false,
        isStreaming: true,
        threadId: "tid-1",
        attempt: MAX_STREAM_RESUME_ATTEMPTS - 1,
      }),
    ).toBe(true);
  });

  it("skips reconnect for unfocused sessions", () => {
    expect(
      shouldResumeStreamAfterClose({
        intentionalClose: false,
        isStreaming: true,
        threadId: "tid-1",
        sessionFocused: false,
      }),
    ).toBe(false);
    expect(
      shouldResumeStreamAfterClose({
        intentionalClose: false,
        isStreaming: true,
        threadId: "tid-1",
        sessionFocused: true,
      }),
    ).toBe(true);
  });
});

describe("historySuggestsActiveTurn", () => {
  it("flags trailing user message (reply may still be in flight)", () => {
    expect(historySuggestsActiveTurn([{ role: "user", status: "done" }])).toBe(
      true,
    );
  });

  it("flags streaming assistant bubbles", () => {
    expect(
      historySuggestsActiveTurn([
        { role: "user", status: "done" },
        { role: "assistant", status: "streaming" },
      ]),
    ).toBe(true);
  });

  it("skips finished assistant turns", () => {
    expect(
      historySuggestsActiveTurn([
        { role: "user", status: "done" },
        { role: "assistant", status: "done" },
      ]),
    ).toBe(false);
  });

  it("skips empty history", () => {
    expect(historySuggestsActiveTurn([])).toBe(false);
  });
});

describe("shouldProbeActiveTurn", () => {
  it("probes while already streaming", () => {
    expect(
      shouldProbeActiveTurn({ isStreaming: true, justHydrated: false }),
    ).toBe(true);
  });

  it("probes hydrate only when history suggests mid-turn", () => {
    expect(
      shouldProbeActiveTurn({
        isStreaming: false,
        justHydrated: true,
        historySuggestsActive: true,
      }),
    ).toBe(true);
    expect(
      shouldProbeActiveTurn({
        isStreaming: false,
        justHydrated: true,
        historySuggestsActive: false,
      }),
    ).toBe(false);
  });

  it("skips idle hydrated sessions", () => {
    expect(
      shouldProbeActiveTurn({
        isStreaming: false,
        justHydrated: false,
        historySuggestsActive: true,
      }),
    ).toBe(false);
  });
});

describe("shouldBlockHistoryRefresh", () => {
  it("blocks only when streaming with a live socket", () => {
    expect(
      shouldBlockHistoryRefresh({ isStreaming: true, hasLiveSocket: true }),
    ).toBe(true);
  });

  it("allows sticky isStreaming without a socket (recovery path)", () => {
    expect(
      shouldBlockHistoryRefresh({ isStreaming: true, hasLiveSocket: false }),
    ).toBe(false);
    expect(
      shouldBlockHistoryRefresh({ isStreaming: false, hasLiveSocket: false }),
    ).toBe(false);
  });
});

describe("shouldForceSealStream", () => {
  const now = 1_000_000;

  it("does not seal while a live socket is open (long tools)", () => {
    expect(
      shouldForceSealStream({
        isStreaming: true,
        hasLiveSocket: true,
        lastActivityAt: now - 120_000,
        now,
      }),
    ).toBe(false);
  });

  it("seals sticky stream with no socket past grace", () => {
    expect(
      shouldForceSealStream({
        isStreaming: true,
        hasLiveSocket: false,
        lastActivityAt: now - STREAM_STALE_WITHOUT_SOCKET_MS - 1,
        now,
      }),
    ).toBe(true);
  });

  it("waits during reconnect grace window", () => {
    expect(
      shouldForceSealStream({
        isStreaming: true,
        hasLiveSocket: false,
        lastActivityAt: now - 1_000,
        now,
      }),
    ).toBe(false);
  });

  it("seals streaming with no activity marker and no socket", () => {
    expect(
      shouldForceSealStream({
        isStreaming: true,
        hasLiveSocket: false,
        lastActivityAt: null,
        now,
      }),
    ).toBe(true);
  });

  it("does not seal unfocused background sessions", () => {
    expect(
      shouldForceSealStream({
        isStreaming: true,
        hasLiveSocket: false,
        lastActivityAt: null,
        now,
        sessionFocused: false,
      }),
    ).toBe(false);
  });
});

describe("shouldEmitStreamResumeNotice", () => {
  it("emits only after a reattach attempt with an active turn", () => {
    expect(
      shouldEmitStreamResumeNotice({ resumeAttempt: 1, turnActive: true }),
    ).toBe(true);
    expect(
      shouldEmitStreamResumeNotice({ resumeAttempt: 0, turnActive: true }),
    ).toBe(false);
    expect(
      shouldEmitStreamResumeNotice({ resumeAttempt: 2, turnActive: false }),
    ).toBe(false);
  });
});
