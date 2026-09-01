package main

import (
	"archive/zip"
	"bytes"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

func launchReady(root string) bool {
	if _, err := os.Stat(filepath.Join(root, "launch.py")); err != nil {
		return false
	}
	info, err := os.Stat(pythonExe(root))
	if err != nil || !info.Mode().IsRegular() || info.Size() < 1024 {
		return false
	}
	return runtime.GOOS == "windows" || info.Mode().Perm()&0o111 != 0
}

func pythonExe(root string) string {
	if runtime.GOOS == "windows" {
		return filepath.Join(root, "runtime", "python.exe")
	}
	return filepath.Join(root, "runtime", "bin", "python3")
}

func ensurePortable(locale Locale, status func(string)) error {
	root := portableDir()
	if launchReady(root) {
		status(desktopText(locale, "正在使用已有运行环境…", "Using the existing runtime…"))
		return nil
	}
	status(desktopText(locale, "首次启动，正在解压内置运行环境…", "First launch: unpacking the bundled runtime…"))
	if err := extractPortable(root); err != nil {
		return err
	}
	if runtime.GOOS == "darwin" {
		_ = exec.Command("xattr", "-dr", "com.apple.quarantine", root).Run()
	}
	if !launchReady(root) {
		return fmt.Errorf("portable extract missing launch.py or python under %s", root)
	}
	return nil
}

func extractPortable(root string) error {
	if os.Getenv("OCTOP_DESKTOP_PORTABLE_ZIP") != "" {
		zipPath, err := bundledPortableZip()
		if err != nil {
			return err
		}
		return unzipGreen(zipPath, root)
	}
	if len(embeddedPortable) > 0 {
		return unzipGreenBytes(embeddedPortable, root)
	}
	zipPath, err := bundledPortableZip()
	if err != nil {
		return err
	}
	return unzipGreen(zipPath, root)
}

func bundledPortableZip() (string, error) {
	name := fmt.Sprintf("Octop-%s.zip", greenPlat())
	if override := os.Getenv("OCTOP_DESKTOP_PORTABLE_ZIP"); override != "" {
		if _, err := os.Stat(override); err != nil {
			return "", fmt.Errorf("bundled portable package: %w", err)
		}
		return override, nil
	}
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	dir := filepath.Dir(exe)
	candidates := []string{
		filepath.Join(dir, name),
		filepath.Join(dir, "..", "Resources", name),
	}
	for _, candidate := range candidates {
		candidate = filepath.Clean(candidate)
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("bundled portable package %s not found beside application", name)
}

func unzipGreen(zipPath, dest string) error {
	r, err := zip.OpenReader(zipPath)
	if err != nil {
		return err
	}
	defer r.Close()
	return unzipGreenFiles(r.File, dest)
}

func unzipGreenBytes(data []byte, dest string) error {
	r, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return err
	}
	return unzipGreenFiles(r.File, dest)
}

func unzipGreenFiles(files []*zip.File, dest string) error {
	_ = os.RemoveAll(dest)
	if err := os.MkdirAll(dest, 0o755); err != nil {
		return err
	}
	// Zip root is Octop-<plat>/… — strip that prefix.
	for _, f := range files {
		name := f.Name
		parts := strings.SplitN(name, "/", 2)
		if len(parts) < 2 {
			continue
		}
		rel := parts[1]
		if rel == "" {
			continue
		}
		target := filepath.Join(dest, filepath.FromSlash(rel))
		if !strings.HasPrefix(target, filepath.Clean(dest)+string(os.PathSeparator)) && target != filepath.Clean(dest) {
			return fmt.Errorf("illegal zip path %s", name)
		}
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(target, 0o755); err != nil {
				return err
			}
			continue
		}
		if f.Mode()&os.ModeSymlink != 0 {
			rc, err := f.Open()
			if err != nil {
				return err
			}
			linkTarget, err := io.ReadAll(rc)
			rc.Close()
			if err != nil {
				return err
			}
			if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
				return err
			}
			if err := os.Symlink(string(linkTarget), target); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}
		rc, err := f.Open()
		if err != nil {
			return err
		}
		out, err := os.OpenFile(target, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, f.Mode())
		if err != nil {
			rc.Close()
			return err
		}
		_, err = io.Copy(out, rc)
		out.Close()
		rc.Close()
		if err != nil {
			return err
		}
	}
	return nil
}

func waitHealth(locale Locale, base string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	url := strings.TrimRight(base, "/") + "/api/health"
	var lastErr error
	var lastStatus int
	for time.Now().Before(deadline) {
		resp, err := http.Get(url)
		if err == nil {
			lastStatus = resp.StatusCode
			lastErr = nil
			resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 500 {
				return nil
			}
		} else {
			lastErr = err
			lastStatus = 0
		}
		time.Sleep(400 * time.Millisecond)
	}
	return formatHealthWaitError(locale, base, timeout, lastErr, lastStatus)
}

func formatWaitDuration(locale Locale, d time.Duration) string {
	sec := int(d.Round(time.Second) / time.Second)
	if sec < 1 {
		sec = 1
	}
	minutes := sec%60 == 0
	n := sec
	if minutes {
		n = sec / 60
	}
	if locale == LocaleEN {
		unit := "seconds"
		if minutes {
			unit = "minutes"
		}
		if n == 1 {
			if minutes {
				return "1 minute"
			}
			return "1 second"
		}
		return fmt.Sprintf("%d %s", n, unit)
	}
	if minutes {
		return fmt.Sprintf("%d 分钟", n)
	}
	return fmt.Sprintf("%d 秒", n)
}

func formatHealthWaitError(locale Locale, base string, timeout time.Duration, lastErr error, lastStatus int) error {
	addr := strings.TrimRight(base, "/")
	wait := formatWaitDuration(locale, timeout)
	switch {
	case lastStatus >= 500:
		return fmt.Errorf("%s", desktopText(locale,
			fmt.Sprintf("Octop 服务未在%s内就绪（%s）。服务已响应但尚未就绪，请稍后再试，或查看终端日志。", wait, addr),
			fmt.Sprintf("Octop did not become ready within %s (%s). The service responded but is not ready yet. Try again, or check the terminal logs.", wait, addr),
		))
	case lastErr != nil:
		return fmt.Errorf("%s", desktopText(locale,
			fmt.Sprintf("Octop 服务未在%s内就绪（%s）。目前无法连接该地址，请确认 Octop 正在运行。", wait, addr),
			fmt.Sprintf("Octop did not become ready within %s (%s). Could not connect — make sure Octop is running.", wait, addr),
		))
	default:
		return fmt.Errorf("%s", desktopText(locale,
			fmt.Sprintf("Octop 服务未在%s内就绪（%s）。请确认本机已启动 Octop，且地址、端口正确；也可查看终端日志。", wait, addr),
			fmt.Sprintf("Octop did not become ready within %s (%s). Make sure Octop is running at this address, or check the terminal logs.", wait, addr),
		))
	}
}
