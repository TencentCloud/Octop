package main

import "testing"

func TestDarwinTrayLeftClickShowsSettings(t *testing.T) {
	if !trayLeftClickShowsSettings("darwin") {
		t.Fatal("macOS menu-bar click should open the settings popover")
	}
}

func TestNonDarwinTrayLeftClickDoesNotShowSettings(t *testing.T) {
	for _, goos := range []string{"windows", "linux"} {
		if trayLeftClickShowsSettings(goos) {
			t.Fatalf("%s left-click should restore the main window, not the settings popover", goos)
		}
	}
}
