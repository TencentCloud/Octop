const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function iconFor(code, fallback) {
  if (fallback) return fallback;
  const n = Number(code);
  if (n === 0) return "☀️";
  if (n === 1) return "🌤️";
  if (n === 2) return "⛅";
  if (n === 3) return "☁️";
  if (n === 45 || n === 48) return "🌫️";
  if (n >= 51 && n <= 67) return "🌧️";
  if (n >= 71 && n <= 77) return "❄️";
  if (n >= 80 && n <= 82) return "🌦️";
  if (n >= 95) return "⛈️";
  return "🌡️";
}

function sky(code, dark) {
  const n = Number(code);
  if (n === 0) return dark ? "linear-gradient(160deg,#1e3a5f,#0ea5e9)" : "linear-gradient(160deg,#7dd3fc,#38bdf8 45%,#fde68a)";
  if (n <= 3) return dark ? "linear-gradient(160deg,#334155,#64748b)" : "linear-gradient(160deg,#cbd5e1,#94a3b8)";
  if (n >= 71 && n < 80) return dark ? "linear-gradient(160deg,#1e293b,#94a3b8)" : "linear-gradient(160deg,#e2e8f0,#bfdbfe)";
  if (n >= 50) return dark ? "linear-gradient(160deg,#1e293b,#1d4ed8)" : "linear-gradient(160deg,#93c5fd,#64748b)";
  return dark ? "linear-gradient(160deg,#1e293b,#334155)" : "linear-gradient(160deg,#e0f2fe,#bae6fd)";
}

function WeatherCard(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const cur = d.current && typeof d.current === "object" ? d.current : {};
  const daily = Array.isArray(d.daily) ? d.daily : [];
  if (d.error) return null;
  const emoji = iconFor(cur.weather_code, cur.icon);
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 440,
      borderRadius: 20,
      overflow: "hidden",
      color: dark ? "#f8fafc" : "#0f172a",
      boxShadow: dark ? "0 12px 32px rgba(0,0,0,.35)" : "0 12px 28px rgba(14,165,233,.18)",
    },
    "data-octop-plugin-ui": "weather",
    children: [
      _jsxs("div", {
        style: {
          padding: "18px 18px 16px",
          background: sky(cur.weather_code, dark),
        },
        children: [
          _jsx("div", {
            style: { fontSize: 13, opacity: 0.85, fontWeight: 600 },
            children: `${d.city || ""} ${d.country || ""}`.trim(),
          }),
          _jsxs("div", {
            style: { display: "flex", alignItems: "center", gap: 12, marginTop: 8 },
            children: [
              _jsx("span", { style: { fontSize: 56, lineHeight: 1, filter: "drop-shadow(0 4px 8px rgba(0,0,0,.15))" }, children: emoji }),
              _jsxs("div", {
                children: [
                  _jsxs("div", {
                    style: { fontSize: 44, fontWeight: 800, letterSpacing: -1, lineHeight: 1 },
                    children: [cur.temp == null ? "—" : cur.temp, _jsx("span", { style: { fontSize: 22, fontWeight: 600 }, children: "°" })],
                  }),
                  _jsx("div", { style: { fontSize: 15, fontWeight: 600, marginTop: 4 }, children: cur.label || "" }),
                ],
              }),
            ],
          }),
          _jsxs("div", {
            style: { display: "flex", gap: 8, marginTop: 14 },
            children: [
              _jsx("span", {
                style: {
                  padding: "6px 10px",
                  borderRadius: 999,
                  background: "rgba(255,255,255,.28)",
                  fontSize: 12,
                  fontWeight: 600,
                },
                children: `💧 ${cur.humidity ?? "—"}%`,
              }),
              _jsx("span", {
                style: {
                  padding: "6px 10px",
                  borderRadius: 999,
                  background: "rgba(255,255,255,.28)",
                  fontSize: 12,
                  fontWeight: 600,
                },
                children: `🌬️ ${cur.wind ?? "—"} km/h`,
              }),
            ],
          }),
        ],
      }),
      _jsx("div", {
        style: {
          display: "grid",
          gridTemplateColumns: `repeat(${Math.max(daily.length, 1)}, 1fr)`,
          gap: 6,
          padding: 12,
          background: dark ? "#18181b" : "#fff",
        },
        children: daily.map((row) =>
          _jsxs(
            "div",
            {
              style: { textAlign: "center", padding: "8px 4px", borderRadius: 12, background: dark ? "#27272a" : "#f8fafc" },
              children: [
                _jsx("div", { style: { fontSize: 11, opacity: 0.65, marginBottom: 4 }, children: String(row.date || "").slice(5) }),
                _jsx("div", { style: { fontSize: 22, lineHeight: 1.2 }, children: iconFor(row.weather_code, row.icon) }),
                _jsx("div", { style: { fontSize: 12, fontWeight: 700, marginTop: 4 }, children: `${row.t_min ?? "?"}° / ${row.t_max ?? "?"}°` }),
              ],
            },
            String(row.date),
          ),
        ),
      }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "weather_card",
    tools: ["get_weather"],
    component: WeatherCard,
  });
}
