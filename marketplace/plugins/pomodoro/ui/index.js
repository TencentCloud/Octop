const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;
const { useEffect, useState } = React;

function formatSec(total) {
  const s = Math.max(0, Math.floor(total));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

function pomodoroRemaining(d, now) {
  if (d.paused) return Number(d.remaining_sec) || 0;
  const started = Date.parse(d.started_at || "") || now;
  const elapsed = Math.floor((now - started) / 1000);
  return Math.max(0, Number(d.duration_sec || 0) - elapsed);
}

function countdownRemaining(target, now) {
  const t = Date.parse(target) || 0;
  return Math.max(0, Math.floor((t - now) / 1000));
}

function Ring({ remaining, duration, done }) {
  const r = 54;
  const c = 2 * Math.PI * r;
  const pct = duration > 0 ? Math.min(1, remaining / duration) : 0;
  return _jsxs("svg", {
    width: 148,
    height: 148,
    viewBox: "0 0 148 148",
    children: [
      _jsx("circle", { cx: 74, cy: 74, r, fill: "none", stroke: "rgba(255,255,255,.22)", strokeWidth: 10 }),
      _jsx("circle", {
        cx: 74,
        cy: 74,
        r,
        fill: "none",
        stroke: done ? "#86efac" : "#fff",
        strokeWidth: 10,
        strokeLinecap: "round",
        strokeDasharray: `${c * pct} ${c}`,
        transform: "rotate(-90 74 74)",
      }),
    ],
  });
}

function pill(label, onClick, { ghost } = {}) {
  return _jsx("button", {
    type: "button",
    onClick,
    style: {
      border: ghost ? "1px solid rgba(255,255,255,.45)" : "none",
      background: ghost ? "transparent" : "#fff",
      color: ghost ? "#fff" : "#9a3412",
      borderRadius: 999,
      padding: "8px 18px",
      fontSize: 13,
      fontWeight: 700,
      cursor: "pointer",
      boxShadow: ghost ? "none" : "0 6px 16px rgba(0,0,0,.12)",
    },
    children: label,
  });
}

function TimerCard(props) {
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (d.paused) return undefined;
    const id = setInterval(() => setNow(Date.now()), 400);
    return () => clearInterval(id);
  }, [d.paused, d.started_at, d.target_iso]);

  const remaining =
    d.kind === "countdown" ? countdownRemaining(d.target_iso, now) : pomodoroRemaining(d, now);
  const duration =
    d.kind === "countdown"
      ? Math.max(remaining, 1)
      : Number(d.duration_sec || 1);
  const done = remaining <= 0;

  const patch = (next) => {
    if (!props.callId) return;
    props.host.patchResult(props.callId, { ...d, ...next });
  };

  const isPomo = d.kind !== "countdown";
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 320,
      borderRadius: 24,
      padding: "22px 20px 18px",
      textAlign: "center",
      color: "#fff",
      background: done
        ? "linear-gradient(165deg,#16a34a,#22c55e)"
        : isPomo
          ? "linear-gradient(165deg,#c2410c,#ea580c 40%,#fb923c)"
          : "linear-gradient(165deg,#1d4ed8,#2563eb 45%,#7c3aed)",
      boxShadow: "0 16px 36px rgba(234,88,12,.28)",
    },
    "data-octop-plugin-ui": "pomodoro",
    children: [
      _jsx("div", { style: { fontSize: 28, lineHeight: 1 }, children: isPomo ? "🍅" : "⏳" }),
      _jsx("div", {
        style: { marginTop: 6, fontWeight: 700, letterSpacing: 0.3, opacity: 0.92 },
        children: d.label || d.title || (isPomo ? "专注时钟" : "倒数"),
      }),
      _jsxs("div", {
        style: { position: "relative", width: 148, height: 148, margin: "14px auto 8px" },
        children: [
          _jsx(Ring, { remaining: isPomo ? remaining : remaining, duration: isPomo ? duration : Math.max(duration, remaining || 1), done }),
          _jsx("div", {
            style: {
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 28,
              fontWeight: 800,
              fontVariantNumeric: "tabular-nums",
            },
            children: formatSec(remaining),
          }),
        ],
      }),
      isPomo
        ? _jsxs("div", {
            style: { display: "flex", gap: 10, justifyContent: "center", marginTop: 8 },
            children: [
              pill(d.paused ? "继续" : "暂停", () =>
                patch(
                  d.paused
                    ? {
                        paused: false,
                        started_at: new Date(
                          Date.now() - (Number(d.duration_sec) - remaining) * 1000,
                        ).toISOString(),
                      }
                    : { paused: true, remaining_sec: remaining },
                ),
              ),
              pill(
                "重置",
                () =>
                  patch({
                    paused: false,
                    remaining_sec: d.duration_sec,
                    started_at: new Date().toISOString(),
                  }),
                { ghost: true },
              ),
            ],
          })
        : _jsx("div", {
            style: { fontSize: 12, opacity: 0.85, marginTop: 4 },
            children: d.target_iso || "",
          }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "timer_card",
    tools: ["start_pomodoro", "start_countdown"],
    component: TimerCard,
  });
}
