package main

import (
	"sync/atomic"
	"testing"
	"time"
)

// The loading page reports itself ready and the fallback timer may both fire;
// boot must still run exactly once.
func TestStartBootRunsOnce(t *testing.T) {
	var calls atomic.Int32
	done := make(chan struct{}, 1)
	app := &App{bootFn: func() {
		calls.Add(1)
		done <- struct{}{}
	}}

	app.BootReady()
	app.startBoot()
	app.BootReady()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("boot never ran")
	}
	time.Sleep(50 * time.Millisecond)
	if got := calls.Load(); got != 1 {
		t.Fatalf("boot ran %d times, want 1", got)
	}
}
