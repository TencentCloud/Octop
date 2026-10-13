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
	writeTestGreenZip(t, zipPath, "1.0.0")

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
	if err := ensurePortable(LocaleZH, func(status string) { statuses = append(statuses, status) }); err != nil {
		t.Fatal(err)
	}

	if got := portableVersion(root); got != "0.9.32" {
		t.Fatalf("portable version = %q, want 0.9.32", got)
	}
	if _, err := os.Stat(stale); !os.IsNotExist(err) {
		t.Fatalf("old runtime was not replaced: %v", err)
	}
	if len(statuses) < 2 ||
		statuses[0] != "发现客户端新版 0.9.32，正在备份数据库…" ||
		statuses[1] != "正在更新内置运行环境…" {
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

	if err := ensurePortable(LocaleZH, func(string) {}); err != nil {
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

	if err := ensurePortable(LocaleZH, func(string) {}); err == nil {
		t.Fatal("backup failure should abort the runtime upgrade")
	}
	if got := portableVersion(root); got != "0.9.29" {
		t.Fatalf("portable version = %q, want preserved 0.9.29", got)
	}
}

func TestEnsurePortableKeepsNewerExistingRuntime(t *testing.T) {
	for _, test := range []struct {
		name, installed, recorded, bundled string
	}{
		{"stable", "0.9.33", "0.9.31", "0.9.32"},
		{"in-app prerelease upgrade", "1.0.2b6", "1.0.2b4", "1.0.2b5"},
	} {
		t.Run(test.name, func(t *testing.T) {
			home := t.TempDir()
			t.Setenv("OCTOP_HOME", home)
			root := portableDir()

			newZip := filepath.Join(t.TempDir(), "new.zip")
			writeTestGreenZip(t, newZip, test.installed)
			if err := unzipGreen(newZip, root); err != nil {
				t.Fatal(err)
			}
			// An in-app package upgrade can leave the original VERSION.txt behind.
			preserved := map[string]string{
				filepath.Join(root, "VERSION.txt"): "octop_version=" + test.recorded + "\n",
				filepath.Join(root, "keep.txt"):    "keep",
				filepath.Join(home, "octop.db"):    "database",
			}
			for path, content := range preserved {
				if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
					t.Fatal(err)
				}
			}

			oldZip := filepath.Join(t.TempDir(), "old.zip")
			writeTestGreenZip(t, oldZip, test.bundled)
			t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", oldZip)
			if got, err := bundledPortableVersion(); err != nil || got != test.bundled {
				t.Fatalf("bundled version = %q, err = %v, want %q", got, err, test.bundled)
			}
			backupCalls := 0
			previousBackup := runSQLiteBackup
			runSQLiteBackup = func(_, _, _ string) error {
				backupCalls++
				return errors.New("unexpected backup for a newer installed runtime")
			}
			t.Cleanup(func() { runSQLiteBackup = previousBackup })

			for startup := 0; startup < 2; startup++ {
				var statuses []string
				if err := ensurePortable(LocaleZH, func(status string) { statuses = append(statuses, status) }); err != nil {
					t.Fatal(err)
				}
				if got := portableVersion(root); got != test.installed {
					t.Fatalf("portable version = %q, want %q", got, test.installed)
				}
				if got := installedPackageVersion(root); got != test.installed {
					t.Fatalf("installed package version = %q, want %q", got, test.installed)
				}
				for path, want := range preserved {
					if data, err := os.ReadFile(path); err != nil || string(data) != want {
						t.Fatalf("startup %d changed %s: %q, %v", startup, path, data, err)
					}
				}
				if len(statuses) != 1 || statuses[0] != desktopText(LocaleZH, copyStatusUsingRuntime) {
					t.Fatalf("unexpected startup statuses: %v", statuses)
				}
				if backupCalls != 0 {
					t.Fatalf("newer installed runtime triggered %d backups", backupCalls)
				}
			}
		})
	}
}

func TestPortableVersionPrefersNewerMetadataOverVersionTxt(t *testing.T) {
	home := t.TempDir()
	t.Setenv("OCTOP_HOME", home)
	root := portableDir()
	b4Zip := filepath.Join(t.TempDir(), "b4.zip")
	writeTestGreenZip(t, b4Zip, "1.0.2b4")
	if err := unzipGreen(b4Zip, root); err != nil {
		t.Fatal(err)
	}

	// An in-app upgrade can leave both the old VERSION.txt and old dist-info.
	metadata := filepath.Join(root, "packages", "octop-1.0.2b5.dist-info", "METADATA")
	if err := os.MkdirAll(filepath.Dir(metadata), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(metadata, []byte("Name: octop\nVersion: 1.0.2b5\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if got := portableVersion(root); got != "1.0.2b5" {
		t.Fatalf("portable version = %q, want newer package metadata 1.0.2b5", got)
	}

	preserved := map[string]string{
		filepath.Join(root, "VERSION.txt"): "octop_version=1.0.2b4\n",
		filepath.Join(root, "keep.txt"):    "keep",
		filepath.Join(home, "octop.db"):    "database",
	}
	for path, content := range preserved {
		if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	b5Zip := filepath.Join(t.TempDir(), "b5.zip")
	writeTestGreenZip(t, b5Zip, "1.0.2b5")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", b5Zip)
	backupCalls := 0
	previousBackup := runSQLiteBackup
	runSQLiteBackup = func(_, _, _ string) error {
		backupCalls++
		return errors.New("unexpected backup for an already installed version")
	}
	t.Cleanup(func() { runSQLiteBackup = previousBackup })

	for startup := 0; startup < 2; startup++ {
		var statuses []string
		if err := ensurePortable(LocaleZH, func(status string) { statuses = append(statuses, status) }); err != nil {
			t.Fatal(err)
		}
		if got := portableVersion(root); got != "1.0.2b5" {
			t.Fatalf("portable version = %q, want preserved 1.0.2b5", got)
		}
		for path, want := range preserved {
			if data, err := os.ReadFile(path); err != nil || string(data) != want {
				t.Fatalf("startup %d changed %s: %q, %v", startup, path, data, err)
			}
		}
		if len(statuses) != 1 || statuses[0] != desktopText(LocaleZH, copyStatusUsingRuntime) {
			t.Fatalf("unexpected startup statuses: %v", statuses)
		}
		if backupCalls != 0 {
			t.Fatalf("already installed version triggered %d backups", backupCalls)
		}
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
	writeVersionOnlyZip(t, invalidZip, "0.9.32")
	t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", invalidZip)
	var statuses []string
	if err := ensurePortable(LocaleZH, func(status string) { statuses = append(statuses, status) }); err != nil {
		t.Fatalf("existing runtime should still boot after a failed replacement: %v", err)
	}

	if !launchReady(root) {
		t.Fatal("current runtime should remain usable after replacement failure")
	}
	if got := portableVersion(root); got != "0.9.31" {
		t.Fatalf("portable version = %q, want 0.9.31", got)
	}
	if len(statuses) == 0 || statuses[len(statuses)-1] != "更新内置运行环境失败，继续使用已有运行环境…" {
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
	if err := ensurePortable(LocaleZH, func(string) {}); err != nil {
		t.Fatal(err)
	}
	if got := portableVersion(root); got != "0.9.32" {
		t.Fatalf("portable version = %q, want 0.9.32", got)
	}
}

func TestBundledPortableVersionFallsBackToMetadata(t *testing.T) {
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

// Keep these cases aligned with octop.infra.setup.self_update.parse_version.
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
		{"0.9.34-beta.1", "0.9.34b1", 0},
		{"1.0.2b5", "1.0.2b4", 1},
		{"1.0.2b4", "1.0.2b5", -1},
		{"1.0.2b10", "1.0.2b9", 1},
		{"1.0.2", "1.0.2b5", 1},
		{"1.0.2b5", "1.0.2", -1},
		{"1.0.2a2", "1.0.2b1", -1},
		{"1.0.2b5", "1.0.2rc1", -1},
		{"1.0.2rc1", "1.0.2", -1},
		{"v1.0.2B05", "1.0.2b5", 0},
		{"1.0.2+local.10", "1.0.2+local.9", 0},
		{"1.0.2+local.10", "1.0.2", 0},
		{"1.0.2-custom", "1.0.1", 1},
		{"dev", "dev", 0},
	} {
		t.Run(test.left+"/"+test.right, func(t *testing.T) {
			if got := compareVersions(test.left, test.right); got != test.want {
				t.Fatalf("compareVersions(%q, %q) = %d, want %d", test.left, test.right, got, test.want)
			}
		})
	}
}

func TestEnsurePortablePrereleaseUpgrade(t *testing.T) {
	for _, test := range []struct {
		name, installed, bundled string
		upgrade, backupFails     bool
	}{
		{"beta", "1.0.2b4", "1.0.2b5", true, false},
		{"two-digit beta", "1.0.2b9", "1.0.2b10", true, false},
		{"final", "1.0.2b5", "1.0.2", true, false},
		{"same", "1.0.2b5", "1.0.2b5", false, false},
		{"backup failure", "1.0.2b4", "1.0.2b5", true, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			home := t.TempDir()
			t.Setenv("OCTOP_HOME", home)
			root := portableDir()
			oldZip := filepath.Join(t.TempDir(), "old.zip")
			writeTestGreenZip(t, oldZip, test.installed)
			if err := unzipGreen(oldZip, root); err != nil {
				t.Fatal(err)
			}
			marker := filepath.Join(root, "keep.txt")
			database := filepath.Join(home, "octop.db")
			for _, path := range []string{marker, database} {
				if err := os.WriteFile(path, []byte("preserve"), 0o600); err != nil {
					t.Fatal(err)
				}
			}
			newZip := filepath.Join(t.TempDir(), "new.zip")
			writeTestGreenZip(t, newZip, test.bundled)
			t.Setenv("OCTOP_DESKTOP_PORTABLE_ZIP", newZip)

			backupCalls := 0
			previousBackup := runSQLiteBackup
			runSQLiteBackup = func(_ string, source, destination string) error {
				backupCalls++
				if source != database || portableVersion(root) != test.installed {
					t.Fatal("backup must precede replacement of the installed runtime")
				}
				if test.backupFails {
					return errors.New("backup unavailable")
				}
				return os.WriteFile(destination, []byte("backup"), 0o600)
			}
			t.Cleanup(func() { runSQLiteBackup = previousBackup })

			err := ensurePortable(LocaleZH, func(string) {})
			if (err != nil) != test.backupFails {
				t.Fatalf("ensurePortable error = %v, backupFails = %v", err, test.backupFails)
			}
			wantVersion := test.installed
			if test.upgrade && !test.backupFails {
				wantVersion = test.bundled
			}
			if got := portableVersion(root); got != wantVersion {
				t.Fatalf("portable version = %q, want %q", got, wantVersion)
			}
			wantBackups := 0
			if test.upgrade {
				wantBackups = 1
			}
			if backupCalls != wantBackups {
				t.Fatalf("backup calls = %d, want %d", backupCalls, wantBackups)
			}
			if data, err := os.ReadFile(database); err != nil || string(data) != "preserve" {
				t.Fatalf("database changed: %q, %v", data, err)
			}
			_, markerErr := os.Stat(marker)
			if test.upgrade && !test.backupFails {
				if !os.IsNotExist(markerErr) {
					t.Fatalf("old runtime was not replaced: %v", markerErr)
				}
			} else if markerErr != nil {
				t.Fatalf("installed runtime was not preserved: %v", markerErr)
			}
			if test.backupFails {
				return
			}
			if err := os.WriteFile(marker, []byte("keep on restart"), 0o600); err != nil {
				t.Fatal(err)
			}
			if err := ensurePortable(LocaleZH, func(string) {}); err != nil {
				t.Fatal(err)
			}
			if data, err := os.ReadFile(marker); err != nil || string(data) != "keep on restart" {
				t.Fatalf("runtime was replaced again: %q, %v", data, err)
			}
			if backupCalls != wantBackups {
				t.Fatal("repeated startup unexpectedly backed up the database again")
			}
		})
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

func writeVersionOnlyZip(t *testing.T, path, version string) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	w := zip.NewWriter(f)
	entry, err := w.Create("Octop-test/VERSION.txt")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := entry.Write([]byte("octop_version=" + version + "\n")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
}
