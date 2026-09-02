package main

import "testing"

func TestDesktopTextFollowsLocale(t *testing.T) {
	if got := desktopText(LocaleZH, "中文", "English"); got != "中文" {
		t.Fatalf("zh: %s", got)
	}
	if got := desktopText(LocaleEN, "中文", "English"); got != "English" {
		t.Fatalf("en: %s", got)
	}
	if got := desktopText(Locale(""), "中文", "English"); got != "中文" {
		t.Fatalf("fallback: %s", got)
	}
}
