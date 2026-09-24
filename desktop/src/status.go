package main

import "fmt"

// Status levels the shell page understands. New levels are additive: the page
// renders an unknown level like progress until it learns about it.
const (
	statusLevelProgress = "progress"
	statusLevelError    = "error"
)

// desktopStatus is the desktop:status payload, shared with
// dashboard/src/desktop (ShellApp → LoadingPage).
//
//   - Code is the copy key from status_codes.go, e.g. "error.port_in_use". The
//     page renders `desktopShell.<code>` through i18next, so this side carries
//     no user-facing text of its own.
//   - Level drives the panel state (progress bar vs error panel).
//   - Args are the values the copy interpolates ({"port": 8088}).
type desktopStatus struct {
	Code  string         `json:"code"`
	Level string         `json:"level"`
	Args  map[string]any `json:"args,omitempty"`
}

// desktopFault carries a status code and its args out of the boot helpers, so a
// failure reaches the page as data. Error() is the log/diagnostic form.
type desktopFault struct {
	code  string
	args  map[string]any
	cause error
}

func newDesktopFault(code string, args map[string]any) *desktopFault {
	return &desktopFault{code: code, args: args}
}

func (f *desktopFault) withCause(cause error) *desktopFault {
	f.cause = cause
	return f
}

func (f *desktopFault) Error() string {
	text := f.code
	if len(f.args) > 0 {
		text += fmt.Sprintf(" %v", f.args)
	}
	if f.cause == nil {
		return text
	}
	return text + ": " + f.cause.Error()
}

func (f *desktopFault) Unwrap() error { return f.cause }
