//go:build windows

package main

import (
	"io"
	"os/exec"
	"strconv"
	"syscall"

	"golang.org/x/sys/windows"
)

func hideConsole(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{
		HideWindow:    true,
		CreationFlags: windows.CREATE_NO_WINDOW,
	}
}

func configureProcGroup(cmd *exec.Cmd) {
	hideConsole(cmd)
	cmd.Stdout = io.Discard
	cmd.Stderr = io.Discard
}

func killProcessTree(cmd *exec.Cmd) {
	kill := exec.Command("taskkill", "/F", "/T", "/PID", strconv.Itoa(cmd.Process.Pid))
	hideConsole(kill)
	_ = kill.Run()
}
