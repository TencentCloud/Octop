package main

import (
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestResolveDashboardURLReadsConfig(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	t.Setenv("OCTOP_BIND_HOST", "")
	t.Setenv("OCTOP_PORT", "")
	if err := os.WriteFile(
		filepath.Join(home, "config.json"),
		[]byte(`{"bind_host":"0.0.0.0","port":9000}`),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
	if got := resolveDashboardURL(); got != "http://127.0.0.1:9000/" {
		t.Fatalf("dashboard URL = %q", got)
	}
}

func TestResolveDashboardURLUsesSpecificHost(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	t.Setenv("OCTOP_BIND_HOST", "")
	t.Setenv("OCTOP_PORT", "")
	if err := os.WriteFile(
		filepath.Join(home, "config.json"),
		[]byte(`{"bind_host":"10.0.0.8","port":80}`),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
	if got := resolveDashboardURL(); got != "http://10.0.0.8:80/" {
		t.Fatalf("dashboard URL = %q", got)
	}
}

func TestResolveDashboardURLFallsBackToLegacyHost(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	t.Setenv("OCTOP_BIND_HOST", "")
	t.Setenv("OCTOP_PORT", "")
	if err := os.WriteFile(
		filepath.Join(home, "config.json"),
		[]byte(`{"host":"::1","port":8088}`),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
	if got := resolveDashboardURL(); got != "http://[::1]:8088/" {
		t.Fatalf("dashboard URL = %q", got)
	}
}

func TestResolveDashboardURLEnvOverridesFile(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	t.Setenv("OCTOP_BIND_HOST", "0.0.0.0")
	t.Setenv("OCTOP_PORT", "80")
	if err := os.WriteFile(
		filepath.Join(home, "config.json"),
		[]byte(`{"bind_host":"10.0.0.8","port":9000}`),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
	if got := resolveDashboardURL(); got != "http://127.0.0.1:80/" {
		t.Fatalf("dashboard URL = %q", got)
	}
}

func TestResolveDashboardURLDefaultsWhenConfigMissing(t *testing.T) {
	t.Setenv("OCTOP_HOME", t.TempDir())
	t.Setenv("OCTOP_BIND_HOST", "")
	t.Setenv("OCTOP_PORT", "")
	if got := resolveDashboardURL(); got != "http://127.0.0.1:8088/" {
		t.Fatalf("dashboard URL = %q", got)
	}
}

func TestChooseFreePortUsesStartWhenIdle(t *testing.T) {
	got, err := firstFreePort(8088, func(int) (bool, error) { return false, nil })
	if err != nil || got != 8088 {
		t.Fatalf("port = %d, err = %v", got, err)
	}
}

func TestChooseFreePortSkipsBusyPorts(t *testing.T) {
	busy := map[int]bool{8088: true, 8089: true}
	got, err := firstFreePort(8088, func(port int) (bool, error) { return busy[port], nil })
	if err != nil || got != 8090 {
		t.Fatalf("port = %d, err = %v", got, err)
	}
}

func TestChooseFreePortReportsWhenRangeIsExhausted(t *testing.T) {
	_, err := firstFreePort(8088, func(int) (bool, error) { return true, nil })
	var busy noFreePortError
	if err == nil || !errorAs(err, &busy) || busy.From != 8088 || busy.To != 8088+freePortScanLimit-1 {
		t.Fatalf("err = %v", err)
	}
}

func TestChooseFreePortStopsWhenHostCannotBind(t *testing.T) {
	calls := 0
	_, err := firstFreePort(8088, func(int) (bool, error) {
		calls++
		return false, errors.New("cannot assign requested address")
	})
	if err == nil || calls != 1 {
		t.Fatalf("calls = %d, err = %v", calls, err)
	}
	_, err = chooseFreePort("256.0.0.1", 8088)
	var bind cannotBindError
	if !errors.As(err, &bind) || bind.Port != 8088 {
		t.Fatalf("err = %v", err)
	}
}

func TestListenProbeSeesOpenListener(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := ln.Addr().(*net.TCPAddr).Port
	inUse, err := listenProbe("127.0.0.1", port)
	if err != nil || !inUse {
		t.Fatalf("inUse = %v, err = %v", inUse, err)
	}
	_ = ln.Close()
	inUse, err = listenProbe("127.0.0.1", port)
	if err != nil || inUse {
		t.Fatalf("after close inUse = %v, err = %v", inUse, err)
	}
}

func TestOctopAlreadyRunningRecognizesHealth(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/health" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true,"users_loaded":1,"agents_running":0}`))
	}))
	defer srv.Close()
	if !octopAlreadyRunning(srv.URL) {
		t.Fatal("expected a running Octop")
	}
}

func TestOctopAlreadyRunningRejectsOtherServers(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer srv.Close()
	if octopAlreadyRunning(srv.URL) {
		t.Fatal("a generic health payload is not Octop")
	}
	if octopAlreadyRunning(fmt.Sprintf("http://127.0.0.1:%d/", srv.Listener.Addr().(*net.TCPAddr).Port+1)) {
		t.Fatal("nothing listening should not count as Octop")
	}
}

func TestFindRunningDashboardUsesRememberedPort(t *testing.T) {
	t.Setenv("OCTOP_HOME", t.TempDir())
	srv := httptest.NewServer(octopHealthHandler())
	defer srv.Close()
	port := srv.Listener.Addr().(*net.TCPAddr).Port
	if err := writeDesktopPort(port); err != nil {
		t.Fatal(err)
	}
	got := findRunningDashboard("127.0.0.1", 1)
	if got != dashboardURL("127.0.0.1", port) {
		t.Fatalf("dashboard = %q", got)
	}
}

func TestFindRunningDashboardPrefersConfiguredPort(t *testing.T) {
	t.Setenv("OCTOP_HOME", t.TempDir())
	preferred := httptest.NewServer(octopHealthHandler())
	defer preferred.Close()
	other := httptest.NewServer(octopHealthHandler())
	defer other.Close()
	preferredPort := preferred.Listener.Addr().(*net.TCPAddr).Port
	otherPort := other.Listener.Addr().(*net.TCPAddr).Port
	if err := writeDesktopPort(otherPort); err != nil {
		t.Fatal(err)
	}
	got := findRunningDashboard("127.0.0.1", preferredPort)
	if got != dashboardURL("127.0.0.1", preferredPort) {
		t.Fatalf("dashboard = %q", got)
	}
}

func TestFindRunningDashboardIgnoresDeadRememberedPort(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	if err := os.WriteFile(desktopPortPath(), []byte("nope"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, ok := readDesktopPort(); ok {
		t.Fatal("non-numeric port file was accepted")
	}
	if err := writeDesktopPort(1); err != nil {
		t.Fatal(err)
	}
	if got := findRunningDashboard("127.0.0.1", 2); got != "" {
		t.Fatalf("dashboard = %q", got)
	}
}

func octopHealthHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/health" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true,"users_loaded":1,"agents_running":0}`))
	})
}

func errorAs(err error, target *noFreePortError) bool {
	got, ok := err.(noFreePortError)
	if !ok {
		return false
	}
	*target = got
	return true
}
