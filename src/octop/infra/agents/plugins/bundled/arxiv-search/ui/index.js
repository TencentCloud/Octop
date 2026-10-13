const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function ArxivSearch(props) {
  const context = props.host.getToolContext();
  const dark = context.theme === "dark";
  const zh = context.locale.toLowerCase().startsWith("zh");
  const labels = zh
    ? {
        title: "arXiv 论文",
        results: "篇结果",
        abstract: "摘要",
        pdf: "阅读 PDF",
        source: "来源鸣谢",
      }
    : {
        title: "arXiv papers",
        results: "results",
        abstract: "Abstract",
        pdf: "Read PDF",
        source: "Source acknowledgement",
      };
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const items = Array.isArray(d.items) ? d.items : [];
  const linkStyle = {
    color: dark ? "#fca5a5" : "#b31b1b",
    textDecoration: "none",
  };
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 560,
      borderRadius: 18,
      overflow: "hidden",
      background: dark ? "#18181b" : "#fff",
      border: dark ? "1px solid #3f3f46" : "1px solid #e4e4e7",
    },
    "data-octop-plugin-ui": "arxiv-search",
    children: [
      _jsxs("div", {
        style: {
          padding: "12px 14px",
          background: dark ? "#27272a" : "#fff1f2",
        },
        children: [
          _jsx("div", { style: { fontWeight: 800 }, children: labels.title }),
          d.query
            ? _jsx("div", {
                style: { marginTop: 4, fontSize: 13, overflowWrap: "anywhere" },
                children: d.query,
              })
            : null,
          !d.error && items.length > 0
            ? _jsxs("div", {
                style: { marginTop: 4, fontSize: 12, opacity: 0.7 },
                children: [d.total ?? items.length, " ", labels.results],
              })
            : null,
        ],
      }),
      d.error || items.length === 0
        ? _jsx("p", {
            style: { margin: 0, padding: 14, fontSize: 14, lineHeight: 1.55 },
            children: props.textFallback || "",
          })
        : _jsx("ol", {
            start: (d.start || 0) + 1,
            style: { margin: 0, padding: "0 14px", listStyle: "none" },
            children: items.map((row, i) =>
              _jsxs(
                "li",
                {
                  style: {
                    padding: "14px 0",
                    borderBottom: dark
                      ? "1px solid #27272a"
                      : "1px solid #f4f4f5",
                  },
                  children: [
                    _jsx("a", {
                      href: row.url,
                      target: "_blank",
                      rel: "noopener noreferrer",
                      style: {
                        ...linkStyle,
                        fontSize: 15,
                        fontWeight: 700,
                        lineHeight: 1.5,
                        overflowWrap: "anywhere",
                      },
                      children: row.title,
                    }),
                    _jsx("div", {
                      style: {
                        marginTop: 6,
                        fontSize: 12,
                        lineHeight: 1.5,
                        opacity: 0.8,
                      },
                      children: Array.isArray(row.authors)
                        ? row.authors.join(", ")
                        : "",
                    }),
                    _jsx("div", {
                      style: { marginTop: 4, fontSize: 11, opacity: 0.65 },
                      children: [
                        row.id,
                        Array.isArray(row.categories)
                          ? row.categories.join(", ")
                          : row.primary_category,
                      ]
                        .filter(Boolean)
                        .join(" · "),
                    }),
                    row.summary
                      ? _jsxs("details", {
                          style: {
                            marginTop: 8,
                            fontSize: 13,
                            lineHeight: 1.55,
                          },
                          children: [
                            _jsx("summary", {
                              style: { cursor: "pointer" },
                              children: labels.abstract,
                            }),
                            _jsx("p", {
                              style: {
                                margin: "8px 0 0",
                                whiteSpace: "pre-wrap",
                                overflowWrap: "anywhere",
                              },
                              children: row.summary,
                            }),
                          ],
                        })
                      : null,
                    row.pdf_url
                      ? _jsx("a", {
                          href: row.pdf_url,
                          target: "_blank",
                          rel: "noopener noreferrer",
                          style: {
                            ...linkStyle,
                            display: "inline-block",
                            marginTop: 8,
                            fontSize: 12,
                          },
                          children: labels.pdf,
                        })
                      : null,
                  ],
                },
                row.id || String(i),
              ),
            ),
          }),
      _jsxs("details", {
        style: {
          padding: "10px 14px",
          fontSize: 11,
          lineHeight: 1.55,
          opacity: 0.7,
        },
        children: [
          _jsx("summary", {
            style: { cursor: "pointer" },
            children: labels.source,
          }),
          _jsx("a", {
            href: "https://arxiv.org",
            target: "_blank",
            rel: "noopener noreferrer",
            style: linkStyle,
            children: "arXiv.org",
          }),
          _jsx("p", {
            lang: "en",
            style: { margin: "6px 0 0" },
            children:
              "Thank you to arXiv for use of its open access interoperability. This service was not reviewed or approved by, nor does it necessarily express or reflect the policies or opinions of, arXiv.",
          }),
        ],
      }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "arxiv_search_list",
    tools: ["search_arxiv"],
    component: ArxivSearch,
  });
}
