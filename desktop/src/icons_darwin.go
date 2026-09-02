//go:build darwin

package main

import (
	_ "embed"

	"github.com/wailsapp/wails/v3/pkg/application"
)

// Wails sizes the menu bar image to the full NSStatusBar thickness (22pt), so
// the icon must carry its own padding and be a monochrome template to sit at
// the same visual weight as system items.
//
//go:embed assets/tray-icon-template.png
var trayTemplateIcon []byte

func applyTrayIcon(tray *application.SystemTray) {
	tray.SetTemplateIcon(trayTemplateIcon)
}

// The bundle's icons.icns already carries the Dock icon with the macOS
// 824/1024 icon-grid padding. Overriding NSApp's icon image would replace it
// with a full-bleed PNG that renders a size bigger than every other app.
func applyAppIcon(_ *application.App) {}
