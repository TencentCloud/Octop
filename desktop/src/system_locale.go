package main

import "strings"

// systemLocale is the shell's default UI language: the OS language preference,
// mapped onto the two locales the shell ships copy for.
func systemLocale() Locale {
	return normalizeLocaleTag(systemLocaleTag())
}

// normalizeLocaleTag maps an OS locale tag ("zh_CN", "zh-Hans-CN", "en-US") to a
// supported shell locale. Anything that is not Chinese falls back to English,
// matching dashboard/src/utils/localePrefs.ts.
func normalizeLocaleTag(tag string) Locale {
	if strings.HasPrefix(strings.ToLower(strings.TrimSpace(tag)), "zh") {
		return LocaleZH
	}
	return LocaleEN
}

// firstLocaleTag pulls the first entry out of `defaults read` list output, e.g.
// `(\n    "zh-Hans-CN",\n    "en-US"\n)`.
func firstLocaleTag(raw string) string {
	start := strings.Index(raw, "\"")
	if start < 0 {
		return ""
	}
	rest := raw[start+1:]
	end := strings.Index(rest, "\"")
	if end < 0 {
		return ""
	}
	return rest[:end]
}
