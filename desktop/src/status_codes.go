package main

// Status codes are the wire contract with the shell page. Each one is a copy key
// in dashboard/src/locales/{en,zh}.json under `desktopShell.` and the page
// renders it through i18next, which is the shell's only copy source. Format
// arguments travel next to the code as `args` (e.g. {"port": 8088}).
const (
	codeStatusConnecting       = "status.connecting"
	codeStatusCheckingRuntime  = "status.checking_runtime"
	codeStatusStartingService  = "status.starting_service"
	codeStatusReady            = "status.ready"
	codeStatusUsingRuntime     = "status.using_runtime"
	codeStatusBackupDatabase   = "status.backup_database"
	codeStatusUpdatingRuntime  = "status.updating_runtime"
	codeStatusFirstExtract     = "status.first_extract"
	codeStatusUpdateFailedKeep = "status.update_failed_keep"

	codeErrorAppTooOld      = "error.app_too_old"
	codeErrorBackupFailed   = "error.backup_failed"
	codeErrorPortInUse      = "error.port_in_use"
	codeErrorForeignService = "error.foreign_service"
	codeErrorStartFailed    = "error.start_failed"
	codeErrorUnexpected     = "error.unexpected"

	codeHealthNotReady5xx     = "health.not_ready_5xx"
	codeHealthNotReadyConnect = "health.not_ready_connect"
	codeHealthNotReady        = "health.not_ready"
)

// shellStatusCodes lists every code the shell can emit, so a test can prove the
// page bundles carry copy for all of them.
var shellStatusCodes = []string{
	codeStatusConnecting,
	codeStatusCheckingRuntime,
	codeStatusStartingService,
	codeStatusReady,
	codeStatusUsingRuntime,
	codeStatusBackupDatabase,
	codeStatusUpdatingRuntime,
	codeStatusFirstExtract,
	codeStatusUpdateFailedKeep,
	codeErrorAppTooOld,
	codeErrorBackupFailed,
	codeErrorPortInUse,
	codeErrorForeignService,
	codeErrorStartFailed,
	codeErrorUnexpected,
	codeHealthNotReady5xx,
	codeHealthNotReadyConnect,
	codeHealthNotReady,
}
