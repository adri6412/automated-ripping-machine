; Inno Setup script for Automated Ripping Machine.
; Build: ISCC.exe /DMyAppVersion=1.0.0 installer\AutoRipMachine.iss
; Requires the PyInstaller output in dist\AutoRipMachine (see build.bat / CI workflow).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyAppName "Automated Ripping Machine"
#define MyAppExe "AutoRipMachine.exe"
#define PowerShell "{sys}\WindowsPowerShell\v1.0\powershell.exe"
#define DepsScript "{app}\setup\install-deps.ps1"

[Setup]
AppId={{8C2F6B1E-5A4D-4C7B-9E1F-3D2A6B7C8E90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=adri6412
AppPublisherURL=https://github.com/adri6412/automated-ripping-machine
AppSupportURL=https://github.com/adri6412/automated-ripping-machine/issues
DefaultDirName={autopf}\AutoRipMachine
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=AutoRipMachine-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Types]
Name: "full"; Description: "Completa: app + tutti i programmi esterni (consigliata)"
Name: "compact"; Description: "Solo l'app (i programmi esterni li installi tu)"
Name: "custom"; Description: "Personalizzata"; Flags: iscustom

[Components]
Name: "app"; Description: "Automated Ripping Machine"; Types: full compact custom; Flags: fixed
Name: "deps"; Description: "Programmi esterni (scaricati da Internet durante l'installazione)"; Types: full
Name: "deps\makemkv"; Description: "MakeMKV - decifra e rippa DVD, Blu-ray e 4K UHD (+ chiave beta)"; Types: full
Name: "deps\cyanrip"; Description: "cyanrip - rip bit-perfect dei CD audio"; Types: full

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Avvia l'app all'accesso a Windows"; GroupDescription: "Opzioni:"; Flags: unchecked

[Files]
Source: "..\dist\AutoRipMachine\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "install-deps.ps1"; DestDir: "{app}\setup"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Aggiorna programmi esterni"; Filename: "{#PowerShell}"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{#DepsScript}"" -InstallDir ""{app}"""; \
  Comment: "Scarica le ultime versioni di MakeMKV (e della chiave beta) e di cyanrip"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon
Name: "{autostartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: autostart

[Run]
Filename: "{#PowerShell}"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{#DepsScript}"" -InstallDir ""{app}"" {code:DepSwitches}"; \
  StatusMsg: "Download e installazione dei programmi esterni (può richiedere alcuni minuti)..."; \
  Flags: waituntilterminated; Check: HasDeps
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Programs downloaded by install-deps.ps1 (MakeMKV has its own uninstaller).
Type: filesandordirs; Name: "{app}\tools"

[Code]
function DepSwitches(Param: String): String;
begin
  Result := '';
  if WizardIsComponentSelected('deps\cyanrip') then Result := Result + ' -Cyanrip';
  if WizardIsComponentSelected('deps\makemkv') then Result := Result + ' -MakeMKV';
  if (Result <> '') and WizardSilent then Result := Result + ' -NoPause';
end;

function HasDeps: Boolean;
begin
  Result := DepSwitches('') <> '';
end;
