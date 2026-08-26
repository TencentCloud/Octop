//go:build !(windows && production)

package main

// Dev / non-Windows builds look for Octop-<plat>.zip beside the executable
// (or under Contents/Resources on macOS). Windows production embeds the zip.
var embeddedPortable []byte
