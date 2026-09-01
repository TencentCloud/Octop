package main

func desktopText(locale Locale, zh, en string) string {
	if locale == LocaleEN {
		return en
	}
	return zh
}
