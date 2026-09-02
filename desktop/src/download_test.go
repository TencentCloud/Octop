package main

import (
	"archive/zip"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestEnsurePortableUsesEmbeddedPackage(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", "")

	zipPath := filepath.Join(t.TempDir(), "embedded.zip")
	writeTestGreenZip(t, zipPath)
	data, err := os.ReadFile(zipPath)
	if err != nil {
		t.Fatal(err)
	}
	prev := embeddedPortable
	embeddedPortable = data
	t.Cleanup(func() { embeddedPortable = prev })

	if err := ensurePortable(LocaleZH, func(string) {}); err != nil {
		t.Fatal(err)
	}
	if !launchReady(portableDir()) {
		t.Fatal("embedded package was not extracted into the portable directory")
	}
}

func TestEnsurePortableUsesBundledPackage(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)

	zipPath := filepath.Join(t.TempDir(), "Octop-"+greenPlat()+".zip")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", zipPath)
	writeTestGreenZip(t, zipPath)

	var statuses []string
	err := ensurePortable(LocaleZH, func(status string) {
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

func TestFormatHealthWaitErrorIsActionableChinese(t *testing.T) {
	err := formatHealthWaitError(LocaleZH, "http://127.0.0.1:8088/", time.Minute, errors.New("connection refused"), 0)
	if err == nil {
		t.Fatal("expected an error")
	}
	msg := err.Error()
	for _, needle := range []string{
		"Octop 服务未在",
		"1 分钟",
		"http://127.0.0.1:8088",
		"请确认",
	} {
		if !strings.Contains(msg, needle) {
			t.Fatalf("friendly health error missing %q: %s", needle, msg)
		}
	}
	if strings.Contains(msg, "/api/health") {
		t.Fatalf("user-facing status should not expose the health path: %s", msg)
	}
	if strings.Contains(msg, "did not become healthy") {
		t.Fatalf("should not use the old English diagnostic: %s", msg)
	}
}

func TestFormatHealthWaitErrorUsesEnglishWhenLocaleIsEn(t *testing.T) {
	msg := formatHealthWaitError(LocaleEN, "http://127.0.0.1:8088", time.Minute, errors.New("connection refused"), 0).Error()
	for _, needle := range []string{
		"Octop did not become ready within",
		"1 minute",
		"http://127.0.0.1:8088",
		"make sure Octop is running",
	} {
		if !strings.Contains(msg, needle) {
			t.Fatalf("English health error missing %q: %s", needle, msg)
		}
	}
	if strings.Contains(msg, "服务未在") || strings.Contains(msg, "请确认") {
		t.Fatalf("English locale should not use Chinese splash copy: %s", msg)
	}
}

func TestFormatHealthWaitErrorUsesServiceNotReadyHintOn5xx(t *testing.T) {
	zh := formatHealthWaitError(LocaleZH, "http://127.0.0.1:8088", 2*time.Minute, nil, 503).Error()
	if !strings.Contains(zh, "2 分钟") || !strings.Contains(zh, "尚未就绪") {
		t.Fatalf("zh 5xx hint: %s", zh)
	}
	en := formatHealthWaitError(LocaleEN, "http://127.0.0.1:8088", 2*time.Minute, nil, 503).Error()
	if !strings.Contains(en, "2 minutes") || !strings.Contains(en, "not ready yet") {
		t.Fatalf("en 5xx hint: %s", en)
	}
}

func TestWaitHealthSucceedsOnOK(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	if err := waitHealth(LocaleZH, srv.URL, time.Second); err != nil {
		t.Fatal(err)
	}
}

func TestWaitHealthTimesOutWithFriendlyMessage(t *testing.T) {
	err := waitHealth(LocaleEN, "http://127.0.0.1:1", 50*time.Millisecond)
	if err == nil {
		t.Fatal("closed port should time out")
	}
	if strings.Contains(err.Error(), "did not become healthy") {
		t.Fatalf("should not use the old English diagnostic: %s", err)
	}
	if !strings.Contains(err.Error(), "Octop did not become ready within") {
		t.Fatalf("timeout should follow the desktop locale: %s", err)
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
