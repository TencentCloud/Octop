const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;
const { useEffect, useRef, useState } = React;

const COLS = 10;
const ROWS = 20;
const CELL = 16;
const KINDS = ["I", "O", "T", "S", "Z", "J", "L"];
const COLORS = {
  I: "#22d3ee",
  O: "#facc15",
  T: "#c084fc",
  S: "#4ade80",
  Z: "#f87171",
  J: "#60a5fa",
  L: "#fb923c",
};
const SHAPES = {
  I: [
    [[0, 1], [1, 1], [2, 1], [3, 1]],
    [[1, 0], [1, 1], [1, 2], [1, 3]],
    [[0, 2], [1, 2], [2, 2], [3, 2]],
    [[2, 0], [2, 1], [2, 2], [2, 3]],
  ],
  O: [
    [[1, 1], [1, 2], [2, 1], [2, 2]],
    [[1, 1], [1, 2], [2, 1], [2, 2]],
    [[1, 1], [1, 2], [2, 1], [2, 2]],
    [[1, 1], [1, 2], [2, 1], [2, 2]],
  ],
  T: [
    [[1, 0], [0, 1], [1, 1], [2, 1]],
    [[1, 0], [1, 1], [2, 1], [1, 2]],
    [[0, 1], [1, 1], [2, 1], [1, 2]],
    [[1, 0], [0, 1], [1, 1], [1, 2]],
  ],
  S: [
    [[1, 0], [2, 0], [0, 1], [1, 1]],
    [[1, 0], [1, 1], [2, 1], [2, 2]],
    [[1, 1], [2, 1], [0, 2], [1, 2]],
    [[0, 0], [0, 1], [1, 1], [1, 2]],
  ],
  Z: [
    [[0, 0], [1, 0], [1, 1], [2, 1]],
    [[2, 0], [1, 1], [2, 1], [1, 2]],
    [[0, 1], [1, 1], [1, 2], [2, 2]],
    [[1, 0], [0, 1], [1, 1], [0, 2]],
  ],
  J: [
    [[0, 0], [0, 1], [1, 1], [2, 1]],
    [[1, 0], [2, 0], [1, 1], [1, 2]],
    [[0, 1], [1, 1], [2, 1], [2, 2]],
    [[1, 0], [1, 1], [0, 2], [1, 2]],
  ],
  L: [
    [[2, 0], [0, 1], [1, 1], [2, 1]],
    [[1, 0], [1, 1], [1, 2], [2, 2]],
    [[0, 1], [1, 1], [2, 1], [0, 2]],
    [[0, 0], [1, 0], [1, 1], [1, 2]],
  ],
};

function emptyBoard() {
  return Array.from({ length: ROWS }, () => Array(COLS).fill(null));
}

function shuffle(list) {
  const out = list.slice();
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = out[i];
    out[i] = out[j];
    out[j] = tmp;
  }
  return out;
}

function cellsOf(kind, rot, x, y) {
  return SHAPES[kind][rot].map(([cx, cy]) => [x + cx, y + cy]);
}

function collides(board, kind, rot, x, y) {
  return cellsOf(kind, rot, x, y).some(([cx, cy]) => {
    if (cx < 0 || cx >= COLS || cy >= ROWS) return true;
    if (cy < 0) return false;
    return Boolean(board[cy][cx]);
  });
}

function lockPiece(board, kind, rot, x, y) {
  const next = board.map((row) => row.slice());
  cellsOf(kind, rot, x, y).forEach(([cx, cy]) => {
    if (cy >= 0 && cy < ROWS && cx >= 0 && cx < COLS) next[cy][cx] = kind;
  });
  return next;
}

function clearLines(board) {
  const kept = board.filter((row) => row.some((cell) => !cell));
  const cleared = ROWS - kept.length;
  while (kept.length < ROWS) kept.unshift(Array(COLS).fill(null));
  return { board: kept, cleared };
}

function spawn(bag) {
  let nextBag = bag.slice();
  if (nextBag.length < 2) nextBag = nextBag.concat(shuffle(KINDS));
  const kind = nextBag[0];
  nextBag = nextBag.slice(1);
  return { kind, rot: 0, x: 3, y: -1, bag: nextBag, next: nextBag[0] || shuffle(KINDS)[0] };
}

function createGame() {
  const spawned = spawn([]);
  return {
    board: emptyBoard(),
    ...spawned,
    score: 0,
    lines: 0,
    level: 1,
    paused: false,
    over: false,
  };
}

function tryMove(state, dx, dy, drot) {
  if (state.paused || state.over) return state;
  const rot = (state.rot + drot + 4) % 4;
  const x = state.x + dx;
  const y = state.y + dy;
  if (!collides(state.board, state.kind, rot, x, y)) {
    return { ...state, rot, x, y };
  }
  if (drot !== 0) {
    for (const kick of [-1, 1, -2, 2]) {
      if (!collides(state.board, state.kind, rot, state.x + kick, y)) {
        return { ...state, rot, x: state.x + kick, y };
      }
    }
  }
  return null;
}

function hardDropY(state) {
  let y = state.y;
  while (!collides(state.board, state.kind, state.rot, state.x, y + 1)) y += 1;
  return y;
}

function place(state) {
  const locked = lockPiece(state.board, state.kind, state.rot, state.x, state.y);
  const { board, cleared } = clearLines(locked);
  const scores = [0, 100, 300, 500, 800];
  const lines = state.lines + cleared;
  const spawned = spawn(state.bag);
  const next = {
    ...state,
    board,
    ...spawned,
    score: state.score + (scores[cleared] || 0) * state.level + 2,
    lines,
    level: 1 + Math.floor(lines / 10),
  };
  if (collides(next.board, next.kind, next.rot, next.x, next.y)) {
    return { ...next, over: true };
  }
  return next;
}

function stepDown(state) {
  const moved = tryMove(state, 0, 1, 0);
  if (moved) return moved;
  return place(state);
}

function btnStyle(wide) {
  return {
    border: "none",
    borderRadius: 10,
    padding: wide ? "10px 0" : "8px 0",
    fontSize: 13,
    fontWeight: 700,
    cursor: "pointer",
    background: "#27272a",
    color: "#f4f4f5",
  };
}

function MiniPreview({ kind }) {
  const cells = new Set((SHAPES[kind] || SHAPES.I)[0].map(([x, y]) => `${x},${y}`));
  return _jsx("div", {
    style: { display: "grid", gridTemplateColumns: "repeat(4, 10px)", gap: 2, justifyContent: "center" },
    children: Array.from({ length: 16 }, (_, i) => {
      const x = i % 4;
      const y = Math.floor(i / 4);
      const on = cells.has(`${x},${y}`);
      return _jsx(
        "div",
        {
          style: {
            width: 10,
            height: 10,
            borderRadius: 2,
            background: on ? COLORS[kind] : "transparent",
          },
        },
        String(i),
      );
    }),
  });
}

function TetrisCard(props) {
  const [game, setGame] = useState(createGame);
  const gameRef = useRef(game);
  gameRef.current = game;
  const [focused, setFocused] = useState(false);
  const wrapRef = useRef(null);
  const patchedOver = useRef(false);

  useEffect(() => {
    const delay = Math.max(120, 720 - (game.level - 1) * 70);
    const id = setInterval(() => {
      setGame((g) => {
        if (g.paused || g.over) return g;
        return stepDown(g);
      });
    }, delay);
    return () => clearInterval(id);
  }, [game.level, game.paused, game.over]);

  useEffect(() => {
    if (!game.over || patchedOver.current || !props.callId) return;
    patchedOver.current = true;
    const d = props.data && typeof props.data === "object" ? props.data : {};
    props.host.patchResult(props.callId, {
      ...d,
      kind: "tetris",
      score: game.score,
      lines: game.lines,
      over: true,
    });
  }, [game.over, game.score, game.lines, props]);

  const act = (fn) => {
    setGame((g) => {
      const next = fn(g);
      return next || g;
    });
  };

  useEffect(() => {
    const onKey = (e) => {
      if (!focused) return;
      const g = gameRef.current;
      if (e.key === "p" || e.key === "P") {
        e.preventDefault();
        setGame((cur) => (cur.over ? cur : { ...cur, paused: !cur.paused }));
        return;
      }
      if (g.paused || g.over) return;
      const map = {
        ArrowLeft: () => act((s) => tryMove(s, -1, 0, 0)),
        ArrowRight: () => act((s) => tryMove(s, 1, 0, 0)),
        ArrowDown: () => act((s) => tryMove(s, 0, 1, 0) || s),
        ArrowUp: () => act((s) => tryMove(s, 0, 0, 1)),
        " ": () =>
          act((s) => {
            if (s.paused || s.over) return s;
            const y = hardDropY(s);
            return place({ ...s, y, score: s.score + Math.max(0, y - s.y) * 2 });
          }),
        z: () => act((s) => tryMove(s, 0, 0, -1)),
        Z: () => act((s) => tryMove(s, 0, 0, -1)),
        x: () => act((s) => tryMove(s, 0, 0, 1)),
        X: () => act((s) => tryMove(s, 0, 0, 1)),
      };
      const handler = map[e.key];
      if (!handler) return;
      e.preventDefault();
      handler();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focused]);

  const ghostY = hardDropY(game);
  const live = new Set(cellsOf(game.kind, game.rot, game.x, game.y).map(([x, y]) => `${x},${y}`));
  const ghost = new Set(cellsOf(game.kind, game.rot, game.x, ghostY).map(([x, y]) => `${x},${y}`));

  return _jsxs("div", {
    ref: wrapRef,
    tabIndex: 0,
    onClick: () => {
      setFocused(true);
      if (wrapRef.current && wrapRef.current.focus) wrapRef.current.focus();
    },
    onBlur: () => setFocused(false),
    style: {
      margin: 0,
      maxWidth: 360,
      outline: focused ? "2px solid #22d3ee" : "none",
      borderRadius: 20,
      padding: 14,
      background: "linear-gradient(180deg,#0f172a,#020617)",
      color: "#e2e8f0",
      boxShadow: "0 16px 36px rgba(2,6,23,.45)",
      fontFamily: "ui-sans-serif, system-ui, sans-serif",
    },
    "data-octop-plugin-ui": "tetris",
    children: [
      _jsxs("div", {
        style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 },
        children: [
          _jsx("div", { style: { fontWeight: 800, fontSize: 15 }, children: "🧱 俄罗斯方块" }),
          _jsx("div", {
            style: { fontSize: 11, opacity: focused ? 0.95 : 0.55 },
            children: focused ? "键盘已接管" : "点击卡片后用方向键",
          }),
        ],
      }),
      _jsxs("div", { style: { display: "flex", gap: 12 }, children: [
        _jsx("div", {
          style: {
            position: "relative",
            width: COLS * CELL,
            height: ROWS * CELL,
            background: "#020617",
            borderRadius: 8,
            overflow: "hidden",
            boxShadow: "inset 0 0 0 1px #1e293b",
          },
          children: Array.from({ length: ROWS * COLS }, (_, i) => {
            const x = i % COLS;
            const y = Math.floor(i / COLS);
            const locked = game.board[y][x];
            const isLive = live.has(`${x},${y}`);
            const isGhost = !isLive && ghost.has(`${x},${y}`);
            const kind = isLive ? game.kind : locked;
            return _jsx(
              "div",
              {
                style: {
                  position: "absolute",
                  left: x * CELL,
                  top: y * CELL,
                  width: CELL - 1,
                  height: CELL - 1,
                  borderRadius: 3,
                  background: kind ? COLORS[kind] : isGhost ? "rgba(148,163,184,.28)" : "rgba(15,23,42,.6)",
                  boxShadow: kind ? "inset 0 0 0 1px rgba(255,255,255,.2)" : "none",
                },
              },
              String(i),
            );
          }),
        }),
        _jsxs("div", {
          style: { width: 88, fontSize: 12, display: "flex", flexDirection: "column", gap: 10 },
          children: [
            _jsxs("div", {
              style: { background: "#111827", borderRadius: 10, padding: 8 },
              children: [
                _jsx("div", { style: { opacity: 0.6, marginBottom: 4 }, children: "下一个" }),
                _jsx(MiniPreview, { kind: game.next }),
              ],
            }),
            _jsxs("div", { style: { background: "#111827", borderRadius: 10, padding: 8, lineHeight: 1.6 }, children: [
              _jsx("div", { children: `分数 ${game.score}` }),
              _jsx("div", { children: `行数 ${game.lines}` }),
              _jsx("div", { children: `等级 ${game.level}` }),
            ] }),
            game.over
              ? _jsx("div", { style: { color: "#fca5a5", fontWeight: 800 }, children: "游戏结束" })
              : game.paused
                ? _jsx("div", { style: { color: "#fde68a", fontWeight: 700 }, children: "已暂停" })
                : null,
          ],
        }),
      ] }),
      _jsxs("div", {
        style: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginTop: 12 },
        children: [
          _jsx("button", { type: "button", style: btnStyle(), onClick: () => act((s) => tryMove(s, -1, 0, 0)), children: "←" }),
          _jsx("button", { type: "button", style: btnStyle(), onClick: () => act((s) => tryMove(s, 0, 0, 1)), children: "↻" }),
          _jsx("button", { type: "button", style: btnStyle(), onClick: () => act((s) => tryMove(s, 1, 0, 0)), children: "→" }),
          _jsx("button", { type: "button", style: btnStyle(), onClick: () => act((s) => tryMove(s, 0, 1, 0) || s), children: "↓" }),
          _jsx("button", {
            type: "button",
            style: btnStyle(),
            onClick: () =>
              act((s) => {
                if (s.paused || s.over) return s;
                const y = hardDropY(s);
                return place({ ...s, y, score: s.score + Math.max(0, y - s.y) * 2 });
              }),
            children: "硬降",
          }),
          _jsx("button", {
            type: "button",
            style: btnStyle(),
            onClick: () => setGame((g) => (g.over ? g : { ...g, paused: !g.paused })),
            children: game.paused ? "继续" : "暂停",
          }),
        ],
      }),
      _jsx("button", {
        type: "button",
        style: { ...btnStyle(true), width: "100%", marginTop: 6, background: "#1d4ed8" },
        onClick: () => {
          patchedOver.current = false;
          setGame(createGame());
        },
        children: "重新开始",
      }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "tetris_game",
    tools: ["start_tetris"],
    component: TetrisCard,
  });
}
