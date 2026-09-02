package main

import (
	"os"
	"strings"
	"testing"
)

func TestDesktopDragRegionClassMatchesDashboard(t *testing.T) {
	if desktopDragRegionClass != "octop-desktop-drag" {
		t.Fatalf("drag region class is %q, dashboard CSS will not apply", desktopDragRegionClass)
	}
}

func TestDragOverlayJSStartsWailsDragWithoutCapturingOverlay(t *testing.T) {
	js := dragOverlayJS()
	for _, needle := range []string{
		"wails:drag",
		"wails:drag:doubleclick",
		"--wails-draggable",
		"data-octop-no-drag",
		"clientY <= 32",
	} {
		if !strings.Contains(js, needle) {
			t.Fatalf("drag JS missing %q", needle)
		}
	}
	if strings.Contains(js, "octop-window-drag-overlay") {
		t.Fatal("full-width capturing overlay would steal title-bar clicks")
	}
}

func TestSplashHTMLHasFramelessWindowControls(t *testing.T) {
	html, err := os.ReadFile("assets/index.html")
	if err != nil {
		t.Fatal(err)
	}
	body := string(html)
	for _, needle := range []string{
		`id="window-chrome"`,
		`octop-desktop-drag`,
		`data-octop-no-drag`,
		`data-action="toggle-maximise"`,
		`data-action="minimise"`,
		`data-action="close"`,
		`id="mascot"`,
		`id="loading-brand"`,
	} {
		if !strings.Contains(body, needle) {
			t.Fatalf("splash HTML missing %q", needle)
		}
	}
	if !strings.Contains(body, `data-chrome="mac"`) || !strings.Contains(body, `data-chrome="windows"`) {
		t.Fatal("splash HTML must ship both mac and windows caption groups")
	}
}

func TestSplashLoadingCardWrapsProgressAndStatus(t *testing.T) {
	html, err := os.ReadFile("assets/index.html")
	if err != nil {
		t.Fatal(err)
	}
	body := string(html)
	for _, needle := range []string{
		`class="loading-card"`,
		`class="loading-footer"`,
		`class="loading-bar"`,
		`id="status"`,
		`.loading-card {`,
		`border-radius: 14px`,
		`box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06)`,
	} {
		if !strings.Contains(body, needle) {
			t.Fatalf("splash HTML missing %q", needle)
		}
	}
	cardAt := strings.Index(body, `class="loading-card"`)
	footerAt := strings.Index(body, `class="loading-footer"`)
	barAt := strings.Index(body, `class="loading-bar"`)
	statusAt := strings.Index(body, `id="status"`)
	if cardAt < 0 || footerAt < cardAt || barAt < footerAt || statusAt < barAt {
		t.Fatal("progress bar and status must sit at the bottom of the loading card")
	}
	if strings.Contains(body, `class="spinner"`) || strings.Contains(body, `.spinner {`) {
		t.Fatal("splash should use a progress bar, not a circular spinner")
	}
	statusCSS := cssRule(body, ".loading-status")
	if statusCSS == "" {
		t.Fatal("missing .loading-status rule")
	}
	if strings.Contains(statusCSS, "border:") {
		t.Fatal("status text must not have its own bordered box")
	}
}

func cssRule(html, selector string) string {
	start := strings.Index(html, selector+" {")
	if start < 0 {
		return ""
	}
	rest := html[start:]
	end := strings.Index(rest, "}")
	if end < 0 {
		return ""
	}
	return rest[:end+1]
}

func TestSettingsHTMLFitsWithoutScrollbar(t *testing.T) {
	html, err := os.ReadFile("assets/index.html")
	if err != nil {
		t.Fatal(err)
	}
	body := string(html)
	for _, needle := range []string{
		`dataset.mode = "settings"`,
		`html[data-mode="settings"]`,
		`overflow: hidden`,
		`html[data-mode="settings"] .wrap`,
		`html[data-mode="settings"] #title`,
	} {
		if !strings.Contains(body, needle) {
			t.Fatalf("settings HTML missing %q", needle)
		}
	}
	if !strings.Contains(body, `padding: 44px 20px 28px`) {
		t.Fatal("settings wrap must keep a 28px bottom gap, matching the visual side inset")
	}
	wrapRule := cssRule(body, `html[data-mode="settings"] .wrap`)
	if wrapRule == "" {
		t.Fatal("missing settings wrap rule")
	}
	if !strings.Contains(wrapRule, "height: 100%") {
		t.Fatal("settings wrap must fill the window so the 28px bottom gap is not clipped")
	}
	if !strings.Contains(wrapRule, "display: flex") {
		t.Fatal("settings wrap must be a column so action buttons sit above the bottom padding")
	}
	if !strings.Contains(body, `.glyph`) || !strings.Contains(body, `translateY(-0.5px)`) {
		t.Fatal("traffic-light glyphs must be optically centered in the lights")
	}
	if !strings.Contains(body, `html[data-mode="settings"] .window-controls [data-action="minimise"]`) ||
		!strings.Contains(body, `html[data-mode="settings"] .window-controls [data-action="toggle-maximise"]`) {
		t.Fatal("settings popover should show only the close button")
	}
	if !strings.Contains(body, `"HideSettings"`) {
		t.Fatal("settings close must hide the settings window, not the main window")
	}
}

func TestSettingsWindowSizeFitsContent(t *testing.T) {
	if settingsWindowWidth != 400 {
		t.Fatalf("settings width is %d, expected 400", settingsWindowWidth)
	}
	if settingsWindowHeight >= 500 {
		t.Fatalf("settings height %d leaves empty space under the form", settingsWindowHeight)
	}
	if settingsWindowHeight < 456 {
		t.Fatalf("settings height %d clips the bottom padding", settingsWindowHeight)
	}
	if settingsWindowWindowsExtraHeight < 16 {
		t.Fatal("Windows settings window needs extra height so DWM frame does not eat the 28px bottom gap")
	}
	if settingsWindowOuterHeight() < settingsWindowHeight {
		t.Fatal("outer height must be at least the content height")
	}
}
