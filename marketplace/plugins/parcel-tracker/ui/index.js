const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function ParcelCard(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const traces = Array.isArray(d.traces) ? d.traces : [];
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 480,
      borderRadius: 20,
      overflow: "hidden",
      background: dark ? "#18181b" : "#fff",
      boxShadow: "0 12px 28px rgba(15,23,42,.1)",
      border: dark ? "1px solid #27272a" : "1px solid #e2e8f0",
    },
    "data-octop-plugin-ui": "parcel-tracker",
    children: [
      _jsxs("div", {
        style: {
          padding: "14px 16px",
          background: dark ? "#1e3a5f" : "linear-gradient(135deg,#0ea5e9,#2563eb)",
          color: "#fff",
        },
        children: [
          _jsx("div", { style: { fontSize: 13, opacity: 0.85 }, children: "📦 快递追踪" }),
          _jsx("div", { style: { fontWeight: 800, fontSize: 18, marginTop: 4 }, children: d.number || "—" }),
          d.company ? _jsx("div", { style: { fontSize: 12, opacity: 0.85 }, children: `承运商 ${d.company}` }) : null,
        ],
      }),
      _jsx("div", {
        style: { padding: "12px 16px 16px" },
        children: traces.length
          ? _jsx("div", {
              children: traces.map((row, i) =>
                _jsxs(
                  "div",
                  {
                    style: { display: "flex", gap: 10, marginBottom: 12 },
                    children: [
                      _jsxs("div", {
                        style: { display: "flex", flexDirection: "column", alignItems: "center", width: 14 },
                        children: [
                          _jsx("span", {
                            style: {
                              width: 10,
                              height: 10,
                              borderRadius: 99,
                              background: i === 0 ? "#0ea5e9" : "#cbd5e1",
                              marginTop: 4,
                            },
                          }),
                          i < traces.length - 1
                            ? _jsx("span", { style: { width: 2, flex: 1, minHeight: 18, background: dark ? "#3f3f46" : "#e2e8f0" } })
                            : null,
                        ],
                      }),
                      _jsxs("div", {
                        style: { flex: 1 },
                        children: [
                          _jsx("div", { style: { fontSize: 12, opacity: 0.55 }, children: row.time || "" }),
                          _jsx("div", { style: { fontSize: 13, fontWeight: i === 0 ? 700 : 500 }, children: row.context || "" }),
                        ],
                      }),
                    ],
                  },
                  String(i),
                ),
              ),
            })
          : _jsx("div", { style: { fontSize: 13, opacity: 0.7 }, children: "暂无轨迹，可到快递100查看" }),
      }),
      d.url
        ? _jsx("a", {
            href: d.url,
            target: "_blank",
            rel: "noopener noreferrer",
            style: {
              display: "block",
              textAlign: "center",
              padding: "10px 0 14px",
              fontWeight: 700,
              color: "#2563eb",
              textDecoration: "none",
            },
            children: "在快递100打开 →",
          })
        : null,
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "parcel_timeline",
    tools: ["track_parcel"],
    component: ParcelCard,
  });
}
