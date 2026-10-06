package main

import (
	"strings"
	"testing"
)

func TestOctopRunArgsForwardPortOnly(t *testing.T) {
	args := octopRunArgs(8088)
	for _, arg := range args {
		if arg == "--host" {
			t.Fatalf("bind host must come from config.json, got args: %v", args)
		}
	}
	if got := strings.Join(args, " "); got != "run --port 8088" {
		t.Fatalf("unexpected run args: %s", got)
	}
}
