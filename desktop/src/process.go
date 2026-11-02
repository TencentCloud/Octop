package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const freePortScanLimit = 100

type noFreePortError struct {
	From int
	To   int
}

func (e noFreePortError) Error() string {
	return fmt.Sprintf("no free port from %d to %d", e.From, e.To)
}

type cannotBindError struct {
	Host string
	Port int
	Err  error
}

func (e cannotBindError) Error() string {
	return e.Err.Error()
}

func (e cannotBindError) Unwrap() error { return e.Err }

func mustEnv(cmd *exec.Cmd, extra map[string]string) {
	cmd.Env = overlayEnv(os.Environ(), extra)
}

func overlayEnv(base []string, extra map[string]string) []string {
	out := make([]string, 0, len(base)+len(extra))
	for _, entry := range base {
		key, _, ok := strings.Cut(entry, "=")
		if ok {
			if _, replaced := extra[key]; replaced {
				continue
			}
		}
		out = append(out, entry)
	}
	for key, value := range extra {
		out = append(out, key+"="+value)
	}
	return out
}

func startOctop(root string, port int) (*exec.Cmd, error) {
	py := pythonExe(root)
	launch := filepath.Join(root, "launch.py")
	// Omit --host/--port. `octop run` writes those flags back to config.json.
	// OCTOP_PORT selects the free port for this process and is not saved.
	cmd := exec.Command(py, launch, "run")
	cmd.Dir = root
	mustEnv(cmd, map[string]string{
		"OCTOP_HOME":           octopHome(),
		"OCTOP_GREEN_PACKAGES": filepath.Join(root, "packages"),
		"OCTOP_PORT":           strconv.Itoa(port),
		"PYTHONNOUSERSITE":     "1",
		"PYTHONPATH":           "",
	})
	configureProcGroup(cmd)
	if runtime.GOOS == "linux" {
		// The Linux desktop release has no server terminal; the shell owns status
		// presentation just like the Windows GUI executable.
		cmd.Stdout = io.Discard
		cmd.Stderr = io.Discard
	} else if runtime.GOOS != "windows" {
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
	}
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	return cmd, nil
}

func stopOctop(cmd *exec.Cmd) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	killProcessTree(cmd)
}

const desktopPortFileName = "desktop-port"

func desktopPortPath() string {
	return filepath.Join(octopHome(), desktopPortFileName)
}

func readDesktopPort() (int, bool) {
	data, err := os.ReadFile(desktopPortPath())
	if err != nil {
		return 0, false
	}
	port, err := strconv.Atoi(strings.TrimSpace(string(data)))
	if err != nil || port < 1 || port > 65535 {
		return 0, false
	}
	return port, true
}

func writeDesktopPort(port int) error {
	if port < 1 || port > 65535 {
		return fmt.Errorf("invalid desktop port %d", port)
	}
	return os.WriteFile(desktopPortPath(), []byte(strconv.Itoa(port)), 0o644)
}

func clearDesktopPort() {
	_ = os.Remove(desktopPortPath())
}

// findRunningDashboard returns a live Octop URL. The saved port wins. When that
// port is not Octop, the port this shell last bound (desktop-port) is checked
// so a second launch attaches instead of starting another server.
func findRunningDashboard(host string, preferred int) string {
	preferredURL := dashboardURL(host, preferred)
	if octopAlreadyRunning(preferredURL) {
		return preferredURL
	}
	port, ok := readDesktopPort()
	if !ok || port == preferred {
		return ""
	}
	remembered := dashboardURL(host, port)
	if octopAlreadyRunning(remembered) {
		return remembered
	}
	return ""
}

func resolveDashboardURL() string {
	host, port := resolveListen()
	return dashboardURL(host, port)
}

func resolveListen() (string, int) {
	host := "127.0.0.1"
	port := 8088
	if data, err := os.ReadFile(filepath.Join(octopHome(), "config.json")); err == nil {
		var raw struct {
			BindHost string `json:"bind_host"`
			Host     string `json:"host"`
			Port     *int   `json:"port"`
		}
		if json.Unmarshal(data, &raw) == nil {
			switch {
			case raw.BindHost != "":
				host = raw.BindHost
			case raw.Host != "":
				host = raw.Host
			}
			if raw.Port != nil && *raw.Port > 0 && *raw.Port <= 65535 {
				port = *raw.Port
			}
		}
	}
	if v := strings.TrimSpace(os.Getenv("OCTOP_BIND_HOST")); v != "" {
		host = v
	}
	if v := strings.TrimSpace(os.Getenv("OCTOP_PORT")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed > 0 && parsed <= 65535 {
			port = parsed
		}
	}
	return host, port
}

func chooseFreePort(host string, start int) (int, error) {
	return firstFreePort(start, func(port int) (bool, error) {
		inUse, err := listenProbe(host, port)
		if err != nil {
			return false, cannotBindError{Host: probeHost(host), Port: port, Err: err}
		}
		return inUse, nil
	})
}

func firstFreePort(start int, probe func(int) (bool, error)) (int, error) {
	if start < 1 || start > 65535 {
		start = 8088
	}
	last := start + freePortScanLimit - 1
	if last > 65535 {
		last = 65535
	}
	for port := start; port <= last; port++ {
		inUse, err := probe(port)
		if err != nil {
			return 0, err
		}
		if !inUse {
			return port, nil
		}
	}
	return 0, noFreePortError{From: start, To: last}
}

func listenProbe(host string, port int) (bool, error) {
	ln, err := net.Listen("tcp", net.JoinHostPort(probeHost(host), strconv.Itoa(port)))
	if err == nil {
		_ = ln.Close()
		return false, nil
	}
	if errors.Is(err, syscall.EADDRINUSE) {
		return true, nil
	}
	return false, err
}

func octopAlreadyRunning(base string) bool {
	client := &http.Client{Timeout: 800 * time.Millisecond}
	url := strings.TrimRight(base, "/") + "/api/health"
	resp, err := client.Get(url)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return false
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return false
	}
	var payload struct {
		OK            bool            `json:"ok"`
		UsersLoaded   json.RawMessage `json:"users_loaded"`
		AgentsRunning json.RawMessage `json:"agents_running"`
	}
	if json.Unmarshal(body, &payload) != nil {
		return false
	}
	return payload.OK && len(payload.UsersLoaded) > 0 && len(payload.AgentsRunning) > 0
}

func probeHost(host string) string {
	host = strings.TrimSpace(host)
	host = strings.Trim(host, "[]")
	if host == "" {
		return "127.0.0.1"
	}
	return host
}

func dashboardURL(host string, port int) string {
	switch host {
	case "0.0.0.0", "::", "[::]":
		host = "127.0.0.1"
	}
	if strings.Contains(host, ":") && !strings.HasPrefix(host, "[") {
		host = "[" + host + "]"
	}
	return fmt.Sprintf("http://%s:%d/", host, port)
}
