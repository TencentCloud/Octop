package main

import (
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestParseFileDropEvent(t *testing.T) {
	paths, ok := parseFileDropEvent("desktop:minimise")
	if ok || paths != nil {
		t.Fatalf("unrelated event parsed as file drop: %#v %v", paths, ok)
	}
	raw := `["/tmp/a.txt","/tmp/文档"]`
	name := fileDropEventPrefix + strings.ReplaceAll(raw, " ", "")
	// JSON has no spaces; QueryUnescape is still applied.
	got, ok := parseFileDropEvent(name)
	if !ok {
		t.Fatal("expected file drop event")
	}
	if len(got) != 2 || got[0] != "/tmp/a.txt" || got[1] != "/tmp/文档" {
		t.Fatalf("paths = %#v", got)
	}
}

func TestExpandDroppedPathsWalksFolders(t *testing.T) {
	root := t.TempDir()
	nested := filepath.Join(root, "docs", "nested")
	if err := os.MkdirAll(nested, 0o755); err != nil {
		t.Fatal(err)
	}
	readme := filepath.Join(root, "docs", "README.md")
	note := filepath.Join(nested, "note.txt")
	if err := os.WriteFile(readme, []byte("# hi"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(note, []byte("note"), 0o644); err != nil {
		t.Fatal(err)
	}
	loose := filepath.Join(root, "loose.txt")
	if err := os.WriteFile(loose, []byte("loose"), 0o644); err != nil {
		t.Fatal(err)
	}

	files, truncated := expandDroppedPaths([]string{filepath.Join(root, "docs"), loose, "relative.txt"})
	if truncated {
		t.Fatal("small drop was truncated")
	}
	names := map[string]bool{}
	for _, file := range files {
		names[file.Name] = true
		if !filepath.IsAbs(file.Path) {
			t.Fatalf("path is not absolute: %s", file.Path)
		}
	}
	if !names["README.md"] || !names["note.txt"] || !names["loose.txt"] {
		t.Fatalf("files = %#v", files)
	}
	if names["docs"] {
		t.Fatal("directory itself was included")
	}
}

func TestDropServerServesOnlyPublishedFiles(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "hello.txt")
	if err := os.WriteFile(path, []byte("hello"), 0o644); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	server := &dropServer{}
	t.Cleanup(server.close)
	base, err := server.publish([]localDropFile{{
		Name: "hello.txt",
		Path: path,
		Type: "text/plain",
		Size: info.Size(),
	}})
	if err != nil {
		t.Fatal(err)
	}
	var resp *http.Response
	var err error
	for attempt := 0; attempt < 20; attempt++ {
		resp, err = http.Get(base + "/0")
		if err == nil {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK || string(body) != "hello" {
		t.Fatalf("status %d body %q", resp.StatusCode, body)
	}
	if got := resp.Header.Get("Access-Control-Allow-Origin"); got != "*" {
		t.Fatalf("cors = %q", got)
	}
	missing, err := http.Get(base + "/1")
	if err != nil {
		t.Fatal(err)
	}
	missing.Body.Close()
	if missing.StatusCode != http.StatusNotFound {
		t.Fatalf("missing index status %d", missing.StatusCode)
	}
}

func TestDesktopDropDispatchJS(t *testing.T) {
	payload, err := json.Marshal(desktopDropPayload{
		Files: []desktopDropFile{{Name: "a.txt", URL: "http://127.0.0.1:1/drop/t/0", Type: "text/plain", Size: 1}},
	})
	if err != nil {
		t.Fatal(err)
	}
	js := desktopDropDispatchJS(payload)
	if !strings.Contains(js, desktopDropEvent) || !strings.Contains(js, "a.txt") {
		t.Fatalf("dispatch js = %s", js)
	}
}

func TestFileDropJSBridgesNativeDrops(t *testing.T) {
	js := fileDropJS()
	for _, needle := range []string{
		"handlePlatformFileDrop",
		"handleDragOver",
		"data-octop-chat-drop",
		"postMessageWithAdditionalObjects",
		fileDropEventPrefix,
		"wails:runtime:ready",
	} {
		if !strings.Contains(js, needle) {
			t.Fatalf("file drop JS missing %q", needle)
		}
	}
	if strings.Index(js, "handlePlatformFileDrop") > strings.Index(js, "wails:runtime:ready") {
		t.Fatal("runtime ready must be signaled after the drop handler is installed")
	}
}

func TestDropBatchExpires(t *testing.T) {
	server := &dropServer{}
	t.Cleanup(server.close)
	dir := t.TempDir()
	path := filepath.Join(dir, "a.txt")
	if err := os.WriteFile(path, []byte("a"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := server.publish([]localDropFile{{Name: "a.txt", Path: path, Type: "text/plain", Size: 1}}); err != nil {
		t.Fatal(err)
	}
	server.mu.Lock()
	for token, batch := range server.batches {
		batch.expires = time.Now().Add(-time.Second)
		server.batches[token] = batch
	}
	server.mu.Unlock()
	if _, ok := server.lookup("missing", 0); ok {
		t.Fatal("missing token was found")
	}
	server.mu.Lock()
	var token string
	for key := range server.batches {
		token = key
	}
	server.mu.Unlock()
	if _, ok := server.lookup(token, 0); ok {
		t.Fatal("expired batch was served")
	}
}
