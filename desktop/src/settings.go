package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"sync"
)

type Locale string

const (
	LocaleZH Locale = "zh"
	LocaleEN Locale = "en"
)

type ThemeMode string

const (
	ThemeLight ThemeMode = "light"
	ThemeDark  ThemeMode = "dark"
)

// Settings is persisted at ~/.octop/desktop-settings.json
type Settings struct {
	Locale          Locale    `json:"locale"`
	Theme           ThemeMode `json:"theme"`
	Autostart       bool      `json:"autostart"`
	MinimizeToTray  bool      `json:"minimizeToTray"`
	PreventSleepMac bool      `json:"preventSleepMac"`
	Port            int       `json:"port,omitempty"`
}

func defaultSettings() Settings {
	return Settings{
		Locale:          LocaleZH,
		Theme:           ThemeLight,
		Autostart:       false,
		MinimizeToTray:  true,
		PreventSleepMac: false,
		Port:            8088,
	}
}

func octopHome() string {
	if v := os.Getenv("OCTOP_HOME"); v != "" {
		return v
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return ".octop"
	}
	return filepath.Join(home, ".octop")
}

func portableDir() string {
	return filepath.Join(octopHome(), "portable")
}

func settingsPath() string {
	return filepath.Join(octopHome(), "desktop-settings.json")
}

type settingsStore struct {
	mu  sync.Mutex
	cur Settings
}

func loadSettings() Settings {
	s := defaultSettings()
	data, err := os.ReadFile(settingsPath())
	if err != nil {
		return s
	}
	_ = json.Unmarshal(data, &s)
	if s.Port == 0 {
		s.Port = 8088
	}
	if s.Locale != LocaleEN {
		s.Locale = LocaleZH
	}
	if s.Theme != ThemeDark {
		s.Theme = ThemeLight
	}
	return s
}

func (st *settingsStore) get() Settings {
	st.mu.Lock()
	defer st.mu.Unlock()
	return st.cur
}

func (st *settingsStore) save(next Settings) error {
	st.mu.Lock()
	defer st.mu.Unlock()
	if next.Port == 0 {
		next.Port = 8088
	}
	if err := os.MkdirAll(octopHome(), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(next, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(settingsPath(), data, 0o644); err != nil {
		return err
	}
	st.cur = next
	return nil
}

func greenPlat() string {
	osName := runtime.GOOS
	arch := runtime.GOARCH
	switch osName {
	case "darwin":
		osName = "darwin"
	case "windows":
		osName = "windows"
	default:
		osName = "linux"
	}
	switch arch {
	case "arm64":
		arch = "arm64"
	default:
		arch = "amd64"
	}
	return osName + "-" + arch
}
