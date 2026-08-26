package main

import (
	"context"
	"embed"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"sync"
	"time"

	"github.com/wailsapp/wails/v3/pkg/application"
	"github.com/wailsapp/wails/v3/pkg/events"
)

//go:embed assets/*
var assets embed.FS

// App is the Wails service bound to the shell UI.
type App struct {
	app      *application.App
	window   *application.WebviewWindow
	store    *settingsStore
	sleep    *sleepGuard
	cmd      *exec.Cmd
	mu       sync.Mutex
	quitting bool
}

func (a *App) ServiceName() string { return "desktop" }

func (a *App) ServiceStartup(context.Context, application.ServiceOptions) error { return nil }

func (a *App) ServiceShutdown() error {
	a.sleep.stop()
	a.mu.Lock()
	cmd := a.cmd
	a.cmd = nil
	a.mu.Unlock()
	stopOctop(cmd)
	return nil
}

func (a *App) GetSettings() Settings {
	return a.store.get()
}

func (a *App) Platform() map[string]any {
	return map[string]any{
		"darwin": isDarwin(),
		"plat":   greenPlat(),
		"home":   octopHome(),
	}
}

func (a *App) SaveSettings(next Settings) (Settings, error) {
	cur := a.store.get()
	if err := a.store.save(next); err != nil {
		return cur, err
	}
	saved := a.store.get()
	a.applyAutostart(saved.Autostart)
	a.sleep.set(saved.PreventSleepMac)
	a.applyDashboardPrefs(saved)
	return saved, nil
}

func (a *App) applyAutostart(on bool) {
	if a.app == nil {
		return
	}
	if on {
		_ = a.app.Autostart.Enable()
		return
	}
	_ = a.app.Autostart.Disable()
}

func (a *App) applyDashboardPrefs(s Settings) {
	if a.window == nil {
		return
	}
	pref := "light"
	if s.Theme == ThemeDark {
		pref = "dark"
	}
	js := fmt.Sprintf(
		`(function(){try{localStorage.setItem('octop:ui-locale',%s);var t={};try{t=JSON.parse(localStorage.getItem('theme')||'{}')||{}}catch(e){t={}}t.preference=%s;localStorage.setItem('theme',JSON.stringify(t));}catch(e){}})();`,
		jsonString(string(s.Locale)),
		jsonString(pref),
	)
	a.window.ExecJS(js)
}

func jsonString(s string) string {
	b, _ := json.Marshal(s)
	return string(b)
}

func (a *App) setStatus(msg string) {
	if a.app == nil {
		return
	}
	a.app.Event.Emit("desktop:status", msg)
}

func (a *App) boot() {
	if url := os.Getenv("OCTOP_DESKTOP_URL"); url != "" {
		a.setStatus("connecting " + url)
		if err := waitHealth(url, 60*time.Second); err != nil {
			a.setStatus(err.Error())
			return
		}
		a.showDashboard(url)
		return
	}
	s := a.store.get()
	a.setStatus("preparing portable runtime")
	if err := ensureGreenZip(s.GitHubRepo, a.setStatus); err != nil {
		a.setStatus(err.Error())
		return
	}
	root := portableDir()
	a.mu.Lock()
	stopOctop(a.cmd)
	cmd, err := startOctop(root, s.Port)
	a.cmd = cmd
	a.mu.Unlock()
	if err != nil {
		a.setStatus(err.Error())
		return
	}
	base := dashboardURL(s.Port)
	a.setStatus("waiting for Octop")
	if err := waitHealth(base, 2*time.Minute); err != nil {
		a.setStatus(err.Error())
		return
	}
	a.showDashboard(base)
}

func (a *App) showDashboard(base string) {
	if a.window == nil {
		return
	}
	a.window.SetURL(base)
	s := a.store.get()
	go func() {
		time.Sleep(800 * time.Millisecond)
		a.applyDashboardPrefs(s)
	}()
	a.setStatus("ready")
}

func (a *App) hideToTray() {
	if a.window == nil {
		return
	}
	if a.store.get().MinimizeToTray {
		a.window.Hide()
	}
}

func (a *App) showWindow() {
	if a.window == nil {
		return
	}
	a.window.Show()
	a.window.Focus()
}

func (a *App) requestQuit() {
	a.mu.Lock()
	a.quitting = true
	a.mu.Unlock()
	if a.app != nil {
		a.app.Quit()
	}
}

func main() {
	store := &settingsStore{cur: loadSettings()}
	api := &App{
		store: store,
		sleep: &sleepGuard{},
	}

	app := application.New(application.Options{
		Name:        "Octop",
		Description: "Octop desktop",
		Services: []application.Service{
			application.NewService(api),
		},
		Assets: application.AssetOptions{
			Handler: application.BundledAssetFileServer(assets),
		},
		Windows: application.WindowsOptions{
			DisableQuitOnLastWindowClosed: true,
		},
		Mac: application.MacOptions{
			ApplicationShouldTerminateAfterLastWindowClosed: false,
		},
	})
	api.app = app

	win := app.Window.NewWithOptions(application.WebviewWindowOptions{
		Title:            "Octop",
		Width:            1200,
		Height:           800,
		URL:              "/",
		BackgroundColour: application.NewRGB(15, 17, 21),
	})
	api.window = win

	settingsWin := app.Window.NewWithOptions(application.WebviewWindowOptions{
		Title:            "Octop",
		Width:            560,
		Height:           640,
		URL:              "/",
		Hidden:           true,
		BackgroundColour: application.NewRGB(15, 17, 21),
	})

	win.OnWindowEvent(events.Common.WindowClosing, func(e *application.WindowEvent) {
		api.mu.Lock()
		quit := api.quitting
		api.mu.Unlock()
		if quit {
			return
		}
		e.Cancel()
		api.hideToTray()
	})
	win.OnWindowEvent(events.Common.WindowMinimise, func(_ *application.WindowEvent) {
		api.hideToTray()
	})

	settingsWin.OnWindowEvent(events.Common.WindowClosing, func(e *application.WindowEvent) {
		api.mu.Lock()
		quit := api.quitting
		api.mu.Unlock()
		if quit {
			return
		}
		e.Cancel()
		settingsWin.Hide()
	})

	tray := app.SystemTray.New()
	menu := app.NewMenu()
	menu.Add("Show Octop").OnClick(func(*application.Context) { api.showWindow() })
	menu.Add("Settings").OnClick(func(*application.Context) {
		settingsWin.Show()
		settingsWin.Focus()
	})
	menu.AddSeparator()
	menu.Add("Quit").OnClick(func(*application.Context) { api.requestQuit() })
	tray.SetMenu(menu)
	tray.SetTooltip("Octop")
	tray.OnClick(func() { api.showWindow() })

	api.applyAutostart(store.get().Autostart)
	api.sleep.set(store.get().PreventSleepMac)

	go api.boot()

	if err := app.Run(); err != nil {
		log.Fatal(err)
	}
}
