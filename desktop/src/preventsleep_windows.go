//go:build windows

package main

import (
	"fmt"

	"golang.org/x/sys/windows"
)

const (
	esContinuous      = 0x80000000
	esSystemRequired  = 0x00000001
	esDisplayRequired = 0x00000002
)

var setThreadExecutionState = windows.NewLazySystemDLL("kernel32.dll").NewProc("SetThreadExecutionState")

func startSleepInhibitor() (func(), error) {
	result, _, err := setThreadExecutionState.Call(esContinuous | esSystemRequired | esDisplayRequired)
	if result == 0 {
		return nil, fmt.Errorf("prevent sleep on Windows: %w", err)
	}
	return func() {
		_, _, _ = setThreadExecutionState.Call(esContinuous)
	}, nil
}
