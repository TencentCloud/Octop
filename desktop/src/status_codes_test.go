package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// The shell page renders `desktopShell.<code>` through i18next, so every code
// this binary can emit must have copy in both page bundles.
func TestShellStatusCodesHavePageCopy(t *testing.T) {
	for _, name := range []string{"en.json", "zh.json"} {
		keys := readShellBundleKeys(t, name)
		for _, code := range shellStatusCodes {
			key := "desktopShell." + code
			if _, ok := keys[key]; !ok {
				t.Fatalf("%s has no copy for %s", name, key)
			}
		}
	}
}

func readShellBundleKeys(t *testing.T, name string) map[string]string {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("..", "..", "dashboard", "src", "locales", name))
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	keys := map[string]string{}
	collectBundleKeys("", doc, keys)
	return keys
}

func collectBundleKeys(prefix string, node any, out map[string]string) {
	switch value := node.(type) {
	case map[string]any:
		for key, child := range value {
			next := key
			if prefix != "" {
				next = prefix + "." + key
			}
			collectBundleKeys(next, child, out)
		}
	case string:
		if strings.HasPrefix(prefix, "desktopShell.") {
			out[prefix] = value
		}
	}
}
