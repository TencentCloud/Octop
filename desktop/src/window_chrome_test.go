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
