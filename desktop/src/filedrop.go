package main

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"log"
	"mime"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/wailsapp/wails/v3/pkg/application"
)

const (
	fileDropEventPrefix = "desktop:file-drop:"
	desktopDropEvent    = "octop:desktop-file-drop"
	maxDesktopDropFiles = 500
	dropBatchTTL        = 2 * time.Minute
)

type fileDropEventListener struct {
	app *App
}

func (l *fileDropEventListener) DispatchWailsEvent(event *application.CustomEvent) {
	if event == nil || l.app == nil {
		return
	}
	paths, ok := parseFileDropEvent(event.Name)
	if !ok {
		return
	}
	go l.app.deliverDroppedFiles(paths)
}

func attachFileDropEventListener(app *application.App, api *App) {
	if app == nil || api == nil {
		return
	}
	appendWailsEventListener(app, &fileDropEventListener{app: api})
}

func parseFileDropEvent(name string) ([]string, bool) {
	if !strings.HasPrefix(name, fileDropEventPrefix) {
		return nil, false
	}
	raw, err := url.QueryUnescape(strings.TrimPrefix(name, fileDropEventPrefix))
	if err != nil || strings.TrimSpace(raw) == "" {
		return nil, false
	}
	var paths []string
	if err := json.Unmarshal([]byte(raw), &paths); err != nil {
		return nil, false
	}
	return paths, true
}

type localDropFile struct {
	Name string
	Path string
	Type string
	Size int64
}

func expandDroppedPaths(paths []string) (files []localDropFile, truncated bool) {
	seen := map[string]struct{}{}
	add := func(path string, info os.FileInfo) {
		if len(files) >= maxDesktopDropFiles {
			truncated = true
			return
		}
		cleaned := filepath.Clean(path)
		if _, ok := seen[cleaned]; ok {
			return
		}
		seen[cleaned] = struct{}{}
		name := filepath.Base(cleaned)
		if name == "." || name == ".." || name == string(filepath.Separator) {
			return
		}
		media := mime.TypeByExtension(filepath.Ext(name))
		if media == "" {
			media = "application/octet-stream"
		}
		files = append(files, localDropFile{
			Name: name,
			Path: cleaned,
			Type: media,
			Size: info.Size(),
		})
	}
	for _, raw := range paths {
		if len(files) >= maxDesktopDropFiles {
			truncated = true
			break
		}
		raw = strings.TrimSpace(raw)
		if raw == "" || strings.ContainsRune(raw, 0) || !filepath.IsAbs(raw) {
			continue
		}
		abs, err := filepath.Abs(raw)
		if err != nil {
			continue
		}
		info, err := os.Stat(abs)
		if err != nil {
			continue
		}
		if info.IsDir() {
			_ = filepath.WalkDir(abs, func(path string, entry fs.DirEntry, walkErr error) error {
				if walkErr != nil || entry.IsDir() {
					return nil
				}
				st, err := os.Stat(path)
				if err != nil || !st.Mode().IsRegular() {
					return nil
				}
				add(path, st)
				if len(files) >= maxDesktopDropFiles {
					truncated = true
					return fs.SkipAll
				}
				return nil
			})
			continue
		}
		if info.Mode().IsRegular() {
			add(abs, info)
		}
	}
	return files, truncated
}

type desktopDropFile struct {
	Name string `json:"name"`
	URL  string `json:"url"`
	Type string `json:"type"`
	Size int64  `json:"size"`
}

type desktopDropPayload struct {
	Files     []desktopDropFile `json:"files"`
	Truncated bool              `json:"truncated,omitempty"`
	Max       int               `json:"max,omitempty"`
}

func desktopDropDispatchJS(payload []byte) string {
	return fmt.Sprintf(
		`window.dispatchEvent(new CustomEvent(%q,{detail:%s}))`,
		desktopDropEvent,
		payload,
	)
}

type dropBatch struct {
	files   []localDropFile
	expires time.Time
}

type dropServer struct {
	mu       sync.Mutex
	listener net.Listener
	server   *http.Server
	addr     string
	batches  map[string]dropBatch
}

func (s *dropServer) publish(files []localDropFile) (string, error) {
	if err := s.ensure(); err != nil {
		return "", err
	}
	token, err := randomToken()
	if err != nil {
		return "", err
	}
	s.mu.Lock()
	s.batches[token] = dropBatch{files: files, expires: time.Now().Add(dropBatchTTL)}
	addr := s.addr
	s.mu.Unlock()
	return "http://" + addr + "/drop/" + token, nil
}

func (s *dropServer) ensure() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.server != nil {
		return nil
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return err
	}
	s.listener = listener
	s.addr = listener.Addr().String()
	s.batches = map[string]dropBatch{}
	mux := http.NewServeMux()
	mux.HandleFunc("/drop/", s.serve)
	s.server = &http.Server{Handler: mux}
	go func() {
		if err := s.server.Serve(listener); err != nil && err != http.ErrServerClosed {
			log.Printf("desktop file drop server: %v", err)
		}
	}()
	return nil
}

func (s *dropServer) close() {
	s.mu.Lock()
	server := s.server
	s.server = nil
	s.listener = nil
	s.batches = nil
	s.mu.Unlock()
	if server != nil {
		_ = server.Close()
	}
}

func (s *dropServer) lookup(token string, index int) (localDropFile, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	batch, ok := s.batches[token]
	if !ok || time.Now().After(batch.expires) || index < 0 || index >= len(batch.files) {
		return localDropFile{}, false
	}
	return batch.files[index], true
}

func (s *dropServer) serve(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Cache-Control", "no-store")
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodGet && r.Method != http.MethodHead {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	token, index, ok := parseDropURL(r.URL.Path)
	if !ok {
		http.NotFound(w, r)
		return
	}
	file, ok := s.lookup(token, index)
	if !ok {
		http.NotFound(w, r)
		return
	}
	opened, err := os.Open(file.Path)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer opened.Close()
	info, err := opened.Stat()
	if err != nil || !info.Mode().IsRegular() {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", file.Type)
	http.ServeContent(w, r, file.Name, info.ModTime(), opened)
}

func parseDropURL(path string) (string, int, bool) {
	trimmed := strings.TrimPrefix(path, "/drop/")
	token, indexRaw, ok := strings.Cut(trimmed, "/")
	if !ok || token == "" || strings.Contains(token, "/") || strings.Contains(indexRaw, "/") {
		return "", 0, false
	}
	index, err := strconv.Atoi(indexRaw)
	if err != nil {
		return "", 0, false
	}
	return token, index, true
}

func randomToken() (string, error) {
	buf := make([]byte, 16)
	if _, err := io.ReadFull(rand.Reader, buf); err != nil {
		return "", err
	}
	return hex.EncodeToString(buf), nil
}

func (a *App) deliverDroppedFiles(paths []string) {
	files, truncated := expandDroppedPaths(paths)
	payload := desktopDropPayload{Files: []desktopDropFile{}}
	if truncated {
		payload.Truncated = true
		payload.Max = maxDesktopDropFiles
	}
	if len(files) > 0 {
		base, err := a.drops.publish(files)
		if err != nil {
			log.Printf("desktop file drop: %v", err)
			return
		}
		for i, file := range files {
			payload.Files = append(payload.Files, desktopDropFile{
				Name: file.Name,
				URL:  base + "/" + strconv.Itoa(i),
				Type: file.Type,
				Size: file.Size,
			})
		}
	}
	body, err := json.Marshal(payload)
	if err != nil || a.window == nil {
		return
	}
	a.window.ExecJS(desktopDropDispatchJS(body))
}

func fileDropJS() string {
	return `(function(){
		if (!window._wails || typeof window._wails.invoke !== "function") return;
		if (window.__octopFileDrop) return;
		window.__octopFileDrop = true;
		var nativeDrag = false;
		var current = null;
		function zoneAt(x, y) {
			var el = document.elementFromPoint(x, y);
			if (!el || !el.closest) return null;
			return el.closest("[data-octop-chat-drop]");
		}
		function clearZone() {
			if (current) current.classList.remove("file-drop-target-active");
			current = null;
		}
		function emitPaths(filenames) {
			var payload = JSON.stringify(filenames || []);
			window._wails.invoke("wails:event:emit:desktop:file-drop:" + encodeURIComponent(payload));
		}
		if (typeof window._wails.handleDragEnter !== "function") {
			window._wails.handleDragEnter = function() { nativeDrag = true; };
		}
		if (typeof window._wails.handleDragLeave !== "function") {
			window._wails.handleDragLeave = function() { nativeDrag = false; clearZone(); };
		}
		if (typeof window._wails.handleDragOver !== "function") {
			window._wails.handleDragOver = function(x, y) {
				if (!nativeDrag) return;
				var zone = zoneAt(x, y);
				if (current && current !== zone) current.classList.remove("file-drop-target-active");
				if (zone) {
					zone.classList.add("file-drop-target-active");
					current = zone;
				} else {
					current = null;
				}
			};
		}
		if (typeof window._wails.handlePlatformFileDrop !== "function") {
			window._wails.handlePlatformFileDrop = function(filenames, x, y) {
				var zone = zoneAt(x, y);
				clearZone();
				if (!zone) return;
				emitPaths(filenames);
			};
		}
		document.addEventListener("drop", function(event) {
			var transfer = event.dataTransfer;
			if (!transfer || !transfer.types || Array.prototype.indexOf.call(transfer.types, "Files") < 0) return;
			var node = event.target && event.target.nodeType === 1 ? event.target : (event.target && event.target.parentElement);
			var zone = node && node.closest ? node.closest("[data-octop-chat-drop]") : null;
			if (!zone) return;
			event.preventDefault();
			var webview = window.chrome && window.chrome.webview;
			if (webview && typeof webview.postMessageWithAdditionalObjects === "function") {
				var files = [];
				var items = transfer.items;
				if (items) {
					for (var i = 0; i < items.length; i++) {
						if (items[i].kind !== "file") continue;
						var file = items[i].getAsFile();
						if (file) files.push(file);
					}
				}
				if (files.length > 0) {
					event.stopPropagation();
					clearZone();
					webview.postMessageWithAdditionalObjects("file:drop:" + event.clientX + ":" + event.clientY, files);
				}
				return;
			}
			event.stopPropagation();
			clearZone();
		}, true);
		window._wails.invoke("wails:runtime:ready");
	})();`
}
