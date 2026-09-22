const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function ColorConvert(props) {
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.error) return null;
  const rgb = d.rgb || {};
  const swatch = d.hex || "#888";
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 320,
      borderRadius: 18,
      overflow: "hidden",
      boxShadow: "0 10px 24px rgba(0,0,0,.1)",
    },
    "data-octop-plugin-ui": "color-convert",
    children: [
      _jsx("div", { style: { height: 56, background: swatch } }),
      _jsxs("div", { style: { padding: 14, background: "#fff" }, children: [
        _jsx("div", { style: { fontWeight: 800 }, children: d.hex || "" }),
        _jsxs("div", { style: { fontSize: 13, marginTop: 6, opacity: 0.8 }, children: [
          `rgb(${rgb.r ?? 0}, ${rgb.g ?? 0}, ${rgb.b ?? 0})`,
        ] }),
        d.hsl
          ? _jsxs("div", { style: { fontSize: 13, marginTop: 4, opacity: 0.8 }, children: [
              `hsl(${d.hsl.h}, ${d.hsl.s}%, ${d.hsl.l}%)`,
            ] })
          : null,
      ] }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "color_convert_card", tools: ["convert_color"], component: ColorConvert });
}
