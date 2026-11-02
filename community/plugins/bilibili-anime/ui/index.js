const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function cardStyle(theme) {
  const dark = theme === "dark";
  return {
    margin: 0,
    padding: "14px",
    borderRadius: 18,
    border: dark ? "1px solid #3f3f46" : "1px solid #fecdd3",
    background: dark ? "#18181b" : "#fff",
    color: dark ? "#f4f4f5" : "#1f2937",
    maxWidth: 560,
    fontSize: 13,
    boxShadow: "0 12px 28px rgba(244,63,94,.12)",
  };
}

function playerUrl(ep) {
  if (!ep) return "";
  const params = new URLSearchParams();
  params.set("isOutside", "true");
  if (ep.bvid) params.set("bvid", String(ep.bvid));
  if (ep.aid) params.set("aid", String(ep.aid));
  if (ep.cid) params.set("cid", String(ep.cid));
  params.set("high_quality", "1");
  return `https://player.bilibili.com/player.html?${params.toString()}`;
}

function BilibiliPlayer(props) {
  const theme = props.host.getToolContext().theme;
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const results = Array.isArray(d.results) ? d.results : [];
  const selectedId = d.selected_season_id;
  const season =
    results.find((r) => r && r.season_id === selectedId) || results[0] || null;
  const episodes = season && Array.isArray(season.episodes) ? season.episodes : [];
  const current = Number(d.current_episode) || 1;
  const ep = episodes.find((e) => e && e.index === current) || episodes[0];
  const dark = theme === "dark";

  const patch = (next) => {
    if (!props.callId) return;
    props.host.patchResult(props.callId, { ...d, ...next });
  };

  return _jsxs("div", {
    style: cardStyle(theme),
    "data-octop-plugin-ui": "bilibili-anime",
    children: [
      d.error
        ? _jsx("div", { style: { color: "#dc2626" }, children: String(d.error) })
        : null,
      results.length > 1
        ? _jsx("div", {
            style: {
              display: "flex",
              gap: 6,
              flexWrap: "wrap",
              marginBottom: 8,
            },
            children: results.map((item) =>
              _jsx(
                "button",
                {
                  type: "button",
                  onClick: () =>
                    patch({
                      selected_season_id: item.season_id,
                      current_episode: 1,
                    }),
                  style: {
                    border:
                      item.season_id === (season && season.season_id)
                        ? "1px solid #2563eb"
                        : dark
                          ? "1px solid #3f3f46"
                          : "1px solid #d0d5dd",
                    background:
                      item.season_id === (season && season.season_id)
                        ? dark
                          ? "#1e3a8a"
                          : "#dbeafe"
                        : "transparent",
                    color: "inherit",
                    borderRadius: 8,
                    padding: "4px 8px",
                    cursor: "pointer",
                    fontSize: 12,
                  },
                  children: item.title || `ss${item.season_id}`,
                },
                String(item.season_id),
              ),
            ),
          })
        : null,
      season
        ? _jsx("div", {
            style: { fontWeight: 600, marginBottom: 8 },
            children: season.title || "",
          })
        : _jsx("div", {
            children: props.textFallback || "未找到番剧",
          }),
      ep
        ? _jsx("iframe", {
            title: ep.label || "bilibili",
            src: playerUrl(ep),
            allowFullScreen: true,
            sandbox: "allow-scripts allow-same-origin allow-presentation",
            style: {
              width: "100%",
              aspectRatio: "16 / 9",
              border: 0,
              borderRadius: 8,
              background: "#000",
            },
          })
        : null,
      episodes.length
        ? _jsxs("div", {
            style: { marginTop: 8 },
            children: [
              _jsxs("div", {
                style: {
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                  marginBottom: 8,
                },
                children: [
                  _jsx("button", {
                    type: "button",
                    disabled: current <= 1,
                    onClick: () => patch({ current_episode: current - 1 }),
                    children: "上一集",
                  }),
                  _jsx("span", {
                    style: { fontSize: 12, opacity: 0.8 },
                    children: ep ? ep.label : "",
                  }),
                  _jsx("button", {
                    type: "button",
                    disabled: current >= episodes.length,
                    onClick: () => patch({ current_episode: current + 1 }),
                    children: "下一集",
                  }),
                ],
              }),
              _jsx("div", {
                style: {
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(72px, 1fr))",
                  gap: 6,
                  maxHeight: 160,
                  overflow: "auto",
                },
                children: episodes.map((item) =>
                  _jsx(
                    "button",
                    {
                      type: "button",
                      onClick: () => patch({ current_episode: item.index }),
                      style: {
                        fontSize: 12,
                        padding: "4px 6px",
                        borderRadius: 6,
                        cursor: "pointer",
                        border:
                          item.index === current
                            ? "1px solid #2563eb"
                            : dark
                              ? "1px solid #3f3f46"
                              : "1px solid #e5e7eb",
                        background:
                          item.index === current
                            ? dark
                              ? "#1e3a8a"
                              : "#dbeafe"
                            : "transparent",
                        color: "inherit",
                      },
                      children: item.title || item.index,
                    },
                    String(item.index),
                  ),
                ),
              }),
            ],
          })
        : null,
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "bilibili_player",
    tools: ["bilibili_search_anime"],
    component: BilibiliPlayer,
  });
}
