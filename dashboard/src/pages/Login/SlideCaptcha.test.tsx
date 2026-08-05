import { describe, expect, it, vi } from "vitest";
import { act, render, screen, fireEvent } from "@testing-library/react";
import SlideCaptcha from "./SlideCaptcha";

function mockTrackRect(el: HTMLElement, width = 300) {
  Object.defineProperty(el, "getBoundingClientRect", {
    configurable: true,
    value: () => ({
      left: 0,
      top: 0,
      right: width,
      bottom: 40,
      width,
      height: 40,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }),
  });
}

async function dragThumb(clientFrom: number, clientTo: number) {
  const track = screen.getByTestId("slide-captcha-track");
  const thumb = screen.getByTestId("slide-captcha-thumb");
  mockTrackRect(track, 300);

  fireEvent.mouseDown(thumb, { clientX: clientFrom });
  await act(async () => {
    fireEvent.mouseMove(window, { clientX: clientTo });
    fireEvent.mouseUp(window, { clientX: clientTo });
  });
}

describe("SlideCaptcha", () => {
  it("does not verify until the thumb reaches the end", async () => {
    const onVerified = vi.fn();
    render(
      <SlideCaptcha hint="Slide" verifiedLabel="OK" onVerified={onVerified} />,
    );

    await dragThumb(20, 100);

    expect(onVerified).not.toHaveBeenCalled();
    expect(screen.queryByText("OK")).not.toBeInTheDocument();
  });

  it("calls onVerified when the thumb is dragged to the end", async () => {
    const onVerified = vi.fn();
    render(
      <SlideCaptcha hint="Slide" verifiedLabel="OK" onVerified={onVerified} />,
    );

    await dragThumb(20, 290);

    expect(onVerified).toHaveBeenCalledTimes(1);
    expect(screen.getByText("OK")).toBeInTheDocument();
  });

  it("resets when resetKey changes", async () => {
    const onVerified = vi.fn();
    const { rerender } = render(
      <SlideCaptcha
        hint="Slide"
        verifiedLabel="OK"
        onVerified={onVerified}
        resetKey={0}
      />,
    );

    await dragThumb(20, 290);
    expect(screen.getByText("OK")).toBeInTheDocument();

    rerender(
      <SlideCaptcha
        hint="Slide"
        verifiedLabel="OK"
        onVerified={onVerified}
        resetKey={1}
      />,
    );

    expect(screen.queryByText("OK")).not.toBeInTheDocument();
    expect(screen.getByText("Slide")).toBeInTheDocument();
  });
});
