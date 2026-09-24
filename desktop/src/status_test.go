package main

import (
	"encoding/json"
	"errors"
	"testing"
)

func TestEmitStatusKeepsTheLastMessageForReplay(t *testing.T) {
	app := &App{}
	app.setStatus(codeStatusConnecting, nil)
	if app.status.Code != codeStatusConnecting || app.status.Level != statusLevelProgress {
		t.Fatalf("status should carry its copy key as the code: %+v", app.status)
	}

	app.setError(codeErrorPortInUse, map[string]any{"port": 8088})
	if app.status.Level != statusLevelError || app.status.Code != codeErrorPortInUse {
		t.Fatalf("error status should carry level and code: %+v", app.status)
	}
	if app.status.Args["port"] != 8088 {
		t.Fatalf("error status should carry its args: %+v", app.status)
	}
}

func TestSetFaultKeepsTheFaultCode(t *testing.T) {
	app := &App{}
	app.setFault(newDesktopFault(codeErrorAppTooOld, map[string]any{
		"currentVersion": "1.0.2",
		"appVersion":     "1.0.1",
	}))
	if app.status.Code != codeErrorAppTooOld || app.status.Level != statusLevelError {
		t.Fatalf("fault should keep its key as code: %+v", app.status)
	}
	if app.status.Args["currentVersion"] != "1.0.2" {
		t.Fatalf("fault should keep its args: %+v", app.status)
	}

	app.setFault(errors.New("portable extract missing launch.py"))
	if app.status.Level != statusLevelError || app.status.Code != codeErrorUnexpected {
		t.Fatalf("plain errors should fall back to a generic code: %+v", app.status)
	}
	if app.status.Args["error"] != "portable extract missing launch.py" {
		t.Fatalf("plain errors should carry their message as an arg: %+v", app.status)
	}
}

func TestReplayStatusWithoutWindowIsSafe(t *testing.T) {
	app := &App{}
	app.replayStatus()
	app.setStatus(codeStatusReady, nil)
	app.replayStatus()
}

// The wire shape of desktop:status is shared with dashboard/src/desktop
// (statusFromEvent), which parses exactly these field names.
func TestDesktopStatusWireShape(t *testing.T) {
	encoded, err := json.Marshal(desktopStatus{
		Code:  codeErrorPortInUse,
		Level: statusLevelError,
		Args:  map[string]any{"port": 8088},
	})
	if err != nil {
		t.Fatal(err)
	}
	want := `{"code":"error.port_in_use","level":"error","args":{"port":8088}}`
	if string(encoded) != want {
		t.Fatalf("payload = %s, want %s", encoded, want)
	}
}
