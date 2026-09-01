package main

import (
	"testing"

	"github.com/wailsapp/wails/v3/pkg/application"
)

type fakeWindow struct {
	shown     bool
	hidden    bool
	focused   bool
	minimised bool
	showCount int
}

func (w *fakeWindow) Hide() application.Window {
	w.hidden = true
	w.shown = false
	return nil
}
func (w *fakeWindow) Show() application.Window {
	w.showCount++
	w.shown = true
	w.hidden = false
	return nil
}
func (w *fakeWindow) Focus()            { w.focused = true }
func (w *fakeWindow) IsMinimised() bool { return w.minimised }
func (w *fakeWindow) UnMinimise()       { w.minimised = false }

func TestRestoreMainAfterDockClickHidesSettingsAndShowsMain(t *testing.T) {
	main := &fakeWindow{}
	settings := &fakeWindow{}

	restoreMainAfterDockClick(main, settings)

	if settings.showCount != 0 || !settings.hidden {
		t.Fatal("dock click must not show the settings window")
	}
	if !main.shown || !main.focused {
		t.Fatal("dock click should restore and focus the main window")
	}
}

func TestRestoreMainAfterDockClickUnminimisesMain(t *testing.T) {
	main := &fakeWindow{minimised: true}
	settings := &fakeWindow{}

	restoreMainAfterDockClick(main, settings)

	if main.minimised {
		t.Fatal("dock click should unminimise the main window")
	}
	if !main.shown {
		t.Fatal("dock click should show the main window")
	}
	if !settings.hidden {
		t.Fatal("dock click must hide settings even when main was minimised")
	}
}

func TestRestoreMainAfterDockClickNilWindows(t *testing.T) {
	restoreMainAfterDockClick(nil, nil)
	restoreMainAfterDockClick(&fakeWindow{}, nil)
	restoreMainAfterDockClick(nil, &fakeWindow{})
}
