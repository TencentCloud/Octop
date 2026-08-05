import { describe, expect, it } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { UNAUTHORIZED_EVENT } from "../api/request";
import { useUnauthorizedRedirect } from "./useUnauthorizedRedirect";

function Harness() {
  useUnauthorizedRedirect();
  return (
    <Routes>
      <Route path="/chat" element={<div>chat screen</div>} />
      <Route path="/login" element={<div>login screen</div>} />
    </Routes>
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
});
