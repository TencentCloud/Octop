#ifndef MyAppVersion
#define MyAppVersion "0.0.0-dev"
#endif

#ifndef SourceDir
#define SourceDir "..\..\dist\Octop"
#endif

#define MyAppName "Octop"
#define MyAppPublisher "Octop Contributors"
#define MyAppExeName "Octop.exe"

[Setup]
AppId={{9DFEFAB4-7071-4E9C-8C19-01F30682B6DD}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Octop
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no
OutputDir=..\..\dist\installer
OutputBaseFilename=Octop-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function IsWebView2RuntimeInstalled: Boolean;
begin
  Result :=
    RegKeyExists(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F1C3BB35-1C0A-4E7D-8B16-8EF336A6B3E4}') or
    RegKeyExists(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F1C3BB35-1C0A-4E7D-8B16-8EF336A6B3E4}') or
    RegKeyExists(HKLM64, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F1C3BB35-1C0A-4E7D-8B16-8EF336A6B3E4}');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not IsWebView2RuntimeInstalled) then
  begin
    MsgBox(
      'Octop uses Microsoft Edge WebView2 to display the desktop window.' + #13#10 +
      'If Octop does not open on this computer, install the WebView2 Runtime from Microsoft and launch Octop again.',
      mbInformation,
      MB_OK
    );
  end;
end;
