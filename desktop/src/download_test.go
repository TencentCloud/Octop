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
	writeTestGreenZip(t, zipPath, "1.0.0")
	data, err := os.ReadFile(zipPath)
	if err != nil {
		t.Fatal(err)
	}
	prev := embeddedPortable
	embeddedPortable = data
	t.Cleanup(func() { embeddedPortable = prev })

	if err := ensurePortable(func(string, map[string]any) {}); err != nil {
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
	writeTestGreenZip(t, zipPath, "1.0.0")

	var statuses []string
	err := ensurePortable(func(key string, _ map[string]any) {
		statuses = append(statuses, key)
	})
	if err != nil {
		t.Fatal(err)
	}
	if !launchReady(portableDir()) {
		t.Fatal("local package was not extracted into the portable directory")
	}
	if len(statuses) == 0 || statuses[0] != codeStatusFirstExtract {
		t.Fatalf("unexpected statuses: %v", statuses)
	}
	if _, err := os.Stat(zipPath); err != nil {
		t.Fatalf("bundled package should be retained: %v", err)
	}
}

func TestEnsurePortableReplacesOlderRuntime(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	root := portableDir()

	oldZip := filepath.Join(t.TempDir(), "old.zip")
	writeTestGreenZip(t, oldZip, "0.9.31")
	if err := unzipGreen(oldZip, root); err != nil {
		t.Fatal(err)
	}
	stale := filepath.Join(root, "stale.txt")
	if err := os.WriteFile(stale, []byte("old"), 0o644); err != nil {
		t.Fatal(err)
	}

	newZip := filepath.Join(t.TempDir(), "new.zip")
	writeTestGreenZip(t, newZip, "0.9.32")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", newZip)
	var statuses []string
	if err := ensurePortable(func(key string, _ map[string]any) { statuses = append(statuses, key) }); err != nil {
		t.Fatal(err)
	}

	if got := portableVersion(root); got != "0.9.32" {
		t.Fatalf("portable version = %q, want 0.9.32", got)
	}
	if _, err := os.Stat(stale); !os.IsNotExist(err) {
		t.Fatalf("old runtime was not replaced: %v", err)
	}
	if len(statuses) < 2 ||
		statuses[0] != codeStatusBackupDatabase ||
		statuses[1] != codeStatusUpdatingRuntime {
		t.Fatalf("unexpected statuses: %v", statuses)
	}
}

func TestEnsurePortableUpgradesBundledVersionAfterDatabaseBackup(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	root := portableDir()

	oldZip := filepath.Join(t.TempDir(), "old.zip")
	writeTestGreenZip(t, oldZip, "0.9.29")
	if err := unzipGreen(oldZip, root); err != nil {
		t.Fatal(err)
	}
	database := filepath.Join(home, "octop.db")
	if err := os.WriteFile(database, []byte("database"), 0o600); err != nil {
		t.Fatal(err)
	}

	newZip := filepath.Join(t.TempDir(), "new.zip")
	writeTestGreenZip(t, newZip, "0.9.32")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", newZip)

	previousBackup := runSQLiteBackup
	runSQLiteBackup = func(_ string, source string, destination string) error {
		if source != database {
			t.Fatalf("backup source = %q, want %q", source, database)
		}
		return os.WriteFile(destination, []byte("backup"), 0o600)
	}
	t.Cleanup(func() { runSQLiteBackup = previousBackup })

	if err := ensurePortable(func(string, map[string]any) {}); err != nil {
		t.Fatal(err)
	}
	if got := portableVersion(root); got != "0.9.32" {
		t.Fatalf("portable version = %q, want 0.9.32", got)
	}
	backups, err := filepath.Glob(filepath.Join(home, "backups", "octop-desktop-pre-upgrade-*.db"))
	if err != nil || len(backups) != 1 {
		t.Fatalf("upgrade backup = %v, err = %v", backups, err)
	}
}

func TestEnsurePortableKeepsRuntimeWhenDatabaseBackupFails(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	root := portableDir()

	oldZip := filepath.Join(t.TempDir(), "old.zip")
	writeTestGreenZip(t, oldZip, "0.9.29")
	if err := unzipGreen(oldZip, root); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(home, "octop.db"), []byte("database"), 0o600); err != nil {
		t.Fatal(err)
	}
	newZip := filepath.Join(t.TempDir(), "new.zip")
	writeTestGreenZip(t, newZip, "0.9.32")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", newZip)

	previousBackup := runSQLiteBackup
	runSQLiteBackup = func(_, _, _ string) error { return errors.New("backup unavailable") }
	t.Cleanup(func() { runSQLiteBackup = previousBackup })

	if err := ensurePortable(func(string, map[string]any) {}); err == nil {
		t.Fatal("backup failure should abort the runtime upgrade")
	}
	if got := portableVersion(root); got != "0.9.29" {
		t.Fatalf("portable version = %q, want preserved 0.9.29", got)
	}
}

func TestEnsurePortableRejectsAppOlderThanLocalData(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	root := portableDir()

	newZip := filepath.Join(t.TempDir(), "new.zip")
	writeTestGreenZip(t, newZip, "0.9.33")
	if err := unzipGreen(newZip, root); err != nil {
		t.Fatal(err)
	}
	sentinel := filepath.Join(root, "keep.txt")
	if err := os.WriteFile(sentinel, []byte("keep"), 0o644); err != nil {
		t.Fatal(err)
	}

	oldZip := filepath.Join(t.TempDir(), "old.zip")
	writeTestGreenZip(t, oldZip, "0.9.32")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", oldZip)
	err := ensurePortable(func(string, map[string]any) {})
	if err == nil {
		t.Fatal("older App should be rejected")
	}
	fault, ok := err.(*desktopFault)
	if !ok {
		t.Fatalf("error should carry a status code: %v", err)
	}
	if fault.code != codeErrorAppTooOld {
		t.Fatalf("code = %q", fault.code)
	}
	if fault.args["currentVersion"] != "0.9.33" ||
		fault.args["appVersion"] != "0.9.32" ||
		fault.args["requiredVersion"] != "0.9.33" {
		t.Fatalf("args = %v", fault.args)
	}

	if got := portableVersion(root); got != "0.9.33" {
		t.Fatalf("portable version = %q, want 0.9.33", got)
	}
	if _, err := os.Stat(sentinel); err != nil {
		t.Fatalf("newer runtime was unexpectedly replaced: %v", err)
	}
}

func TestEnsurePortableComparesPackageMetadataNotVersionTxt(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	root := portableDir()

	oldZip := filepath.Join(t.TempDir(), "old.zip")
	writeTestGreenZip(t, oldZip, "0.9.31")
	if err := unzipGreen(oldZip, root); err != nil {
		t.Fatal(err)
	}
	newerMeta := filepath.Join(root, "packages", "octop-0.9.33.dist-info", "METADATA")
	if err := os.MkdirAll(filepath.Dir(newerMeta), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(newerMeta, []byte("Name: octop\nVersion: 0.9.33\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	newZip := filepath.Join(t.TempDir(), "new.zip")
	writeTestGreenZip(t, newZip, "0.9.32")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", newZip)
	err := ensurePortable(func(string, map[string]any) {})
	if err == nil {
		t.Fatal("older App should be rejected based on METADATA")
	}
	fault, ok := err.(*desktopFault)
	if !ok {
		t.Fatalf("error should carry a status code: %v", err)
	}
	if fault.code != codeErrorAppTooOld {
		t.Fatalf("code = %q", fault.code)
	}
	if fault.args["currentVersion"] != "0.9.33" ||
		fault.args["appVersion"] != "0.9.32" ||
		fault.args["requiredVersion"] != "0.9.33" {
		t.Fatalf("args = %v", fault.args)
	}
	if got := installedPackageVersion(root); got != "0.9.33" {
		t.Fatalf("METADATA version = %q, want 0.9.33", got)
	}
}

func TestEnsurePortableKeepsCurrentRuntimeWhenReplacementIsInvalid(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	root := portableDir()

	currentZip := filepath.Join(t.TempDir(), "current.zip")
	writeTestGreenZip(t, currentZip, "0.9.31")
	if err := unzipGreen(currentZip, root); err != nil {
		t.Fatal(err)
	}

	invalidZip := filepath.Join(t.TempDir(), "invalid.zip")
	writeMetadataOnlyZip(t, invalidZip, "0.9.32")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", invalidZip)
	var statuses []string
	if err := ensurePortable(func(key string, _ map[string]any) { statuses = append(statuses, key) }); err != nil {
		t.Fatalf("existing runtime should still boot after a failed replacement: %v", err)
	}

	if !launchReady(root) {
		t.Fatal("current runtime should remain usable after replacement failure")
	}
	if got := portableVersion(root); got != "0.9.31" {
		t.Fatalf("portable version = %q, want 0.9.31", got)
	}
	if len(statuses) == 0 || statuses[len(statuses)-1] != codeStatusUpdateFailedKeep {
		t.Fatalf("unexpected statuses: %v", statuses)
	}
}

func TestEnsurePortableReplacesLegacyRuntimeWithoutVersionFiles(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	root := portableDir()

	oldZip := filepath.Join(t.TempDir(), "old.zip")
	writeTestGreenZip(t, oldZip, "0.9.31")
	if err := unzipGreen(oldZip, root); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(filepath.Join(root, "VERSION.txt")); err != nil {
		t.Fatal(err)
	}
	if err := os.RemoveAll(filepath.Join(root, "packages")); err != nil {
		t.Fatal(err)
	}

	newZip := filepath.Join(t.TempDir(), "new.zip")
	writeTestGreenZip(t, newZip, "0.9.32")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", newZip)
	if err := ensurePortable(func(string, map[string]any) {}); err != nil {
		t.Fatal(err)
	}
	if got := portableVersion(root); got != "0.9.32" {
		t.Fatalf("portable version = %q, want 0.9.32", got)
	}
}

func TestBundledPortableVersionReadsMetadata(t *testing.T) {
	zipPath := filepath.Join(t.TempDir(), "meta-only.zip")
	writeMetadataOnlyZip(t, zipPath, "0.9.32")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", zipPath)
	got, err := bundledPortableVersion()
	if err != nil {
		t.Fatal(err)
	}
	if got != "0.9.32" {
		t.Fatalf("bundled version = %q, want 0.9.32", got)
	}
}

func TestCompareVersions(t *testing.T) {
	for _, test := range []struct {
		left, right string
		want        int
	}{
		{"0.9.32", "0.9.31", 1},
		{"0.9.32", "0.9.32", 0},
		{"0.9.31", "0.9.32", -1},
		{"1.0", "1.0.0", 0},
		{"0.9.32rc1", "0.9.31", 1},
	} {
		if got := compareVersions(test.left, test.right); got != test.want {
			t.Fatalf("compareVersions(%q, %q) = %d, want %d", test.left, test.right, got, test.want)
		}
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

// The shell renders health copy from these codes; the page-side wording is
// covered by dashboard/src/desktop tests.
func TestFormatHealthWaitErrorCarriesCodeAndArgs(t *testing.T) {
	refused := faultFromError(
		t,
		formatHealthWaitError("http://127.0.0.1:8088/", time.Minute, errors.New("connection refused"), 0),
	)
	if refused.code != codeHealthNotReadyConnect {
		t.Fatalf("code = %q", refused.code)
	}
	if refused.args["addr"] != "http://127.0.0.1:8088" || refused.args["seconds"] != 60 {
		t.Fatalf("args = %v", refused.args)
	}

	starting := faultFromError(
		t,
		formatHealthWaitError("http://127.0.0.1:8088", 2*time.Minute, nil, 503),
	)
	if starting.code != codeHealthNotReady5xx || starting.args["seconds"] != 120 {
		t.Fatalf("5xx fault = %+v", starting)
	}

	generic := faultFromError(
		t,
		formatHealthWaitError("http://127.0.0.1:8088", time.Minute, nil, 200),
	)
	if generic.code != codeHealthNotReady {
		t.Fatalf("generic fault = %+v", generic)
	}
	if strings.Contains(generic.Error(), "/api/health") {
		t.Fatalf("diagnostic should not expose the health path: %s", generic.Error())
	}
}

func TestWaitHealthSucceedsOnOK(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"ok":true,"started_at":1700000000,"db":true}`))
	}))
	t.Cleanup(srv.Close)
	if err := waitHealth(srv.URL, time.Second); err != nil {
		t.Fatal(err)
	}
}

func TestWaitHealthRejectsForeignServerOnThePort(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`<!doctype html><html><body>some other app</body></html>`))
	}))
	t.Cleanup(srv.Close)
	start := time.Now()
	err := waitHealth(srv.URL, 30*time.Second)
	if err == nil {
		t.Fatal("a foreign server must not be treated as Octop")
	}
	if elapsed := time.Since(start); elapsed > 5*time.Second {
		t.Fatalf("should fail fast instead of waiting for the timeout: %s", elapsed)
	}
	fault := faultFromError(t, err)
	if fault.code != codeErrorForeignService || fault.args["addr"] != srv.URL {
		t.Fatalf("fault = %+v", fault)
	}
}

func TestWaitHealthTimesOutWithFriendlyMessage(t *testing.T) {
	err := waitHealth("http://127.0.0.1:1", 50*time.Millisecond)
	if err == nil {
		t.Fatal("closed port should time out")
	}
	fault := faultFromError(t, err)
	if fault.code != codeHealthNotReadyConnect {
		t.Fatalf("timeout should report the connect hint: %+v", fault)
	}
	if fault.args["addr"] != "http://127.0.0.1:1" || fault.args["seconds"] != 1 {
		t.Fatalf("args = %v", fault.args)
	}
}

func faultFromError(t *testing.T, err error) *desktopFault {
	t.Helper()
	var fault *desktopFault
	if !errors.As(err, &fault) {
		t.Fatalf("expected a status fault, got %v", err)
	}
	return fault
}

func writeTestGreenZip(t *testing.T, path, version string) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	w := zip.NewWriter(f)
	files := []string{
		"Octop-test/launch.py",
		"Octop-test/VERSION.txt",
		"Octop-test/packages/octop-" + version + ".dist-info/METADATA",
	}
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
		if strings.HasSuffix(name, "/VERSION.txt") {
			content = []byte("platform=test\noctop_version=" + version + "\n")
		} else if strings.HasSuffix(name, "/METADATA") {
			content = []byte("Name: octop\nVersion: " + version + "\n")
		} else if strings.HasSuffix(name, "/python3") {
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

func writeMetadataOnlyZip(t *testing.T, path, version string) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	w := zip.NewWriter(f)
	entry, err := w.Create("Octop-test/packages/octop-" + version + ".dist-info/METADATA")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := entry.Write([]byte("Name: octop\nVersion: " + version + "\n")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
}
