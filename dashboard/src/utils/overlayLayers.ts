const CHROME_ID = "octop-chrome";
const STAGE_ID = "octop-stage";

/** Top flex slot. The Windows caption menu is portaled here. */
export function chromeSlot(): HTMLElement {
  const found = document.getElementById(CHROME_ID);
  if (found) return found;
  const chrome = document.createElement("div");
  chrome.id = CHROME_ID;
  const stage = document.getElementById(STAGE_ID);
  if (stage && stage.parentElement === document.body) {
    document.body.insertBefore(chrome, stage);
  } else {
    document.body.insertBefore(chrome, document.body.firstChild);
  }
  return chrome;
}

/**
 * Lower flex slot, under the caption menu. antd popups and toasts mount here
 * so they fill the page and cannot cover the menu.
 */
export function popupLayer(): HTMLElement {
  return document.getElementById(STAGE_ID) ?? document.body;
}
