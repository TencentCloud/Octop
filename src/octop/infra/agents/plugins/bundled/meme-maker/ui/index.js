const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function MemeMaker(props) {
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.error || !d.image_url) return null;
  return _jsxs("div", {
    style: { margin: 0, maxWidth: 420, borderRadius: 12, overflow: "hidden", boxShadow: "0 10px 24px rgba(0,0,0,.12)" },
    "data-octop-plugin-ui": "meme-maker",
    children: [
      _jsx("img", { src: d.image_url, alt: d.template || "meme", style: { width: "100%", display: "block" } }),
      _jsxs("div", { style: { padding: 8, fontSize: 11, opacity: 0.6, wordBreak: "break-all" }, children: [d.image_url] }),
    ],
  });
}

function MemeTemplates(props) {
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const items = Array.isArray(d.items) ? d.items : [];
  return _jsxs("div", {
    style: { margin: 0, maxWidth: 360, borderRadius: 14, padding: 12, background: "#fdf2f8", border: "1px solid #fbcfe8" },
    "data-octop-plugin-ui": "meme-maker",
    children: [
      _jsx("div", { style: { fontWeight: 800, marginBottom: 8 }, children: "模板列表" }),
      items.map((row) =>
        _jsxs("div", { style: { fontSize: 13, marginBottom: 6 }, children: [
          _jsx("code", { children: row.id }),
          " — ",
          row.name,
          row.hint ? _jsxs("span", { style: { opacity: 0.65 }, children: [" · ", row.hint] }) : null,
        ] }, row.id),
      ),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "meme_maker_card", tools: ["make_meme"], component: MemeMaker });
  host.registerRenderer({ id: "meme_templates_list", tools: ["list_meme_templates"], component: MemeTemplates });
}
