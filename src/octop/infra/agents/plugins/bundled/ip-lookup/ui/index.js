const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function IpLookup(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.error) return null;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 360,
      borderRadius: 18,
      padding: 16,
      background: dark ? "#134e4a" : "linear-gradient(135deg,#ccfbf1,#99f6e4)",
      color: dark ? "#ccfbf1" : "#115e59",
      boxShadow: "0 10px 24px rgba(13,148,136,.15)",
    },
    "data-octop-plugin-ui": "ip-lookup",
    children: [
      _jsx("div", { style: { fontWeight: 800, fontSize: 18 }, children: d.query || "IP" }),
      _jsxs("div", { style: { marginTop: 8, lineHeight: 1.6 }, children: [
        _jsxs("div", { children: ["📍 ", d.country, " ", d.regionName, " ", d.city] }),
        _jsxs("div", { children: ["🌐 ", d.isp || ""] }),
      ] }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "ip_lookup_card", tools: ["lookup_ip"], component: IpLookup });
}
