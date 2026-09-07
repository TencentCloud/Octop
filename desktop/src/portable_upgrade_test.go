package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestPortableVersionPrefersNewestPackageMetadata(t *testing.T) {
	root := t.TempDir()
	for versionIndex, version := range []string{"0.9.29", "0.9.32"} {
		path := filepath.Join(
			root,
			"packages",
			"octop-"+version+".dist-info",
			"METADATA",
		)
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte("Version: "+version+"\n"), 0o644); err != nil {
			t.Fatal(err)
		}
		if versionIndex == 0 {
			if err := os.WriteFile(filepath.Join(root, "VERSION.txt"), []byte("octop_version=0.9.28\n"), 0o644); err != nil {
				t.Fatal(err)
			}
		}
	}

	if got := portableVersion(root); got != "0.9.32" {
		t.Fatalf("portable version = %q, want 0.9.32", got)
	}
}

func TestDesktopSQLitePathUsesConfiguredRelativePath(t *testing.T) {
	home := t.TempDir()
	config := `{"database":{"driver":"sqlite","sqlite_path":"state/control.db"}}`
	if err := os.WriteFile(filepath.Join(home, "config.json"), []byte(config), 0o600); err != nil {
		t.Fatal(err)
	}

	path, isSQLite, err := desktopSQLitePath(home)
	if err != nil {
		t.Fatal(err)
	}
	if !isSQLite {
		t.Fatal("configured SQLite database was not detected")
	}
	want := filepath.Join(home, "state", "control.db")
	if path != want {
		t.Fatalf("SQLite path = %q, want %q", path, want)
	}
}

func TestDesktopSQLitePathSkipsPostgreSQL(t *testing.T) {
	home := t.TempDir()
	config := `{"database":{"driver":"postgresql"}}`
	if err := os.WriteFile(filepath.Join(home, "config.json"), []byte(config), 0o600); err != nil {
		t.Fatal(err)
	}

	path, isSQLite, err := desktopSQLitePath(home)
	if err != nil {
		t.Fatal(err)
	}
	if isSQLite || path != "" {
		t.Fatalf("PostgreSQL resolved as SQLite: path=%q isSQLite=%v", path, isSQLite)
	}
}
