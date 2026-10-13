; Установщик Carpo (Inno Setup 6). Сборка: scripts\build_windows.ps1
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppName=Carpo
AppVersion={#AppVersion}
AppPublisher=Carpo
DefaultDirName={autopf}\Carpo
DefaultGroupName=Carpo
OutputDir=..\dist
OutputBaseFilename=Carpo-Setup-{#AppVersion}
SetupIconFile=..\focusfarm\web\brand\favicon.ico
UninstallDisplayIcon={app}\Carpo.exe
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Files]
Source: "..\dist\Carpo\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Carpo"; Filename: "{app}\Carpo.exe"
Name: "{autodesktop}\Carpo"; Filename: "{app}\Carpo.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Carpo.exe"; Description: "Запустить Carpo"; Flags: nowait postinstall skipifsilent

; Данные пользователя (база, правила, журнал) лежат в %APPDATA%\Carpo и при удалении программы остаются.
