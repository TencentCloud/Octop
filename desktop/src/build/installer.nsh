; Same rule as DeepSeek Harness customCheckAppRunning: match this install's
; executable, not another Octop.exe. An update waits up to 10s for the shell
; to leave the tray. Otherwise stop and ask the user to quit. Never taskkill.
!macro customCheckAppRunning
  Push $0
  Push $1
  Push $2
  StrCpy $0 "$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
  ${IfNot} ${FileExists} "$0"
    StrCpy $0 "$WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
  ${EndIf}
  System::Call 'Kernel32::SetEnvironmentVariable(t "OCTOP_INSTALL_EXE", t "$INSTDIR\${APP_EXECUTABLE_FILENAME}")'
  StrCpy $1 0
octop_run_probe:
  nsExec::Exec `"$0" -NoProfile -NonInteractive -Command "try { $$e = [IO.Path]::GetFullPath([Environment]::GetEnvironmentVariable('OCTOP_INSTALL_EXE')); $$hit = $$false; Get-CimInstance Win32_Process | ForEach-Object { if ($$_.ExecutablePath) { try { if ([string]::Equals([IO.Path]::GetFullPath($$_.ExecutablePath), $$e, 'OrdinalIgnoreCase')) { $$hit = $$true } } catch {} } }; if ($$hit) { exit 0 } else { exit 1 } } catch { exit 2 }"`
  Pop $2
  IntCmp $2 0 octop_run_alive
  IntCmp $2 1 octop_run_free octop_run_bad octop_run_bad
octop_run_alive:
  ${If} ${isUpdated}
    IntCmp $1 40 octop_run_busy octop_run_wait octop_run_busy
octop_run_wait:
    IntOp $1 $1 + 1
    Sleep 250
    Goto octop_run_probe
  ${EndIf}
octop_run_busy:
  IntCmp $LANGUAGE 2052 octop_run_zh octop_run_en octop_run_en
octop_run_zh:
  MessageBox MB_OK|MB_ICONINFORMATION "${PRODUCT_NAME} 正在运行，请先在系统托盘中退出应用后重试。" /SD IDOK
  Goto octop_run_quit
octop_run_en:
  MessageBox MB_OK|MB_ICONINFORMATION "${PRODUCT_NAME} is running. Quit it from the system tray and try again." /SD IDOK
octop_run_quit:
  SetErrorLevel 2
  Quit
octop_run_bad:
  IntCmp $LANGUAGE 2052 octop_run_bad_zh octop_run_bad_en octop_run_bad_en
octop_run_bad_zh:
  MessageBox MB_OK|MB_ICONEXCLAMATION "无法确认 ${PRODUCT_NAME} 是否仍在运行，请退出应用后重试。" /SD IDOK
  Goto octop_run_quit
octop_run_bad_en:
  MessageBox MB_OK|MB_ICONEXCLAMATION "Could not check whether ${PRODUCT_NAME} is still running. Quit it and try again." /SD IDOK
  Goto octop_run_quit
octop_run_free:
  Pop $2
  Pop $1
  Pop $0
!macroend

; Expand the green portable zip while the NSIS wizard still has a progress bar.
; The zip stays in $INSTDIR\resources\portable (installer-owned). The tree is
; written to $INSTDIR\resources\sidecar so uninstall can delete it. tar.exe
; (Windows 10+) writes the ~40k files; packing each one as an NSIS payload is slower.
;
; A 32-bit installer on 64-bit Windows is redirected out of System32, so try
; Sysnative first. A 64-bit installer has no Sysnative and uses System32.

!macro customInstall
  Push $0
  Push $1
  Push $2
  Push $3
  Push $4
  Push $5
  DetailPrint "正在展开 Python 运行时…"
  StrCpy $0 "$INSTDIR\resources\portable"
  IfFileExists "$0\portable-version.json" octop_rt_find octop_rt_fail
octop_rt_find:
  ClearErrors
  FindFirst $1 $2 "$0\Octop-portable-*.zip"
  IfErrors octop_rt_fail
  StrCpy $3 "$INSTDIR\resources\sidecar"
  RMDir /r "$3"
  CreateDirectory "$3"
  StrCpy $4 "$WINDIR\Sysnative\tar.exe"
  IfFileExists "$4" octop_rt_extract 0
  StrCpy $4 "$WINDIR\System32\tar.exe"
  IfFileExists "$4" octop_rt_extract octop_rt_close_fail
octop_rt_extract:
  nsExec::ExecToLog '"$4" -xf "$0\$2" -C "$3" --strip-components=1'
  Pop $5
  FindClose $1
  StrCmp "$5" "0" octop_rt_check octop_rt_fail_closed
octop_rt_check:
  IfFileExists "$3\launch.py" 0 octop_rt_fail_closed
  IfFileExists "$3\runtime\python.exe" octop_rt_ok octop_rt_fail_closed
octop_rt_close_fail:
  FindClose $1
  Goto octop_rt_fail_closed
octop_rt_ok:
  Pop $5
  Pop $4
  Pop $3
  Pop $2
  Pop $1
  Pop $0
  Goto octop_rt_end
octop_rt_fail:
octop_rt_fail_closed:
  MessageBox MB_ICONSTOP "未能展开 Python 运行时（resources\sidecar）。$\r$\n安装已中止。"
  Pop $5
  Pop $4
  Pop $3
  Pop $2
  Pop $1
  Pop $0
  Abort
octop_rt_end:
!macroend

!macro customUnInstall
  RMDir /r "$INSTDIR\resources\sidecar"
!macroend
