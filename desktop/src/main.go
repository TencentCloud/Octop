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

//go:embed assets/tray-icon.png
var trayIcon []byte

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

func (a *App) ShowMain() {
	a.showWindow()
}

func (a *App) Quit() {
	a.requestQuit()
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
		a.setStatus("正在连接 Octop…")
		if err := waitHealth(url, 60*time.Second); err != nil {
			a.setStatus(err.Error())
			return
		}
		a.showDashboard(url)
		return
	}
	s := a.store.get()
	a.setStatus("正在检查运行环境…")
	if err := ensurePortable(a.setStatus); err != nil {
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
	a.setStatus("正在启动 Octop 服务…")
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
	a.scheduleDragOverlay()
	s := a.store.get()
	go func() {
		time.Sleep(800 * time.Millisecond)
		a.applyDashboardPrefs(s)
	}()
	a.setStatus("Octop 已就绪")
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

func (a *App) installDragOverlay() {
	if a.window == nil {
		return
	}
	a.window.ExecJS(`(function(){
		if (!document.body || !window._wails || typeof window._wails.invoke !== 'function') return;
		var bar = document.getElementById('octop-window-drag-overlay');
		if (!bar) {
			bar = document.createElement('div');
			bar.id = 'octop-window-drag-overlay';
			bar.setAttribute('aria-hidden', 'true');
			bar.style.cssText = 'position:fixed;top:0;left:0;right:0;height:32px;z-index:2147483647;background:transparent;user-select:none;';
			document.body.appendChild(bar);
		}
		if (bar.dataset.octopDragReady === '1') return;
		bar.dataset.octopDragReady = '1';
		var armed = false, startX = 0, startY = 0;
		bar.addEventListener('mousedown', function(event) {
			if (event.button !== 0) return;
			armed = true;
			startX = event.screenX;
			startY = event.screenY;
		}, true);
		window.addEventListener('mousemove', function(event) {
			if (!armed) return;
			if (Math.abs(event.screenX - startX) + Math.abs(event.screenY - startY) < 4) return;
			armed = false;
			window._wails.invoke('wails:drag');
		}, true);
		window.addEventListener('mouseup', function() { armed = false; }, true);
		bar.addEventListener('dblclick', function(event) {
			event.preventDefault();
			event.stopPropagation();
			armed = false;
			window._wails.invoke('wails:event:emit:desktop:toggle-maximise');
		}, true);
	})();`)
}

func (a *App) scheduleDragOverlay() {
	go func() {
		for range 40 {
			time.Sleep(250 * time.Millisecond)
			a.installDragOverlay()
		}
	}()
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
		Title:                "Octop",
		Width:                1200,
		Height:               800,
		URL:                  "/",
		Frameless:            true,
		AllowSimpleEventEmit: true,
		BackgroundColour:     application.NewRGB(15, 17, 21),
	})
	api.window = win
	app.Event.On("desktop:toggle-maximise", func(_ *application.CustomEvent) {
		win.ToggleMaximise()
	})
	installDragOverlay := func(_ *application.WindowEvent) { api.scheduleDragOverlay() }
	win.OnWindowEvent(events.Mac.WebViewDidFinishNavigation, installDragOverlay)
	win.OnWindowEvent(events.Windows.WebViewNavigationCompleted, installDragOverlay)
	win.OnWindowEvent(events.Linux.WindowLoadFinished, installDragOverlay)
	settingsWin := app.Window.NewWithOptions(application.WebviewWindowOptions{
		Title:            "Octop 设置",
		Width:            400,
		Height:           500,
		URL:              "/?settings=1",
		Hidden:           true,
		Frameless:        true,
		AlwaysOnTop:      true,
		DisableResize:    true,
		BackgroundColour: application.NewRGB(15, 17, 21),
		Windows: application.WindowsWindow{
			HiddenOnTaskbar: true,
		},
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
		e.Cancel()
		settingsWin.Hide()
	})
	settingsWin.OnWindowEvent(events.Common.WindowLostFocus, func(_ *application.WindowEvent) {
		settingsWin.Hide()
	})

	tray := app.SystemTray.New()
	tray.SetIcon(trayIcon)
	tray.SetTooltip("Octop")
	tray.AttachWindow(settingsWin).WindowOffset(6)
	tray.OnClick(func() { api.showWindow() })
	tray.OnRightClick(func() { tray.ShowWindow() })

	api.applyAutostart(store.get().Autostart)
	api.sleep.set(store.get().PreventSleepMac)

	api.scheduleDragOverlay()
	go api.boot()

	if err := app.Run(); err != nil {
		log.Fatal(err)
	}
}
