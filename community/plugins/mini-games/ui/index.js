const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function MiniGameCard(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.kind === "guess") {
    const hintMap = { start: "开始猜吧", low: "再大一点", high: "再小一点", equal: "猜中了！" };
    const tone = d.hint === "equal" ? "#16a34a" : d.hint === "start" ? "#2563eb" : "#ea580c";
    return _jsxs("div", {
      style: {
        margin: 0,
        maxWidth: 280,
        borderRadius: 22,
        padding: 20,
        textAlign: "center",
        background: dark ? "#18181b" : "#fff",
        boxShadow: "0 12px 28px rgba(37,99,235,.12)",
        border: `2px solid ${tone}`,
      },
      "data-octop-plugin-ui": "mini-games",
      children: [
        _jsx("div", { style: { fontSize: 22 }, children: "🎯" }),
        _jsx("div", { style: { fontWeight: 800, marginTop: 4 }, children: "猜数字" }),
        _jsx("div", { style: { fontSize: 40, fontWeight: 800, margin: "8px 0", color: tone }, children: d.guess ?? "?" }),
        _jsx("div", { style: { fontWeight: 700 }, children: hintMap[d.hint] || "" }),
        _jsx("div", { style: { opacity: 0.6, marginTop: 6, fontSize: 12 }, children: `范围 ${d.low ?? 1} – ${d.high ?? 100}` }),
      ],
    });
  }
  const board = String(d.board || ".........").padEnd(9, ".").slice(0, 9);
  const cells = board.split("");
  const result = d.result;
  const patch = (idx) => {
    if (!props.callId || result || cells[idx] !== ".") return;
    const next = cells.slice();
    next[idx] = d.play_as || "X";
    props.host.patchResult(props.callId, { ...d, board: next.join("") });
  };
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 280,
      borderRadius: 22,
      padding: 16,
      textAlign: "center",
      background: dark ? "#18181b" : "#fff7ed",
      boxShadow: "0 12px 28px rgba(234,88,12,.12)",
    },
    "data-octop-plugin-ui": "mini-games",
    children: [
      _jsx("div", { style: { fontWeight: 800, marginBottom: 10 }, children: "⭕ 井字棋" }),
      _jsx("div", {
        style: { display: "grid", gridTemplateColumns: "repeat(3, 64px)", gap: 8, justifyContent: "center" },
        children: cells.map((ch, idx) =>
          _jsx(
            "button",
            {
              type: "button",
              disabled: Boolean(result) || ch !== ".",
              onClick: () => patch(idx),
              style: {
                width: 64,
                height: 64,
                fontSize: 26,
                fontWeight: 800,
                cursor: ch === "." && !result ? "pointer" : "default",
                borderRadius: 14,
                border: "none",
                background: dark ? "#27272a" : "#fff",
                color: ch === "X" ? "#ea580c" : "#2563eb",
                boxShadow: "0 4px 10px rgba(0,0,0,.06)",
              },
              children: ch === "." ? "" : ch,
            },
            String(idx),
          ),
        ),
      }),
      result
        ? _jsx("div", { style: { marginTop: 10, fontWeight: 800 }, children: result === "draw" ? "平局" : `${result} 获胜` })
        : _jsx("div", { style: { marginTop: 10, opacity: 0.65, fontSize: 12 }, children: "点格子预览，把新棋盘发给我才算落子" }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "mini_game_card",
    tools: ["tic_tac_toe", "guess_number"],
    component: MiniGameCard,
  });
}
