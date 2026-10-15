package main

import (
	"strings"
	"testing"
)

func TestValidateOpenURL(t *testing.T) {
	if _, err := validateOpenURL("https://example.com/authorize"); err != nil {
		t.Fatalf("https url should be allowed: %v", err)
	}
	if _, err := validateOpenURL("mailto:user@example.com"); err != nil {
		t.Fatalf("mailto should be allowed: %v", err)
	}
	if _, err := validateOpenURL("about:blank"); err == nil {
		t.Fatal("about:blank must be rejected")
	}
	if _, err := validateOpenURL("javascript:alert(1)"); err == nil {
		t.Fatal("javascript urls must be rejected")
	}
}

func TestParseOpenURLEvent(t *testing.T) {
	raw, ok := parseOpenURLEvent("desktop:open-url:" + "https%3A%2F%2Fexample.com%2Foauth")
	if !ok || raw != "https://example.com/oauth" {
		t.Fatalf("parsed %#v ok=%v", raw, ok)
	}
	if _, ok := parseOpenURLEvent("desktop:minimise"); ok {
		t.Fatal("non open-url events must be ignored")
	}
}

func TestInjectExternalLinksJSOpensNamedWindows(t *testing.T) {
	js := injectExternalLinksJS()
	if strings.Contains(js, `name.toLowerCase() === "_blank"`) {
		t.Fatal("named window.open such as octop-connector-auth must open externally")
	}
	for _, needle := range []string{
		`lower === "_self"`,
		`lower === "_parent"`,
		`lower === "_top"`,
		`if (url && openExternal(url)) return null;`,
		`desktop:open-url:`,
	} {
		if !strings.Contains(js, needle) {
			t.Fatalf("injected JS missing %q", needle)
		}
	}
}
