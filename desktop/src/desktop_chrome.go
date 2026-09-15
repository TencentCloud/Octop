package main

import "runtime"

// chromeStyleForGOOS maps the host OS to the dashboard's frameless chrome
// style. It is the single source of truth for the running app: the Go shell
// injects the result into the webview and the dashboard prefers it over its
// user-agent fallback (dashboard/src/utils/desktopChrome.ts).
func chromeStyleForGOOS(goos string) string {
	if goos == "darwin" {
		return "mac"
	}
	return "windows"
}

// chromeStyleInjectJS publishes the host chrome style as a window global so
// resolveDesktopChromeStyle can read it without sniffing the user agent.
// The splash (assets/index.html) still bootstraps from the user agent because
// it paints before any Go injection can run; keep its regex in sync with the
// dashboard fallback.
func chromeStyleInjectJS() string {
	return `(function(){window.__OCTOP_DESKTOP_CHROME__='` +
		chromeStyleForGOOS(runtime.GOOS) + `';})();`
}

func (a *App) installChromeStyle() {
	if a.window == nil {
		return
	}
	a.window.ExecJS(chromeStyleInjectJS())
}
