package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestNormalizeLocaleTag(t *testing.T) {
	cases := map[string]Locale{
		"zh":              LocaleZH,
		"zh_CN":           LocaleZH,
		"zh-Hans-CN":      LocaleZH,
		"ZH_TW.UTF-8":     LocaleZH,
		"en_US.UTF-8":     LocaleEN,
		"en-GB":           LocaleEN,
		"fr-FR":           LocaleEN,
		"":                LocaleEN,
		"  zh-Hant-TW   ": LocaleZH,
	}
	for tag, want := range cases {
		if got := normalizeLocaleTag(tag); got != want {
			t.Fatalf("normalizeLocaleTag(%q) = %q, want %q", tag, got, want)
		}
	}
}

func TestFirstLocaleTag(t *testing.T) {
	raw := "(\n    \"zh-Hans-CN\",\n    \"en-US\"\n)"
	if got := firstLocaleTag(raw); got != "zh-Hans-CN" {
		t.Fatalf("firstLocaleTag = %q", got)
	}
	if got := firstLocaleTag("en-US"); got != "" {
		t.Fatalf("unquoted output should not parse: %q", got)
	}
}

func TestDefaultSettingsUseASupportedLocale(t *testing.T) {
	if locale := defaultSettings().Locale; locale != LocaleZH && locale != LocaleEN {
		t.Fatalf("default locale = %q", locale)
	}
}

func TestLoadSettingsLocaleResolution(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	system := systemLocale()

	// No file at all: follow the system language preference.
	if got := loadSettings().Locale; got != system {
		t.Fatalf("missing settings file should follow the system locale: %q", got)
	}

	writeSettingsFile(t, home, `{"locale":"zh"}`)
	if got := loadSettings().Locale; got != LocaleZH {
		t.Fatalf("an explicit choice must win: %q", got)
	}

	writeSettingsFile(t, home, `{"locale":""}`)
	if got := loadSettings().Locale; got != system {
		t.Fatalf("an empty locale should follow the system locale: %q", got)
	}
}

func writeSettingsFile(t *testing.T, home, content string) {
	t.Helper()
	if err := os.WriteFile(
		filepath.Join(home, "desktop-settings.json"),
		[]byte(content),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
}
