package main

import (
	"archive/zip"
	"encoding/json"
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

type ghRelease struct {
	TagName string `json:"tag_name"`
	Assets  []struct {
		Name               string `json:"name"`
		BrowserDownloadURL string `json:"browser_download_url"`
	} `json:"assets"`
}

func launchReady(root string) bool {
	if _, err := os.Stat(filepath.Join(root, "launch.py")); err != nil {
		return false
	}
	if runtime.GOOS == "windows" {
		_, err := os.Stat(filepath.Join(root, "runtime", "python.exe"))
		return err == nil
	}
	_, err := os.Stat(filepath.Join(root, "runtime", "bin", "python3"))
	return err == nil
}

func pythonExe(root string) string {
	if runtime.GOOS == "windows" {
		return filepath.Join(root, "runtime", "python.exe")
	}
	return filepath.Join(root, "runtime", "bin", "python3")
}

func ensureGreenZip(repo string, status func(string)) error {
	root := portableDir()
	if launchReady(root) {
		status("using existing portable runtime")
		return nil
	}
	plat := greenPlat()
	name := fmt.Sprintf("Octop-%s.zip", plat)
	status("fetching GitHub release " + name)
	url, err := latestAssetURL(repo, name)
	if err != nil {
		return err
	}
	zipPath := filepath.Join(octopHome(), name)
	if err := os.MkdirAll(octopHome(), 0o755); err != nil {
		return err
	}
	status("downloading " + url)
	if err := downloadFile(url, zipPath); err != nil {
		return err
	}
	defer os.Remove(zipPath)
	status("extracting")
	if err := unzipGreen(zipPath, root); err != nil {
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

func latestAssetURL(repo, assetName string) (string, error) {
	api := "https://api.github.com/repos/" + repo + "/releases/latest"
	req, err := http.NewRequest(http.MethodGet, api, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", "octop-desktop")
	req.Header.Set("Accept", "application/vnd.github+json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return "", fmt.Errorf("github releases: HTTP %d %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	var rel ghRelease
	if err := json.NewDecoder(resp.Body).Decode(&rel); err != nil {
		return "", err
	}
	for _, a := range rel.Assets {
		if a.Name == assetName {
			return a.BrowserDownloadURL, nil
		}
	}
	return "", fmt.Errorf("release %s has no asset %s", rel.TagName, assetName)
}

func downloadFile(url, dest string) error {
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", "octop-desktop")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download HTTP %d", resp.StatusCode)
	}
	tmp := dest + ".partial"
	out, err := os.Create(tmp)
	if err != nil {
		return err
	}
	_, err = io.Copy(out, resp.Body)
	closeErr := out.Close()
	if err != nil {
		_ = os.Remove(tmp)
		return err
	}
	if closeErr != nil {
		_ = os.Remove(tmp)
		return closeErr
	}
	return os.Rename(tmp, dest)
}

func unzipGreen(zipPath, dest string) error {
	r, err := zip.OpenReader(zipPath)
	if err != nil {
		return err
	}
	defer r.Close()
	_ = os.RemoveAll(dest)
	if err := os.MkdirAll(dest, 0o755); err != nil {
		return err
	}
	// Zip root is Octop-<plat>/… — strip that prefix.
	for _, f := range r.File {
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

func waitHealth(base string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	url := strings.TrimRight(base, "/") + "/api/health"
	for time.Now().Before(deadline) {
		resp, err := http.Get(url)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 500 {
				return nil
			}
		}
		time.Sleep(400 * time.Millisecond)
	}
	return fmt.Errorf("octop did not become healthy at %s", url)
}
