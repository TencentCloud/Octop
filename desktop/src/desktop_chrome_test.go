package main

import (
	"runtime"
	"strings"
	"testing"
)

func TestChromeStyleForGOOS(t *testing.T) {
	for _, tc := range []struct {
		goos string
		want string
	}{
		{goos: "darwin", want: "mac"},
		{goos: "windows", want: "windows"},
		{goos: "linux", want: "windows"},
	} {
		if got := chromeStyleForGOOS(tc.goos); got != tc.want {
			t.Fatalf("chromeStyleForGOOS(%q) = %q, want %q", tc.goos, got, tc.want)
		}
	}
}

func TestChromeStyleInjectJSPublishesHostStyle(t *testing.T) {
	js := chromeStyleInjectJS()
	if !strings.Contains(js, "window.__OCTOP_DESKTOP_CHROME__") {
		t.Fatal("inject JS must publish the chrome style global")
	}
	want := chromeStyleForGOOS(runtime.GOOS)
	if !strings.Contains(js, "='"+want+"';") {
		t.Fatalf("inject JS must carry the host style %q: %s", want, js)
	}
}
