const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function Card(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.silent) return null;
  if (d.error) {
    return _jsx("div", {
      style: {
        margin: 0,
        padding: "12px 14px",
        borderRadius: 14,
        maxWidth: 420,
        background: dark ? "#3f1d1d" : "#fef2f2",
        color: dark ? "#fecaca" : "#b91c1c",
        fontWeight: 600,
      },
      "data-octop-plugin-ui": "slack-calendar",
      children: String(d.error),
    });
  }
  const weekend = Number(d.days_to_weekend);
  const holidayDays = d.days_to_holiday;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 380,
      borderRadius: 20,
      padding: 18,
      background: dark
        ? "linear-gradient(165deg,#1e1b4b,#312e81)"
        : "linear-gradient(165deg,#eef2ff,#c7d2fe)",
      color: dark ? "#e0e7ff" : "#312e81",
      boxShadow: "0 12px 28px rgba(99,102,241,.18)",
    },
    "data-octop-plugin-ui": "slack-calendar",
    children: [
      _jsx("div", { style: { fontSize: 22 }, children: "🐟" }),
      _jsx("div", {
        style: { fontWeight: 800, fontSize: 18, marginTop: 6 },
        children: `周${d.weekday || ""} · ${d.date || ""}`,
      }),
      _jsx("div", {
        style: { marginTop: 12, fontSize: 28, fontWeight: 800 },
        children: weekend === 0 ? "周末快乐" : `${weekend} 天后周末`,
      }),
      holidayDays != null
        ? _jsx("div", {
            style: { marginTop: 6, fontWeight: 600, opacity: 0.9 },
            children:
              Number(holidayDays) === 0
                ? d.holiday_name
                : `距${d.holiday_name}还有 ${holidayDays} 天`,
          })
        : null,
      _jsxs("div", {
        style: {
          display: "flex",
          gap: 8,
          flexWrap: "wrap",
          marginTop: 14,
          fontSize: 12,
        },
        children: [
          _jsx("span", {
            style: {
              padding: "6px 10px",
              borderRadius: 999,
              background: "rgba(255,255,255,.35)",
              fontWeight: 700,
            },
            children: `宜 ${d.do || ""}`,
          }),
          _jsx("span", {
            style: {
              padding: "6px 10px",
              borderRadius: 999,
              background: "rgba(255,255,255,.35)",
              fontWeight: 700,
            },
            children: `忌 ${d.dont || ""}`,
          }),
        ],
      }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "slack_calendar_card",
    tools: ["slack_calendar"],
    component: Card,
  });
}
