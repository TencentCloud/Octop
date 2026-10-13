package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const sqliteBackupScript = "import sqlite3,sys; src=sqlite3.connect(sys.argv[1]); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()"

var runSQLiteBackup = func(python, source, destination string) error {
	cmd := exec.Command(python, "-c", sqliteBackupScript, source, destination)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("SQLite backup failed: %w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

type desktopDatabaseConfig struct {
	Database struct {
		Driver     string `json:"driver"`
		SQLitePath string `json:"sqlite_path"`
	} `json:"database"`
}

func desktopSQLitePath(home string) (string, bool, error) {
	driver := "sqlite"
	sqlitePath := "octop.db"
	configPath := filepath.Join(home, "config.json")
	if data, err := os.ReadFile(configPath); err == nil {
		var config desktopDatabaseConfig
		if err := json.Unmarshal(data, &config); err != nil {
			return "", false, fmt.Errorf("read database config: %w", err)
		}
		if config.Database.Driver != "" {
			driver = strings.ToLower(strings.TrimSpace(config.Database.Driver))
		}
		if config.Database.SQLitePath != "" {
			sqlitePath = config.Database.SQLitePath
		}
	} else if !os.IsNotExist(err) {
		return "", false, fmt.Errorf("read database config: %w", err)
	}

	if os.Getenv("OCTOP_DATABASE_URL") != "" {
		driver = "postgresql"
	}
	if value := strings.TrimSpace(os.Getenv("OCTOP_DATABASE_DRIVER")); value != "" {
		driver = strings.ToLower(value)
	}
	if value := os.Getenv("OCTOP_DATABASE_SQLITE_PATH"); value != "" {
		sqlitePath = value
	}
	if driver == "postgresql" {
		return "", false, nil
	}
	if driver != "sqlite" {
		return "", false, fmt.Errorf("unsupported database driver %q", driver)
	}
	if !filepath.IsAbs(sqlitePath) {
		sqlitePath = filepath.Join(home, sqlitePath)
	}
	return filepath.Clean(sqlitePath), true, nil
}

func safeVersion(value string) string {
	var result strings.Builder
	for _, char := range value {
		if (char >= 'a' && char <= 'z') || (char >= 'A' && char <= 'Z') ||
			(char >= '0' && char <= '9') || char == '.' || char == '-' {
			result.WriteRune(char)
		}
	}
	if result.Len() == 0 {
		return "unknown"
	}
	return result.String()
}

func backupSQLiteBeforeUpgrade(root, currentVersion, nextVersion string) (string, error) {
	home := octopHome()
	source, isSQLite, err := desktopSQLitePath(home)
	if err != nil || !isSQLite {
		return "", err
	}
	if _, err := os.Stat(source); os.IsNotExist(err) {
		return "", nil
	} else if err != nil {
		return "", fmt.Errorf("inspect SQLite database: %w", err)
	}

	backupDir := filepath.Join(home, "backups")
	if err := os.MkdirAll(backupDir, 0o700); err != nil {
		return "", fmt.Errorf("create backup directory: %w", err)
	}
	name := fmt.Sprintf(
		"octop-desktop-pre-upgrade-%s-to-%s-%s.db",
		safeVersion(currentVersion),
		safeVersion(nextVersion),
		time.Now().UTC().Format("20060102T150405.000000000Z"),
	)
	destination := filepath.Join(backupDir, name)
	if err := runSQLiteBackup(pythonExe(root), source, destination); err != nil {
		_ = os.Remove(destination)
		return "", err
	}
	if err := os.Chmod(destination, 0o600); err != nil {
		_ = os.Remove(destination)
		return "", fmt.Errorf("secure SQLite backup: %w", err)
	}
	return destination, nil
}
