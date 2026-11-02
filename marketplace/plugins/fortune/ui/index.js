const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function FortuneCard(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.kind === "dice") {
    const rolls = Array.isArray(d.rolls) ? d.rolls : [];
    return _jsxs("div", {
      style: {
        margin: 0,
        maxWidth: 400,
        borderRadius: 20,
        padding: 18,
        textAlign: "center",
        background: dark ? "linear-gradient(165deg,#27272a,#18181b)" : "linear-gradient(165deg,#fff7ed,#ffedd5)",
        boxShadow: "0 10px 28px rgba(234,88,12,.12)",
      },
      "data-octop-plugin-ui": "fortune",
      children: [
        _jsx("div", { style: { fontSize: 22 }, children: "🎲" }),
        _jsx("div", { style: { opacity: 0.7, margin: "4px 0 12px", fontWeight: 600 }, children: d.notation || "dice" }),
        _jsx("div", {
          style: { display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" },
          children: rolls.map((n, i) =>
            _jsx(
              "div",
              {
                style: {
                  width: 52,
                  height: 52,
                  borderRadius: 14,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 800,
                  fontSize: 22,
                  background: dark ? "#3f3f46" : "#fff",
                  boxShadow: "0 8px 16px rgba(0,0,0,.08)",
                },
                children: String(n),
              },
              String(i),
            ),
          ),
        }),
        _jsx("div", { style: { marginTop: 12, fontWeight: 800, fontSize: 16 }, children: `合计 ${d.total ?? ""}` }),
      ],
    });
  }
  if (d.kind === "lot") {
    return _jsxs("div", {
      style: {
        margin: 0,
        width: 120,
        minHeight: 220,
        borderRadius: 12,
        padding: "16px 12px",
        writingMode: "vertical-rl",
        textAlign: "center",
        background: "linear-gradient(180deg,#7f1d1d,#b91c1c)",
        color: "#fef3c7",
        boxShadow: "0 12px 24px rgba(127,29,29,.35)",
      },
      "data-octop-plugin-ui": "fortune",
      children: [
        _jsx("div", { style: { fontWeight: 800, fontSize: 20, letterSpacing: 4 }, children: d.title || "" }),
        _jsx("div", { style: { marginTop: 16, lineHeight: 1.8 }, children: d.verse || "" }),
      ],
    });
  }
  const score = Number(d.score) || 0;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 360,
      borderRadius: 22,
      padding: 20,
      textAlign: "center",
      background: dark ? "linear-gradient(165deg,#312e81,#1e1b4b)" : "linear-gradient(165deg,#eef2ff,#c7d2fe)",
      color: dark ? "#e0e7ff" : "#1e1b4b",
      boxShadow: "0 14px 32px rgba(79,70,229,.18)",
    },
    "data-octop-plugin-ui": "fortune",
    children: [
      _jsx("div", { style: { fontSize: 13, opacity: 0.75 }, children: `✨ ${d.name || "你"} · ${d.date || ""}` }),
      _jsxs("div", { style: { fontSize: 52, fontWeight: 800, margin: "6px 0 2px" }, children: [score, _jsx("span", { style: { fontSize: 16 }, children: "分" })] }),
      _jsx("div", { style: { height: 8, borderRadius: 99, background: "rgba(255,255,255,.35)", overflow: "hidden", margin: "0 24px 12px" }, children: _jsx("div", { style: { width: `${score}%`, height: "100%", background: "#6366f1" } }) }),
      _jsx("div", { style: { fontWeight: 600, lineHeight: 1.5 }, children: d.summary || "" }),
      _jsxs("div", { style: { display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap", marginTop: 12, fontSize: 12 }, children: [
        _jsx("span", { style: { padding: "6px 10px", borderRadius: 999, background: "rgba(255,255,255,.4)", fontWeight: 700 }, children: `🎨 ${d.lucky_color || "—"}` }),
        _jsx("span", { style: { padding: "6px 10px", borderRadius: 999, background: "rgba(255,255,255,.4)", fontWeight: 700 }, children: `宜 ${d.do || ""}` }),
        _jsx("span", { style: { padding: "6px 10px", borderRadius: 999, background: "rgba(255,255,255,.4)", fontWeight: 700 }, children: `忌 ${d.dont || ""}` }),
      ] }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "fortune_card",
    tools: ["roll_dice", "daily_fortune", "draw_lot"],
    component: FortuneCard,
  });
}
