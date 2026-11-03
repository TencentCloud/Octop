const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function QrCard(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.error || !d.image_data_url) return null;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 280,
      borderRadius: 20,
      padding: 16,
      textAlign: "center",
      background: dark ? "#18181b" : "#fff",
      boxShadow: "0 12px 28px rgba(15,23,42,.12)",
      border: dark ? "1px solid #27272a" : "1px solid #e2e8f0",
    },
    "data-octop-plugin-ui": "qrcode",
    children: [
      _jsx("div", { style: { fontWeight: 800, marginBottom: 10 }, children: "🔳 二维码" }),
      _jsx("img", {
        src: d.image_data_url,
        alt: "qrcode",
        style: {
          width: 196,
          height: 196,
          imageRendering: "pixelated",
          borderRadius: 12,
          background: "#fff",
          padding: 8,
        },
      }),
      _jsx("div", {
        style: { marginTop: 10, wordBreak: "break-all", fontSize: 12, opacity: 0.75, textAlign: "left" },
        children: d.content || "",
      }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "qrcode_card",
    tools: ["make_qrcode"],
    component: QrCard,
  });
}
