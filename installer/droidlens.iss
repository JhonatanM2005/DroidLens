; Script de Inno Setup para DroidLens
; Genera DroidLens-Setup.exe con instalación per-user e instalación opcional de driver con UAC

#define MyAppName "DroidLens"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "DroidLens Project"
#define MyAppURL "https://github.com/JhonatanM2005/DroidLens"
#define MyAppExeName "DroidLens.exe"

[Setup]
AppId={{D819C48B-A324-4B2D-9B8A-7012354A0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=DroidLens-Setup-v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "installdriver"; Description: "Instalar driver de cámara virtual DirectShow (Recomendado)"; GroupDescription: "Componentes del sistema:"

[Files]
Source: "..\dist\DroidLens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\driver\*"; DestDir: "{app}\driver"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Registrar driver como Administrador únicamente si el usuario marcó la tarea
Filename: "{app}\driver\install_driver.bat"; Parameters: ""; StatusMsg: "Registrando filtro de cámara virtual UnityCapture..."; Flags: runascurrentuser shellexec waituntilterminated; Tasks: installdriver
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\driver\uninstall_driver.bat"; Parameters: ""; StatusMsg: "Desinstalando filtro de cámara virtual..."; Flags: runascurrentuser shellexec waituntilterminated; RunOnceId: "UninstallDroidLensDriver"
