const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function paperMeta(paper) {
  const authors = Array.isArray(paper.authors) ? paper.authors : [];
  const categories = Array.isArray(paper.categories) ? paper.categories : [];
  return [
    authors.slice(0, 5).join(", "),
    categories.join(", "),
    paper.published ? String(paper.published).slice(0, 10) : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function PaperRow({ paper, dark, full }) {
  const summary = String(paper.summary || "");
  const preview =
    full || summary.length <= 420 ? summary : `${summary.slice(0, 420)}…`;
  return _jsxs("article", {
    style: {
      padding: "12px 0",
      borderBottom: dark ? "1px solid #27272a" : "1px solid #e4e4e7",
    },
    children: [
      _jsx("a", {
        href: paper.abs_url || "#",
        target: "_blank",
        rel: "noopener noreferrer",
        style: {
          color: "inherit",
          fontWeight: 750,
          textDecoration: "none",
          lineHeight: 1.35,
        },
        children: paper.title || paper.id || "arXiv 论文",
      }),
      _jsx("div", {
        style: { marginTop: 5, fontSize: 12, opacity: 0.68, lineHeight: 1.45 },
        children: paperMeta(paper),
      }),
      _jsx("p", {
        style: {
          margin: "8px 0 0",
          lineHeight: 1.55,
          fontSize: 13,
          opacity: 0.9,
        },
        children: preview,
      }),
      _jsxs("div", {
        style: {
          display: "flex",
          gap: 12,
          marginTop: 8,
          fontSize: 12,
          fontWeight: 650,
        },
        children: [
          paper.id
            ? _jsx("span", { style: { opacity: 0.75 }, children: paper.id })
            : null,
          paper.pdf_url
            ? _jsx("a", {
                href: paper.pdf_url,
                target: "_blank",
                rel: "noopener noreferrer",
                style: { color: dark ? "#93c5fd" : "#2563eb" },
                children: "PDF",
              })
            : null,
        ],
      }),
    ],
  });
}

function Card({ children, dark, title, subtitle }) {
  return _jsxs("section", {
    style: {
      margin: 0,
      maxWidth: 620,
      overflow: "hidden",
      borderRadius: 18,
      border: dark ? "1px solid #3f3f46" : "1px solid #cbd5e1",
      background: dark ? "#18181b" : "#fff",
      boxShadow: "0 10px 28px rgba(0,0,0,.08)",
    },
    "data-octop-plugin-ui": "arxiv-search",
    children: [
      _jsxs("header", {
        style: {
          padding: "12px 14px",
          fontWeight: 800,
          background: dark
            ? "#27272a"
            : "linear-gradient(135deg,#eff6ff,#e0e7ff)",
        },
        children: [
          title,
          subtitle
            ? _jsx("span", {
                style: { marginLeft: 8, opacity: 0.65, fontSize: 12 },
                children: subtitle,
              })
            : null,
        ],
      }),
      _jsx("div", { style: { padding: "0 14px" }, children }),
    ],
  });
}

function ArxivSearchResults(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const items = Array.isArray(d.items) ? d.items : [];
  if (d.error || d.empty || items.length === 0) return null;
  const total = Number.isFinite(d.total_results)
    ? `共 ${d.total_results} 篇`
    : "";
  return _jsx(Card, {
    dark,
    title: "arXiv 论文",
    subtitle: total,
    children: items.map((paper, index) =>
      _jsx(PaperRow, { paper, dark, full: false }, String(paper.id || index)),
    ),
  });
}

function ArxivPaperCard(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.error || d.empty || !d.paper) return null;
  return _jsx(Card, {
    dark,
    title: "arXiv 论文详情",
    children: _jsx(PaperRow, { paper: d.paper, dark, full: true }),
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "arxiv_search_results",
    tools: ["arxiv_search"],
    component: ArxivSearchResults,
  });
  host.registerRenderer({
    id: "arxiv_paper_card",
    tools: ["arxiv_paper"],
    component: ArxivPaperCard,
  });
}
