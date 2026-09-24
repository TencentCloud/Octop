package main

import (
	"net"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
)

func TestIsOctopHealth(t *testing.T) {
	cases := []struct {
		name string
		body string
		want bool
	}{
		{"octop payload", `{"ok":true,"started_at":1700000000,"db":true,"users_loaded":1,"agents_running":2}`, true},
		{"starting payload", `{"ok":true,"started_at":null,"db":false}`, true},
		{"plain ok json", `{"ok":true}`, false},
		{"not ok", `{"ok":false,"started_at":1,"db":true}`, false},
		{"html", `<!doctype html><html><body>other app</body></html>`, false},
		{"empty", ``, false},
	}
	for _, tc := range cases {
		if got := isOctopHealth([]byte(tc.body)); got != tc.want {
			t.Fatalf("%s: got %v, want %v", tc.name, got, tc.want)
		}
	}
}

func TestPortBusy(t *testing.T) {
	ln, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = ln.Close() }()
	port := ln.Addr().(*net.TCPAddr).Port
	if !portBusy(port) {
		t.Fatalf("port %s should be reported as busy", strconv.Itoa(port))
	}
	if portBusy(0) {
		t.Fatal("port 0 should be reported as free")
	}
}

func TestVerifyShellDevServerAcceptsShellPage(t *testing.T) {
	shell := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`<html><head><meta name="octop-desktop-shell" content="1" /></head></html>`))
	}))
	t.Cleanup(shell.Close)
	if err := verifyShellDevServer(shell.URL); err != nil {
		t.Fatal(err)
	}
}

func TestVerifyShellDevServerRejectsForeignPage(t *testing.T) {
	foreign := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`<!doctype html><html><body>some other app</body></html>`))
	}))
	t.Cleanup(foreign.Close)
	err := verifyShellDevServer(foreign.URL)
	if err == nil {
		t.Fatal("a foreign dev server must not be rendered")
	}
	if !strings.Contains(err.Error(), "not the Octop shell") {
		t.Fatalf("unexpected message: %v", err)
	}
}

func TestVerifyShellDevServerIgnoresUnsetURL(t *testing.T) {
	if err := verifyShellDevServer("  "); err != nil {
		t.Fatal(err)
	}
}
