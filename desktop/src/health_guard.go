package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// devShellMarker only appears in the desktop shell page (dashboard/desktop.html).
// Wails dev proxies whatever answers on the Vite port, so the marker is what
// tells our page apart from another program that grabbed the port.
const devShellMarker = "octop-desktop-shell"

const (
	healthProbeTimeout = 2 * time.Second
	devServerProbeWait = 10 * time.Second
	devServerProbeStep = 250 * time.Millisecond
)

// probeHealth asks the base URL for Octop's liveness payload. status is 0 when
// nothing answered at all.
func probeHealth(base string) (status int, octop bool, err error) {
	client := &http.Client{Timeout: healthProbeTimeout}
	resp, err := client.Get(strings.TrimRight(base, "/") + "/api/health")
	if err != nil {
		return 0, false, err
	}
	defer func() { _ = resp.Body.Close() }()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
	if err != nil {
		return resp.StatusCode, false, err
	}
	return resp.StatusCode, isOctopHealth(body), nil
}

// isOctopHealth matches the payload of src/octop/api/routers/health.py: a JSON
// object with ok=true plus Octop's own keys. Any other program listening on the
// port can answer 200 with JSON of its own, and that must not be mistaken for
// the local runtime.
func isOctopHealth(body []byte) bool {
	var payload map[string]json.RawMessage
	if err := json.Unmarshal(body, &payload); err != nil {
		return false
	}
	raw, found := payload["ok"]
	if !found {
		return false
	}
	var ok bool
	if json.Unmarshal(raw, &ok) != nil || !ok {
		return false
	}
	// started_at is null until Octop finishes starting, so check the keys only.
	_, hasStarted := payload["started_at"]
	_, hasDB := payload["db"]
	return hasStarted && hasDB
}

// portBusy reports whether something else already accepts connections on the
// loopback port the shell wants to serve Octop on.
func portBusy(port int) bool {
	ln, err := net.Listen("tcp4", net.JoinHostPort("127.0.0.1", strconv.Itoa(port)))
	if err != nil {
		return true
	}
	_ = ln.Close()
	return false
}

// verifyShellDevServer fails when the Wails dev server is not serving our shell
// page. Another program holding the Vite port would otherwise render its own UI
// inside the desktop window, and the settings/loading bridge would be gone.
//
// The message is a developer diagnostic printed to the terminal: this path only
// runs under `wails3 dev`, and the page that would show localized copy is the
// stranger's page we are refusing to render.
func verifyShellDevServer(rawURL string) error {
	rawURL = strings.TrimSpace(rawURL)
	if rawURL == "" {
		return nil
	}
	client := &http.Client{Timeout: healthProbeTimeout}
	deadline := time.Now().Add(devServerProbeWait)
	var lastErr error
	for {
		resp, err := client.Get(rawURL)
		if err == nil {
			body, readErr := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
			_ = resp.Body.Close()
			switch {
			case readErr != nil:
				lastErr = readErr
			case strings.Contains(string(body), devShellMarker):
				return nil
			default:
				return fmt.Errorf(
					"desktop dev server %s is not the Octop shell page: another program is using that port. Stop it and run wails3 dev again",
					rawURL,
				)
			}
		} else {
			lastErr = err
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("desktop dev server %s is not reachable: %w", rawURL, lastErr)
		}
		time.Sleep(devServerProbeStep)
	}
}
