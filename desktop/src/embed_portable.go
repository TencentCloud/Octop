//go:build !production || darwin

package main

// Development builds look for Octop-<plat>.zip beside the executable. macOS
// production keeps the zip in the signed .app Resources directory.
var embeddedPortable []byte
