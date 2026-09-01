package main

// trayLeftClickShowsSettings reports whether a primary click on the system
// tray / menu-bar extra should open the settings popover.
//
// On macOS the icon lives in the menu bar; a left click is the normal way to
// open that popover. Windows/Linux keep left-click for showing the main
// window and use right-click for settings.
func trayLeftClickShowsSettings(goos string) bool {
	return goos == "darwin"
}
