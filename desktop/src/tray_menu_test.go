package main

import "testing"

func TestNewTrayMenuUsesNativeLocalizedItems(t *testing.T) {
	tests := []struct {
		name   string
		locale Locale
		labels []string
	}{
		{name: "English", locale: LocaleEN, labels: []string{"Settings", "Show Octop", "Quit"}},
		{name: "Chinese", locale: LocaleZH, labels: []string{"设置", "显示 Octop", "退出"}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			menu := newTrayMenu(tt.locale, func() {}, func() {}, func() {})
			if got := menu.ItemAt(0).Label(); got != tt.labels[0] {
				t.Fatalf("settings label: got %q, want %q", got, tt.labels[0])
			}
			if got := menu.ItemAt(1).Label(); got != tt.labels[1] {
				t.Fatalf("show-main label: got %q, want %q", got, tt.labels[1])
			}
			if !menu.ItemAt(2).IsSeparator() {
				t.Fatal("third menu item should be a separator")
			}
			if got := menu.ItemAt(3).Label(); got != tt.labels[2] {
				t.Fatalf("quit label: got %q, want %q", got, tt.labels[2])
			}
		})
	}
}

func TestAppRefreshesTrayMenuWhenLocaleChanges(t *testing.T) {
	calls := 0
	settingsLabel := ""
	app := &App{
		setTrayMenuLocale: func(locale Locale) {
			calls++
			menu := newTrayMenu(locale, func() {}, func() {}, func() {})
			settingsLabel = menu.ItemAt(0).Label()
		},
	}

	app.updateTrayMenuLocale(LocaleEN, LocaleZH)

	if calls != 1 {
		t.Fatalf("tray menu rebuild count: got %d, want 1", calls)
	}
	if settingsLabel != "设置" {
		t.Fatalf("settings label after locale change: got %q, want %q", settingsLabel, "设置")
	}
}

func TestAppDoesNotRefreshTrayMenuWhenLocaleIsUnchanged(t *testing.T) {
	calls := 0
	app := &App{
		setTrayMenuLocale: func(Locale) {
			calls++
		},
	}

	app.updateTrayMenuLocale(LocaleEN, LocaleEN)

	if calls != 0 {
		t.Fatalf("tray menu rebuild count: got %d, want 0", calls)
	}
}
