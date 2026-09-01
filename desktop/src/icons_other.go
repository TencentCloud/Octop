//go:build !darwin

package main

import (
	_ "embed"

	"github.com/wailsapp/wails/v3/pkg/application"
)

//go:embed assets/tray-icon.png
var trayIcon []byte

func applyTrayIcon(tray *application.SystemTray) {
	tray.SetIcon(trayIcon)
}

func applyAppIcon(app *application.App) {
	app.SetIcon(trayIcon)
}
