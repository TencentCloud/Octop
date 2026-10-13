const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function FunFacts(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const isJoke = d.kind === "joke";
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 400,
      borderRadius: 18,
      padding: 16,
      background: dark
        ? isJoke
          ? "#422006"
          : "#27272a"
        : isJoke
          ? "linear-gradient(135deg,#fef3c7,#fde68a)"
          : "linear-gradient(135deg,#fffbeb,#fef3c7)",
      boxShadow: "0 10px 24px rgba(245,158,11,.15)",
    },
    "data-octop-plugin-ui": "fun-facts",
    children: [
      _jsx("div", { style: { fontWeight: 800, marginBottom: 8 }, children: isJoke ? "😄 笑话" : "💡 冷知识" }),
      _jsx("div", { style: { lineHeight: 1.6 }, children: d.content || "" }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "fun_facts_card", tools: ["random_fun_fact"], component: FunFacts });
}
