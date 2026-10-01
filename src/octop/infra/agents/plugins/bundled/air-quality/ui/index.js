const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

const LABEL_COLOR = { 优: "#22c55e", 良: "#84cc16", 轻度: "#eab308", 中度: "#f97316", 重度: "#ef4444" };

function AirQuality(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.error) return null;
  const accent = LABEL_COLOR[d.aqi_label] || "#65a30d";
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 340,
      borderRadius: 20,
      padding: 18,
      background: dark ? "#1c1917" : "#fff",
      border: `2px solid ${accent}`,
      boxShadow: `0 12px 28px ${accent}33`,
    },
    "data-octop-plugin-ui": "air-quality",
    children: [
      _jsx("div", { style: { fontWeight: 800 }, children: d.city || "空气质量" }),
      _jsxs("div", { style: { display: "flex", alignItems: "baseline", gap: 10, marginTop: 10 }, children: [
        _jsx("span", { style: { fontSize: 36, fontWeight: 800, color: accent }, children: d.aqi_label || "—" }),
        _jsxs("span", { style: { opacity: 0.7 }, children: ["AQI ", d.us_aqi ?? d.european_aqi ?? "—"] }),
      ] }),
      _jsxs("div", { style: { marginTop: 12, fontSize: 13, opacity: 0.85 }, children: [
        _jsxs("div", { children: ["PM2.5 ", d.pm2_5 ?? "—", " · PM10 ", d.pm10 ?? "—"] }),
      ] }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "air_quality_card", tools: ["get_air_quality"], component: AirQuality });
}
