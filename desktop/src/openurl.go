package main

import (
	"fmt"
	"log"
	"net/url"
	"reflect"
	"strings"
	"sync"
	"unsafe"

	"github.com/wailsapp/wails/v3/pkg/application"
)

const openURLEventPrefix = "desktop:open-url:"

func (a *App) OpenExternal(raw string) error {
	sanitized, err := validateOpenURL(raw)
	if err != nil {
		return err
	}
	if a.app == nil {
		return fmt.Errorf("application is not ready")
	}
	return a.app.Browser.OpenURL(sanitized)
}

type openURLEventListener struct {
	open func(string) error
}

func (l *openURLEventListener) DispatchWailsEvent(event *application.CustomEvent) {
	if event == nil || l.open == nil {
		return
	}
	raw, ok := parseOpenURLEvent(event.Name)
	if !ok {
		return
	}
	if err := l.open(raw); err != nil {
		log.Printf("open external url: %v", err)
	}
}

func parseOpenURLEvent(name string) (string, bool) {
	if !strings.HasPrefix(name, openURLEventPrefix) {
		return "", false
	}
	raw, err := url.QueryUnescape(strings.TrimPrefix(name, openURLEventPrefix))
	if err != nil {
		return "", false
	}
	if _, err := validateOpenURL(raw); err != nil {
		return "", false
	}
	return raw, true
}

func attachOpenURLEventListener(app *application.App, open func(string) error) {
	if app == nil || open == nil {
		return
	}
	root := reflect.ValueOf(app).Elem()
	lockField := root.FieldByName("wailsEventListenerLock")
	listField := root.FieldByName("wailsEventListeners")
	if !lockField.IsValid() || !listField.IsValid() {
		log.Printf("open-url: wails event listener field missing")
		return
	}
	lock := reflect.NewAt(lockField.Type(), unsafe.Pointer(lockField.UnsafeAddr())).Interface().(*sync.Mutex)
	lock.Lock()
	defer lock.Unlock()
	list := reflect.NewAt(listField.Type(), unsafe.Pointer(listField.UnsafeAddr())).Elem()
	var listener application.WailsEventListener = &openURLEventListener{open: open}
	list.Set(reflect.Append(list, reflect.ValueOf(listener)))
}

func validateOpenURL(raw string) (string, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" || strings.ContainsRune(raw, 0) {
		return "", fmt.Errorf("url is not allowed")
	}
	parsed, err := url.Parse(raw)
	if err != nil {
		return "", fmt.Errorf("url is not allowed")
	}
	switch strings.ToLower(parsed.Scheme) {
	case "http", "https":
		if parsed.Host == "" {
			return "", fmt.Errorf("url is not allowed")
		}
	case "mailto":
		if parsed.Opaque == "" && strings.Trim(parsed.Path, "/") == "" {
			return "", fmt.Errorf("url is not allowed")
		}
	default:
		return "", fmt.Errorf("url is not allowed")
	}
	return parsed.String(), nil
}

func injectExternalLinksJS() string {
	return `(function(){
	if (!window._wails || typeof window._wails.invoke !== "function") return;
	if (window.__OCTOP_EXTERNAL_LINKS_INSTALLED__) return;
	window.__OCTOP_EXTERNAL_LINKS_INSTALLED__ = true;
	var lastUrl = "", lastAt = 0;
	function isOpenable(url) {
		try {
			var parsed = new URL(String(url || ""), window.location.href);
			var scheme = parsed.protocol.replace(":", "").toLowerCase();
			if (scheme === "mailto") return Boolean(parsed.pathname || parsed.href.slice("mailto:".length));
			return scheme === "http" || scheme === "https";
		} catch (e) { return false; }
	}
	function openExternal(url) {
		if (!isOpenable(url)) return false;
		var now = Date.now();
		if (url === lastUrl && now - lastAt < 800) return true;
		lastUrl = url;
		lastAt = now;
		window._wails.invoke("wails:event:emit:desktop:open-url:" + encodeURIComponent(url));
		return true;
	}
	function linkFromEvent(event) {
		var node = event.target;
		if (node && node.nodeType === 3) node = node.parentNode;
		if (!node || !node.closest) return null;
		var link = node.closest("a[href][target]");
		if (!link || String(link.target).toLowerCase() !== "_blank") return null;
		if (link.hasAttribute("download")) return null;
		return link;
	}
	function onActivate(event) {
		if (event.button != null && event.button !== 0) return;
		var link = linkFromEvent(event);
		if (!link) return;
		if (!openExternal(link.href)) return;
		event.preventDefault();
	}
	document.addEventListener("click", onActivate, true);
	document.addEventListener("pointerdown", onActivate, true);
	var origOpen = window.open;
	window.open = function(url, target) {
		var name = target == null ? "_blank" : String(target);
		if (url && name.toLowerCase() === "_blank" && openExternal(url)) return null;
		return origOpen.apply(this, arguments);
	};
})();`
}

func (a *App) installExternalLinks() {
	if a.window == nil {
		return
	}
	a.window.ExecJS(injectExternalLinksJS())
}
