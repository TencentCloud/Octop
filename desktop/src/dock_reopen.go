package main

import "github.com/wailsapp/wails/v3/pkg/application"

// dockRestoreWindow is the subset of a Wails window used when the macOS
// dock icon is clicked. Hide/Show match WebviewWindow's return type.
type dockRestoreWindow interface {
	Hide() application.Window
	Show() application.Window
	Focus()
	IsMinimised() bool
	UnMinimise()
}

// restoreMainAfterDockClick brings back the main window only.
// Wails' default ApplicationShouldHandleReopen handler shows every hidden
// window, which would also pop the tray settings overlay.
func restoreMainAfterDockClick(main, settings dockRestoreWindow) {
	if settings != nil {
		settings.Hide()
	}
	if main == nil {
		return
	}
	if main.IsMinimised() {
		main.UnMinimise()
	}
	main.Show()
	main.Focus()
}
