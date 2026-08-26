package main

import (
	"archive/zip"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestEnsurePortableUsesBundledPackage(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)

	zipPath := filepath.Join(t.TempDir(), "Octop-"+greenPlat()+".zip")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", zipPath)
	writeTestGreenZip(t, zipPath)

	var statuses []string
	err := ensurePortable(func(status string) {
		statuses = append(statuses, status)
	})
	if err != nil {
		t.Fatal(err)
	}
	if !launchReady(portableDir()) {
		t.Fatal("local package was not extracted into the portable directory")
	}
	if len(statuses) == 0 || statuses[0] != "首次启动，正在解压内置运行环境…" {
		t.Fatalf("unexpected statuses: %v", statuses)
	}
	if _, err := os.Stat(zipPath); err != nil {
		t.Fatalf("bundled package should be retained: %v", err)
	}
}

func TestBundledPortableZipRequiresMatchingPackage(t *testing.T) {
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", filepath.Join(t.TempDir(), "missing.zip"))
	if _, err := bundledPortableZip(); err == nil {
		t.Fatal("missing bundled package should fail")
	}
}

func TestLaunchReadyRejectsFlattenedPythonSymlink(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	root := portableDir()
	if err := os.MkdirAll(filepath.Join(root, "runtime", "bin"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "launch.py"), []byte("test"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "runtime", "bin", "python3"), []byte("python3.12"), 0o755); err != nil {
		t.Fatal(err)
	}
	if launchReady(root) {
		t.Fatal("flattened Python symlink must not be treated as a ready runtime")
	}
}

func writeTestGreenZip(t *testing.T, path string) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	w := zip.NewWriter(f)
	files := []string{"Octop-test/launch.py"}
	if runtime.GOOS == "windows" {
		files = append(files, "Octop-test/runtime/python.exe")
	} else {
		files = append(files,
			"Octop-test/runtime/bin/python3",
			"Octop-test/runtime/bin/python3.12",
		)
	}
	for _, name := range files {
		header := &zip.FileHeader{Name: name, Method: zip.Store}
		content := []byte("test executable payload")
		if strings.HasSuffix(name, "/python3") {
			header.SetMode(os.ModeSymlink | 0o755)
			content = []byte("python3.12")
		} else {
			header.SetMode(0o755)
			if strings.HasSuffix(name, "/python3.12") || strings.HasSuffix(name, "/python.exe") {
				content = make([]byte, 2048)
			}
		}
		entry, err := w.CreateHeader(header)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := entry.Write(content); err != nil {
			t.Fatal(err)
		}
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
}
