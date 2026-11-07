const GUARD_MARKER = 'data-octop-preview-guard="1"';

const GUARD = `<base href="about:srcdoc"><script ${GUARD_MARKER}>document.addEventListener("click",function(e){var n=e.target;while(n&&n.tagName!=="A")n=n.parentElement;if(!n)return;var h=n.getAttribute("href")||"";if(h.charAt(0)!=="#")return;e.preventDefault();var id=h.slice(1);var el=id?(document.getElementById(id)||document.getElementsByName(id)[0]):null;if(el&&el.scrollIntoView)el.scrollIntoView();});</script>`;

/** Keep in-page anchors inside the sandboxed preview document. */
export function isolateHtmlPreview(content: string): string {
  if (content.includes(GUARD_MARKER)) return content;
  const head = content.match(/<head[^>]*>/i);
  if (head && head.index != null) {
    const at = head.index + head[0].length;
    return content.slice(0, at) + GUARD + content.slice(at);
  }
  const html = content.match(/<html[^>]*>/i);
  if (html && html.index != null) {
    const at = html.index + html[0].length;
    return content.slice(0, at) + `<head>${GUARD}</head>` + content.slice(at);
  }
  return `<!DOCTYPE html><html><head>${GUARD}</head><body>${content}</body></html>`;
}
