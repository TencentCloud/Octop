package main

import "github.com/wailsapp/wails/v3/pkg/application"

func newTrayMenu(locale Locale, showSettings, showMain, quit func()) *application.Menu {
	menu := application.NewMenu()
	menu.Add(desktopText(locale, copyTraySettings)).OnClick(func(_ *application.Context) {
		showSettings()
	})
	menu.Add(desktopText(locale, copyTrayShowMain)).OnClick(func(_ *application.Context) {
		showMain()
	})
	menu.AddSeparator()
	menu.Add(desktopText(locale, copyTrayQuit)).OnClick(func(_ *application.Context) {
		quit()
	})
	return menu
}
