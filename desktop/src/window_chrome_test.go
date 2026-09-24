package main

import (
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
