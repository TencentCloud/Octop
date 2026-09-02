package main

import "runtime"

const (
	settingsWindowWidth  = 400
	settingsWindowHeight = 460
	// Windows DWM frameless decorations shrink the WebView2 client area, which
	// clips the 28px bottom gap used on macOS.
	settingsWindowWindowsExtraHeight = 24
)

func settingsWindowOuterHeight() int {
	if runtime.GOOS == "windows" {
		return settingsWindowHeight + settingsWindowWindowsExtraHeight
	}
	return settingsWindowHeight
}
