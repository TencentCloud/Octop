//go:build !darwin && !windows

package main

import (
	"os"
	"strings"
)

// systemLocaleTag reads the POSIX locale environment, e.g. "zh_CN.UTF-8".
func systemLocaleTag() string {
	for _, key := range []string{"LC_ALL", "LC_MESSAGES", "LANG"} {
		value := strings.TrimSpace(os.Getenv(key))
		if value == "" {
			continue
		}
		if tag, _, found := strings.Cut(value, "."); found {
			return tag
		}
		return value
	}
	return ""
}
