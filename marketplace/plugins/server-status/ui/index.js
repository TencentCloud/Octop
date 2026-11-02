const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function Bar({ label, percent, detail, icon }) {
  const pct = Math.max(0, Math.min(100, Number(percent) || 0));
  const color = pct >= 90 ? "#ef4444" : pct >= 70 ? "#f59e0b" : "#22c55e";
  return _jsxs("div", {
    style: { marginTop: 12 },
    children: [
      _jsxs("div", {
        style: { display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 12, fontWeight: 600 },
        children: [
          _jsx("span", { children: `${icon} ${label}` }),
          _jsx("span", { style: { opacity: 0.7, fontWeight: 500 }, children: detail || `${pct.toFixed(0)}%` }),
        ],
      }),
      _jsx("div", {
        style: { height: 10, borderRadius: 99, background: "rgba(148,163,184,.25)", overflow: "hidden" },
        children: _jsx("div", { style: { width: `${pct}%`, height: "100%", background: color, borderRadius: 99 } }),
      }),
    ],
  });
}

function ServerStatusCard(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const os = d.os && typeof d.os === "object" ? d.os : {};
  const cpu = d.cpu && typeof d.cpu === "object" ? d.cpu : {};
  const mem = d.memory && typeof d.memory === "object" ? d.memory : {};
  const disk = d.disk && typeof d.disk === "object" ? d.disk : {};
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 440,
      borderRadius: 20,
      overflow: "hidden",
      background: dark ? "#18181b" : "#fff",
      boxShadow: "0 12px 28px rgba(15,23,42,.12)",
      border: dark ? "1px solid #27272a" : "1px solid #e2e8f0",
    },
    "data-octop-plugin-ui": "server-status",
    children: [
      _jsxs("div", {
        style: {
          padding: "14px 16px",
          background: dark ? "linear-gradient(135deg,#0f172a,#1e3a8a)" : "linear-gradient(135deg,#1e3a8a,#38bdf8)",
          color: "#fff",
        },
        children: [
          _jsx("div", { style: { fontSize: 13, opacity: 0.85 }, children: "🖥️ 服务器状态" }),
          _jsx("div", { style: { fontWeight: 800, fontSize: 18, marginTop: 4 }, children: d.hostname || "Server" }),
          _jsx("div", { style: { fontSize: 12, opacity: 0.85, marginTop: 4 }, children: `${os.pretty || ""} ${os.machine || ""}`.trim() }),
        ],
      }),
      _jsxs("div", {
        style: { padding: "8px 16px 16px" },
        children: [
          _jsx("div", { style: { fontSize: 12, opacity: 0.65, marginTop: 8 }, children: `内核 ${d.kernel || "—"} · 已运行 ${d.uptime_h || "—"}` }),
          _jsx(Bar, { label: "CPU", icon: "🧠", percent: cpu.percent, detail: `${Number(cpu.percent || 0).toFixed(0)}% · ${cpu.logical || "?"} 核` }),
          _jsx(Bar, { label: "内存", icon: "💾", percent: mem.percent, detail: `${mem.used_h || "?"} / ${mem.total_h || "?"}` }),
          _jsx(Bar, { label: "磁盘", icon: "📀", percent: disk.percent, detail: `${disk.used_h || "?"} / ${disk.total_h || "?"}` }),
        ],
      }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "server_status",
    tools: ["get_server_status"],
    component: ServerStatusCard,
  });
}
