package main

import (
	"runtime"
	"testing"
	"time"
)

func TestWindowReadyWaitsBeforeNavigation(t *testing.T) {
	app := &App{webviewReady: make(chan struct{})}
	done := make(chan struct{})
	go func() {
		app.waitWebviewReady()
		close(done)
	}()

	if runtime.GOOS == "windows" {
		select {
		case <-done:
			t.Fatal("navigation proceeded before the window was ready")
		case <-time.After(50 * time.Millisecond):
		}
	}

	app.markWebviewReady()
	app.markWebviewReady() // Later navigations emit the same event again.
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("navigation did not resume after the window became ready")
	}
}
