//go:build darwin

package main

import (
	"fmt"
	"os/exec"
)

func startSleepInhibitor() (func(), error) {
	cmd := exec.Command("caffeinate", "-dimsu")
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("start macOS sleep inhibitor: %w", err)
	}
	return func() {
		if cmd.Process != nil {
			_ = cmd.Process.Kill()
		}
		_ = cmd.Wait()
	}, nil
}
