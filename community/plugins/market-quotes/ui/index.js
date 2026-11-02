const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

const TITLES = { forex: "💱 汇率", crypto: "🪙 加密货币", cn_stock: "📈 A股" };

function changeColor(pct, kind) {
  if (pct == null || Number.isNaN(Number(pct))) return "inherit";
  const n = Number(pct);
  if (n === 0) return "inherit";
  const up = n > 0;
  if (kind === "cn_stock") return up ? "#ef4444" : "#22c55e";
  return up ? "#22c55e" : "#ef4444";
}

function QuotesCard(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const rows = Array.isArray(d.rows) ? d.rows : [];
  if (d.error && rows.length === 0) return null;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 480,
      borderRadius: 18,
      overflow: "hidden",
      background: dark ? "#18181b" : "#fff",
      border: dark ? "1px solid #27272a" : "1px solid #e2e8f0",
      boxShadow: "0 10px 24px rgba(15,23,42,.08)",
    },
    "data-octop-plugin-ui": "market-quotes",
    children: [
      _jsx("div", {
        style: {
          padding: "12px 14px",
          fontWeight: 800,
          background: dark ? "#27272a" : "linear-gradient(90deg,#ecfdf5,#eff6ff)",
        },
        children: TITLES[d.kind] || "行情",
      }),
      _jsx("table", {
        style: { width: "100%", borderCollapse: "collapse" },
        children: _jsx("tbody", {
          children: rows.map((row, i) =>
            _jsxs(
              "tr",
              {
                style: { background: i % 2 ? (dark ? "#1c1c1f" : "#f8fafc") : "transparent" },
                children: [
                  _jsx("td", { style: { padding: "10px 14px", fontWeight: 700 }, children: row.name || row.symbol }),
                  _jsx("td", {
                    style: { padding: "10px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 700 },
                    children: row.price_cny != null ? `$${row.price} / ¥${row.price_cny}` : row.price,
                  }),
                  _jsx("td", {
                    style: {
                      padding: "10px 14px",
                      textAlign: "right",
                      color: changeColor(row.pct, d.kind),
                      fontVariantNumeric: "tabular-nums",
                      fontWeight: 800,
                    },
                    children: row.pct == null ? "" : `${Number(row.pct) > 0 ? "▲ " : Number(row.pct) < 0 ? "▼ " : ""}${Number(row.pct).toFixed(2)}%`,
                  }),
                ],
              },
              String(row.symbol),
            ),
          ),
        }),
      }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "market_quotes_card",
    tools: ["get_forex", "get_crypto", "get_cn_stock"],
    component: QuotesCard,
  });
}
