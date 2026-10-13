const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function WhatToEat(props) {
  const d = props.data && typeof props.data === "object" ? props.data : {};
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 320,
      borderRadius: 18,
      padding: 18,
      textAlign: "center",
      background: "linear-gradient(135deg,#fef2f2,#fecaca)",
      boxShadow: "0 10px 24px rgba(220,38,38,.12)",
    },
    "data-octop-plugin-ui": "what-to-eat",
    children: [
      _jsx("div", { style: { fontSize: 32 }, children: "🍜" }),
      _jsx("div", { style: { fontSize: 12, opacity: 0.65, marginTop: 4 }, children: d.meal || "meal" }),
      _jsx("div", { style: { fontSize: 22, fontWeight: 800, marginTop: 8 }, children: d.dish || "" }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "what_to_eat_card", tools: ["what_to_eat"], component: WhatToEat });
}
