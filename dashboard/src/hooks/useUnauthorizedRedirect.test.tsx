import { describe, expect, it } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { UNAUTHORIZED_EVENT } from "../api/request";
import { useUnauthorizedRedirect } from "./useUnauthorizedRedirect";

function Harness() {
  useUnauthorizedRedirect();
  const location = useLocation();
  return (
    <>
      <div data-testid="location">
        {location.pathname}
        {location.search}
      </div>
      <Routes>
        <Route path="/chat" element={<div>chat screen</div>} />
        <Route
          path="/embed/chat/:agentId/:threadId"
          element={<div>embedded screen</div>}
        />
        <Route path="/login" element={<div>login screen</div>} />
      </Routes>
    </>
  );
}

function dispatchUnauthorized(): Event {
  const event = new CustomEvent(UNAUTHORIZED_EVENT, { cancelable: true });
  act(() => {
    window.dispatchEvent(event);
  });
  return event;
}

describe("useUnauthorizedRedirect", () => {
  it("routes to /login inside the SPA and cancels the hard navigation", () => {
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <Harness />
      </MemoryRouter>,
    );
    expect(screen.getByText("chat screen")).toBeInTheDocument();

    const event = dispatchUnauthorized();

    expect(event.defaultPrevented).toBe(true);
    expect(screen.getByText("login screen")).toBeInTheDocument();
  });

  it("stops handling the event after unmount", () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={["/chat"]}>
        <Harness />
      </MemoryRouter>,
    );
    unmount();

    expect(dispatchUnauthorized().defaultPrevented).toBe(false);
  });

  it("preserves the embedded thread when the session expires", () => {
    render(
      <MemoryRouter
        initialEntries={["/embed/chat/agent-a/thr_1?mode=small#message"]}
      >
        <Harness />
      </MemoryRouter>,
    );
    dispatchUnauthorized();
    const location = screen.getByTestId("location").textContent!;
    expect(
      new URL(location, "http://localhost").searchParams.get("redirect"),
    ).toBe("/embed/chat/agent-a/thr_1?mode=small#message");
  });
});
