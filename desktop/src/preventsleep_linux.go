//go:build linux

package main

import (
	"fmt"
	"os"

	"github.com/godbus/dbus/v5"
)

func startSleepInhibitor() (func(), error) {
	conn, err := dbus.SystemBus()
	if err != nil {
		return nil, fmt.Errorf("connect to system D-Bus: %w", err)
	}
	call := conn.Object("org.freedesktop.login1", "/org/freedesktop/login1").Call(
		"org.freedesktop.login1.Manager.Inhibit",
		0,
		"idle:sleep",
		"Octop",
		"Octop desktop is running",
		"block",
	)
	if call.Err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("inhibit sleep through logind: %w", call.Err)
	}
	if len(call.Body) != 1 {
		_ = conn.Close()
		return nil, fmt.Errorf("inhibit sleep through logind: missing file descriptor")
	}
	fd, ok := call.Body[0].(dbus.UnixFD)
	if !ok {
		_ = conn.Close()
		return nil, fmt.Errorf("inhibit sleep through logind: invalid file descriptor")
	}
	file := os.NewFile(uintptr(fd), "octop-sleep-inhibitor")
	if file == nil {
		_ = conn.Close()
		return nil, fmt.Errorf("inhibit sleep through logind: open file descriptor")
	}
	return func() {
		_ = file.Close()
		_ = conn.Close()
	}, nil
}
