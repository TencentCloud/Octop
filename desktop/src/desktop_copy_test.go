package main

import "testing"

func TestDesktopTextLooksUpLocaleWithEnglishDefault(t *testing.T) {
	if got := desktopText(LocaleZH, copyStatusReady); got != "Octop 已就绪" {
		t.Fatalf("zh: %s", got)
	}
	if got := desktopText(LocaleEN, copyStatusReady); got != "Octop is ready" {
		t.Fatalf("en: %s", got)
	}
	if got := desktopText(Locale(""), copyStatusReady); got != "Octop is ready" {
		t.Fatalf("unknown locale should fall back to English: %s", got)
	}
	if got := desktopText(LocaleZH, "missing.key"); got != "missing.key" {
		t.Fatalf("unknown key: %s", got)
	}
}

func TestDesktopTextFormatsArgs(t *testing.T) {
	got := desktopText(LocaleEN, copyStatusBackupDatabase, "0.9.32")
	if got != "Desktop update 0.9.32 found. Backing up the database…" {
		t.Fatalf("format: %s", got)
	}

	got = desktopText(LocaleEN, copyErrorAppTooOld, "0.9.33", "0.9.32", "0.9.33")
	want := "Local data version 0.9.33 is newer than this App version 0.9.32. The App version is too old; install version 0.9.33 or later."
	if got != want {
		t.Fatalf("format: %s", got)
	}
}
