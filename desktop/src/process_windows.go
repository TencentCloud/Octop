//go:build windows

package main

import (
	"os/exec"
	"strconv"
)

func configureProcGroup(cmd *exec.Cmd) {}

func killProcessTree(cmd *exec.Cmd) {
	pid := cmd.Process.Pid
	_ = exec.Command("taskkill", "/F", "/T", "/PID", strconv.Itoa(pid)).Run()
}
