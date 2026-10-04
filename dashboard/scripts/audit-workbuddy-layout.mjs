/** Read-only layout observation through the Browser skill's selected tab. */
export async function observeLayout(tab, expectedWidth, expectedHeight) {
  const observation = await tab.playwright.evaluate(() => {
    const visible = (node) => {
      if (node.closest("[hidden]")) return false;
      const r = node.getBoundingClientRect();
      if (!r.width || !r.height) return false;
      for (let p = node; p; p = p.parentElement) {
        const style = getComputedStyle(p);
        if (style.display === "none" || style.visibility === "hidden")
          return false;
      }
      return true;
    };
    const scope =
      [...document.querySelectorAll(".settings-modal__panel")].find(visible) ||
      [...document.querySelectorAll("main")].find(visible) ||
      document.body;
    const bounds = scope.getBoundingClientRect();
    const overflow = [];
    const scrollable = [];
    const unnamed = [];
    for (const node of scope.querySelectorAll(
      "button,input,textarea,[role=tablist],table",
    )) {
      if (!visible(node)) continue;
      const r = node.getBoundingClientRect();
      const label =
        node.getAttribute("aria-label") ||
        node.getAttribute("title") ||
        node.textContent.trim().slice(0, 80);
      if (
        node.tagName === "BUTTON" &&
        !label &&
        !node.querySelector("[aria-label]")
      )
        unnamed.push({
          class: node.className,
          role: node.getAttribute("role"),
        });
      if (r.right <= bounds.right + 2 && r.left >= bounds.left - 2) continue;
      let scrollAncestor = null;
      for (
        let p = node.parentElement;
        p && p !== scope.parentElement;
        p = p.parentElement
      ) {
        if (
          /auto|scroll/.test(getComputedStyle(p).overflowX) &&
          p.scrollWidth > p.clientWidth + 2
        ) {
          scrollAncestor = p;
          break;
        }
      }
      const item = {
        tag: node.tagName,
        label,
        class: node.className,
        width: r.width,
      };
      (scrollAncestor ? scrollable : overflow).push(item);
    }
    return {
      path: location.pathname,
      viewport: [innerWidth, innerHeight],
      rootOverflow: document.documentElement.scrollWidth - innerWidth,
      overflow,
      scrollable,
      unnamed,
      historyCount: document.querySelectorAll(".wb-task-history").length,
      loading: [
        ...scope.querySelectorAll(
          '[class*="PageLoading"],.octop-spin-spinning',
        ),
      ].filter(visible).length,
    };
  });
  if (
    observation.viewport[0] !== expectedWidth ||
    observation.viewport[1] !== expectedHeight
  )
    throw new Error(
      "Viewport belongs to a different tab; do not record misleading evidence",
    );
  return observation;
}
