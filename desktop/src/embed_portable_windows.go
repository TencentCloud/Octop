//go:build windows && production

package main

import _ "embed"

//go:embed bundled/portable.zip
var embeddedPortable []byte
