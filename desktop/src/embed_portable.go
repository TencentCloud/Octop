//go:build !production || darwin

package main

// Development builds look for wkbuddy-<plat>.zip or wkbuddy-portable-<plat>-*.zip
// beside the executable. macOS production copies the zip into Resources as
// wkbuddy-<plat>.zip.
var embeddedPortable []byte
