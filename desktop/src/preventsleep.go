package main

import "sync"

type sleepGuard struct {
	mu     sync.Mutex
	stopFn func()
}

func (g *sleepGuard) set(enabled bool) error {
	g.mu.Lock()
	defer g.mu.Unlock()

	if enabled {
		if g.stopFn != nil {
			return nil
		}
		stop, err := startSleepInhibitor()
		if err != nil {
			return err
		}
		g.stopFn = stop
		return nil
	}
	if g.stopFn != nil {
		g.stopFn()
		g.stopFn = nil
	}
	return nil
}

func (g *sleepGuard) stop() {
	_ = g.set(false)
}
