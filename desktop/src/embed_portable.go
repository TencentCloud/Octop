//go:build !production || darwin

package main

// Development builds look for agentbuddy-<plat>.zip or agentbuddy-portable-<plat>-*.zip
// beside the executable. macOS production copies the zip into Resources as
// agentbuddy-<plat>.zip.
var embeddedPortable []byte
