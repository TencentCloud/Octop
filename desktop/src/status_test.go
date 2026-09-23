package main

import "testing"

func TestEmitStatusKeepsTheLastMessageForReplay(t *testing.T) {
	app := &App{}
	app.setStatus("Connecting to Octop…")
	if app.status.Message != "Connecting to Octop…" || app.status.Error {
		t.Fatalf("progress status should be kept as non-error: %+v", app.status)
	}

	app.setError("Port 8088 is already in use")
	if app.status.Message != "Port 8088 is already in use" || !app.status.Error {
		t.Fatalf("error status should be flagged: %+v", app.status)
	}
}

func TestReplayStatusWithoutWindowIsSafe(t *testing.T) {
	app := &App{}
	app.replayStatus()
	app.setStatus("Octop is ready")
	app.replayStatus()
}
