; The desktop shortcut is chosen on the finish page, so installSection must
; not create it first (createDesktopShortcut: false). Silent installs still
; write the .lnk here.
;
; electron-builder compiles the uninstaller as a second makensis pass
; (-DBUILD_UNINSTALLER, warnings are errors). That pass includes this file
; but does not expand the installer macros, so these Vars must not be
; allocated there or makensis exits with warning 6001.
!ifndef BUILD_UNINSTALLER
Var OctopDesktopLabel
!endif

; common.nsh sets ShowInstDetails nevershow, which removes the details button.
; hide keeps the log collapsed until the user expands it on the progress page.
; The function is defined here, after LogicLib is loaded. The uninstaller
; keeps ShowUninstDetails nevershow and does not get this function.
!macro customHeader
  !ifndef BUILD_UNINSTALLER
    ShowInstDetails hide

    Function octopAppFilesCopied
      !insertmacro octopDetailsOn
      IntCmp $LANGUAGE 2052 octop_files_zh octop_files_en octop_files_en
octop_files_zh:
      DetailPrint "应用程序文件已写入。"
      Goto octop_files_done
octop_files_en:
      DetailPrint "Application files copied."
octop_files_done:
    FunctionEnd
  !endif
!macroend

!macro octopDetailsOn
  ${IfNot} ${Silent}
    ; installSection sets this to none, which drops DetailPrint entirely.
    ; textonly only updates the status line above the progress bar, so the
    ; details list stays empty. both fills that list and the status line.
    ; CopyFiles /SILENT and a quiet tar keep the runtime's files out of it.
    SetDetailsPrint both
  ${EndIf}
!macroend

; Do not define customFiles_<arch>. electron-builder emits that macro when
; resources contain a precompressed file (resources/portable/*.zip) and uses
; it to pack the zip. A second definition aborts makensis with
; "macro named customFiles_x64 already exists". customInstall prints the
; copied-files line after that macro has run.

!macro octopWriteDesktopLink
  CreateShortCut "$newDesktopLink" "$appExe" "" "$appExe" 0 "" "" "${APP_DESCRIPTION}"
  ClearErrors
  WinShell::SetLnkAUMI "$newDesktopLink" "${APP_ID}"
  System::Call 'Shell32::SHChangeNotify(i 0x8000000, i 0, i 0, i 0)'
!macroend

; Finish page: keep "run" and add the desktop-shortcut checkbox.
; Fresh installs start checked. Updates start unchecked so a removed
; shortcut is not put back unless the user asks.
!macro customFinishPage
  !define MUI_PAGE_CUSTOMFUNCTION_PRE octopFinishPre
  !define MUI_PAGE_CUSTOMFUNCTION_SHOW octopFinishShow
  !define MUI_FINISHPAGE_RUN
  !define MUI_FINISHPAGE_RUN_FUNCTION StartApp
  !define MUI_FINISHPAGE_SHOWREADME
  !define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
  !define MUI_FINISHPAGE_SHOWREADME_TEXT "$OctopDesktopLabel"
  !define MUI_FINISHPAGE_SHOWREADME_FUNCTION octopCreateDesktopShortcut
  !insertmacro MUI_PAGE_FINISH

  Function octopFinishPre
    IntCmp $LANGUAGE 2052 octop_fin_zh octop_fin_en octop_fin_en
octop_fin_zh:
    StrCpy $OctopDesktopLabel "创建桌面快捷方式"
    Goto octop_fin_pre_end
octop_fin_en:
    StrCpy $OctopDesktopLabel "Create a desktop shortcut"
octop_fin_pre_end:
  FunctionEnd

  Function octopFinishShow
    ${IfNot} ${isUpdated}
      ${NSD_Check} $mui.FinishPage.ShowReadme
    ${EndIf}
  FunctionEnd

  Function StartApp
    ${If} ${isUpdated}
      StrCpy $1 "--updated"
    ${Else}
      StrCpy $1 ""
    ${EndIf}
    ${StdUtils.ExecShellAsUser} $0 "$launchLink" "open" "$1"
  FunctionEnd

  Function octopCreateDesktopShortcut
    !insertmacro octopWriteDesktopLink
  FunctionEnd
!macroend

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
  !insertmacro octopDetailsOn
  IntCmp $LANGUAGE 2052 octop_run_log_zh octop_run_log_en octop_run_log_en
octop_run_log_zh:
  DetailPrint "正在安装应用程序文件…"
  Goto octop_run_log_done
octop_run_log_en:
  DetailPrint "Installing application files…"
octop_run_log_done:
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
  !insertmacro octopDetailsOn
  Call octopAppFilesCopied
  IntCmp $LANGUAGE 2052 octop_rt_log_zh octop_rt_log_en octop_rt_log_en
octop_rt_log_zh:
  DetailPrint "正在展开 Python 运行时…"
  Goto octop_rt_log_done
octop_rt_log_en:
  DetailPrint "Extracting the Python runtime…"
octop_rt_log_done:
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
  IntCmp $LANGUAGE 2052 octop_rt_tar_zh octop_rt_tar_en octop_rt_tar_en
octop_rt_tar_zh:
  DetailPrint "正在将 $2 写入 resources\sidecar…"
  Goto octop_rt_tar_run
octop_rt_tar_en:
  DetailPrint "Writing $2 to resources\sidecar…"
octop_rt_tar_run:
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
  ; Same directory the desktop shell passes as PYTHONPYCACHEPREFIX. Compile
  ; here so the first launch does not write bytecode. A failure only skips
  ; the warmup; the extracted tree is already usable.
  ReadEnvStr $5 OCTOP_HOME
  StrCmp $5 "" 0 octop_pyc_home
  StrCpy $5 "$PROFILE\.octop"
octop_pyc_home:
  CreateDirectory "$5\pyc"
  System::Call 'Kernel32::SetEnvironmentVariable(t "PYTHONPYCACHEPREFIX", t "$5\pyc")'
  StrCpy $4 "$3\runtime\python.exe"
  IntCmp $LANGUAGE 2052 octop_pyc_zh octop_pyc_en octop_pyc_en
octop_pyc_zh:
  DetailPrint "正在编译 Python 字节码到 $5\pyc…"
  Goto octop_pyc_run
octop_pyc_en:
  DetailPrint "Compiling Python bytecode into $5\pyc…"
octop_pyc_run:
  nsExec::ExecToLog '"$4" -m compileall -q -j0 "$3\packages"'
  Pop $4
  System::Call 'Kernel32::SetEnvironmentVariable(t "PYTHONPYCACHEPREFIX", p 0)'
  StrCmp $4 "0" octop_pyc_ready octop_pyc_warn
octop_pyc_warn:
  IntCmp $LANGUAGE 2052 octop_pyc_warn_zh octop_pyc_warn_en octop_pyc_warn_en
octop_pyc_warn_zh:
  DetailPrint "字节码编译未完成（$4）。首次启动会再编译。"
  Goto octop_pyc_ready
octop_pyc_warn_en:
  DetailPrint "Bytecode compile did not finish ($4). The first launch will compile it."
octop_pyc_ready:
  IntCmp $LANGUAGE 2052 octop_rt_ok_zh octop_rt_ok_en octop_rt_ok_en
octop_rt_ok_zh:
  DetailPrint "Python 运行时已就绪。"
  Goto octop_rt_ok_done
octop_rt_ok_en:
  DetailPrint "Python runtime is ready."
octop_rt_ok_done:
  Pop $5
  Pop $4
  Pop $3
  Pop $2
  Pop $1
  Pop $0
  ${If} ${Silent}
  ${AndIfNot} ${isNoDesktopShortcut}
  ${AndIf} $keepShortcuts == "false"
    !insertmacro octopWriteDesktopLink
  ${EndIf}
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
  IfFileExists "$newDesktopLink" 0 octop_un_old_link
    WinShell::UninstShortcut "$newDesktopLink"
    Delete "$newDesktopLink"
octop_un_old_link:
  IfFileExists "$oldDesktopLink" 0 octop_un_sidecar
    WinShell::UninstShortcut "$oldDesktopLink"
    Delete "$oldDesktopLink"
octop_un_sidecar:
  RMDir /r "$INSTDIR\resources\sidecar"
  ; pyc is a cache inside the user-data directory. Drop only that directory;
  ; the next install runs compileall again. Database, workspace, and config stay.
  Push $0
  ReadEnvStr $0 OCTOP_HOME
  StrCmp $0 "" 0 octop_un_pyc_dir
  StrCpy $0 "$PROFILE\.octop"
octop_un_pyc_dir:
  StrCmp $0 "" octop_un_pyc_done
  IntCmp $LANGUAGE 2052 octop_un_pyc_zh octop_un_pyc_en octop_un_pyc_en
octop_un_pyc_zh:
  DetailPrint "正在删除字节码缓存 $0\pyc…"
  Goto octop_un_pyc_rm
octop_un_pyc_en:
  DetailPrint "Removing bytecode cache $0\pyc…"
octop_un_pyc_rm:
  RMDir /r "$0\pyc"
octop_un_pyc_done:
  Pop $0
!macroend
