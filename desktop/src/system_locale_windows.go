//go:build windows

package main

import (
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

var getUserDefaultLocaleName = windows.NewLazySystemDLL("kernel32.dll").NewProc("GetUserDefaultLocaleName")

// systemLocaleTag reads the Windows user locale, e.g. "zh-CN".
func systemLocaleTag() string {
	const localeNameMaxLength = 85
	buf := make([]uint16, localeNameMaxLength)
	written, _, _ := getUserDefaultLocaleName.Call(
		uintptr(unsafe.Pointer(&buf[0])),
		uintptr(len(buf)),
	)
	if written == 0 {
		return ""
	}
	return syscall.UTF16ToString(buf)
}
