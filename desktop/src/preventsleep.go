package main

import (
	"os"
	"os/exec"
	"runtime"
	"sync"
)

type sleepGuard struct {
	mu  sync.Mutex
	cmd *exec.Cmd
}

func (g *sleepGuard) set(enabled bool) {
	if runtime.GOOS != "darwin" {
		return
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	if enabled {
		if g.cmd != nil && g.cmd.Process != nil {
			return
		}
		cmd := exec.Command("caffeinate", "-dimsu")
		if err := cmd.Start(); err != nil {
			return
		}
		g.cmd = cmd
		return
	}
	if g.cmd != nil && g.cmd.Process != nil {
		_ = g.cmd.Process.Kill()
		_, _ = g.cmd.Process.Wait()
	}
	g.cmd = nil
}

func (g *sleepGuard) stop() {
	g.set(false)
}

func isDarwin() bool {
	return runtime.GOOS == "darwin"
}

func mustEnv(cmd *exec.Cmd, extra map[string]string) {
	cmd.Env = os.Environ()
	for k, v := range extra {
		cmd.Env = append(cmd.Env, k+"="+v)
	}
}
