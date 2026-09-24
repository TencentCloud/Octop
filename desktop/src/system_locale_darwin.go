//go:build darwin

package main

import (
	"os/exec"
	"strings"
)

// systemLocaleTag reads the macOS language preference. AppleLocale carries the
// user's choice ("zh_CN"); AppleLanguages is the ordered preference list and
// covers machines where AppleLocale is unset.
func systemLocaleTag() string {
	if out, err := exec.Command("defaults", "read", "-g", "AppleLocale").Output(); err == nil {
		if tag := strings.TrimSpace(string(out)); tag != "" {
			return tag
		}
	}
	out, err := exec.Command("defaults", "read", "-g", "AppleLanguages").Output()
	if err != nil {
		return ""
	}
	return firstLocaleTag(string(out))
}
