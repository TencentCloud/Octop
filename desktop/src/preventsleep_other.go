//go:build !darwin && !linux && !windows

package main

import "fmt"

func startSleepInhibitor() (func(), error) {
	return nil, fmt.Errorf("preventing system sleep is not supported on this platform")
}
