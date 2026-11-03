const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function UnitConvert(props) {
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.error) return null;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 320,
      borderRadius: 16,
      padding: 16,
      background: "linear-gradient(135deg,#eef2ff,#e0e7ff)",
      fontWeight: 600,
    },
    "data-octop-plugin-ui": "unit-convert",
    children: [
      _jsxs("div", { style: { fontSize: 22, fontWeight: 800 }, children: [d.value, " ", d.from_unit] }),
      _jsx("div", { style: { margin: "8px 0", opacity: 0.5 }, children: "↓" }),
      _jsxs("div", { style: { fontSize: 22, fontWeight: 800, color: "#4338ca" }, children: [d.result, " ", d.to_unit] }),
      d.category ? _jsx("div", { style: { fontSize: 11, marginTop: 8, opacity: 0.6 }, children: d.category }) : null,
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "unit_convert_card", tools: ["convert_unit"], component: UnitConvert });
}
