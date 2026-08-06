import { useCallback, useEffect, useRef, useState } from "react";
import { Check, ChevronRight } from "lucide-react";

const THUMB_SIZE = 40;
const COMPLETE_RATIO = 0.92;

export type SlideCaptchaProps = {
  hint: string;
  verifiedLabel: string;
  onVerified: () => void;
  /** Bump to force the control back to the unverified state. */
  resetKey?: number;
};

function trackMaxOffset(track: HTMLElement | null): number {
  if (!track) return 0;
  return Math.max(0, track.getBoundingClientRect().width - THUMB_SIZE);
}

function clientXFromEvent(e: MouseEvent | TouchEvent): number {
  if ("touches" in e) {
    const t = e.changedTouches[0] ?? e.touches[0];
    return t?.clientX ?? 0;
  }
  return e.clientX;
}

export default function SlideCaptcha({
  hint,
  verifiedLabel,
  onVerified,
  resetKey = 0,
}: SlideCaptchaProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const verifiedRef = useRef(false);
  const startXRef = useRef(0);
  const startOffsetRef = useRef(0);
  const dragCleanupRef = useRef<(() => void) | null>(null);
  const [offset, setOffset] = useState(0);
  const [maxOffset, setMaxOffset] = useState(0);
  const [verified, setVerified] = useState(false);
  const [dragging, setDragging] = useState(false);

  verifiedRef.current = verified;

  useEffect(() => {
    return () => {
      dragCleanupRef.current?.();
      dragCleanupRef.current = null;
    };
  }, []);

  const measure = useCallback(() => {
    setMaxOffset(trackMaxOffset(trackRef.current));
  }, []);

  useEffect(() => {
    measure();
    const track = trackRef.current;
    if (!track || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(track);
    return () => ro.disconnect();
  }, [measure]);

  useEffect(() => {
    setOffset(0);
    setVerified(false);
    setDragging(false);
  }, [resetKey]);

  const complete = useCallback(
    (max: number) => {
      setOffset(max);
      setVerified(true);
      onVerified();
    },
    [onVerified],
  );

  const clampOffset = (raw: number, max: number) =>
    Math.min(max, Math.max(0, raw));

  const beginDrag = (clientX: number) => {
    if (verifiedRef.current) return;
    dragCleanupRef.current?.();
    const max = trackMaxOffset(trackRef.current);
    setMaxOffset(max);
    startXRef.current = clientX;
    startOffsetRef.current = offset;
    setDragging(true);

    const onMove = (ev: MouseEvent | TouchEvent) => {
      if (verifiedRef.current) return;
      if ("cancelable" in ev && ev.cancelable) ev.preventDefault();
      const moveMax = trackMaxOffset(trackRef.current);
      setOffset(
        clampOffset(
          startOffsetRef.current + (clientXFromEvent(ev) - startXRef.current),
          moveMax,
        ),
      );
    };

    const onUp = (ev: MouseEvent | TouchEvent) => {
      cleanup();
      if (verifiedRef.current) return;
      const upMax = trackMaxOffset(trackRef.current);
      const next = clampOffset(
        startOffsetRef.current + (clientXFromEvent(ev) - startXRef.current),
        upMax,
      );
      if (upMax > 0 && next / upMax >= COMPLETE_RATIO) {
        complete(upMax);
      } else {
        setOffset(0);
      }
    };

    const cleanup = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onUp);
      window.removeEventListener("touchcancel", onUp);
      dragCleanupRef.current = null;
      setDragging(false);
    };

    dragCleanupRef.current = cleanup;
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("touchmove", onMove, { passive: false });
    window.addEventListener("touchend", onUp);
    window.addEventListener("touchcancel", onUp);
  };

  return (
    <div
      ref={trackRef}
      data-testid="slide-captcha-track"
      role="slider"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={
        verified ? 100 : maxOffset ? Math.round((offset / maxOffset) * 100) : 0
      }
      aria-valuetext={verified ? verifiedLabel : hint}
      aria-label={hint}
      style={{
        position: "relative",
        width: "100%",
        height: THUMB_SIZE,
        borderRadius: 10,
        background: verified
          ? "var(--fn-success-bg, #e8f8ef)"
          : "var(--fn-bg-layout)",
        border: `1px solid ${
          verified
            ? "var(--fn-success-border, #86d3a9)"
            : "var(--fn-border-primary)"
        }`,
        overflow: "hidden",
        userSelect: "none",
        touchAction: "none",
      }}
    >
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          paddingLeft: verified ? 8 : THUMB_SIZE,
          paddingRight: verified ? THUMB_SIZE : 8,
          fontSize: 13,
          color: verified
            ? "var(--fn-success, #16a34a)"
            : "var(--fn-text-tertiary)",
          pointerEvents: "none",
          whiteSpace: "nowrap",
        }}
      >
        {verified ? verifiedLabel : hint}
      </div>

      {!verified && (
        <div
          aria-hidden
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: offset + THUMB_SIZE / 2,
            background: "var(--fn-primary-bg, rgba(22, 119, 255, 0.12))",
            pointerEvents: "none",
          }}
        />
      )}

      <div
        data-testid="slide-captcha-thumb"
        onMouseDown={(e) => {
          e.preventDefault();
          beginDrag(e.clientX);
        }}
        onTouchStart={(e) => {
          const t = e.touches[0];
          if (!t) return;
          beginDrag(t.clientX);
        }}
        style={{
          position: "absolute",
          left: verified
            ? maxOffset || trackMaxOffset(trackRef.current)
            : offset,
          top: 0,
          width: THUMB_SIZE,
          height: THUMB_SIZE,
          borderRadius: 10,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: verified
            ? "var(--fn-success, #16a34a)"
            : "var(--fn-bg-elevated)",
          border: `1px solid ${
            verified ? "transparent" : "var(--fn-border-primary)"
          }`,
          boxShadow: "0 1px 4px rgba(0,0,0,0.12)",
          cursor: verified ? "default" : dragging ? "grabbing" : "grab",
          color: verified ? "#fff" : "var(--fn-text-secondary)",
        }}
      >
        {verified ? (
          <Check size={18} strokeWidth={2.5} />
        ) : (
          <ChevronRight size={18} />
        )}
      </div>
    </div>
  );
}
