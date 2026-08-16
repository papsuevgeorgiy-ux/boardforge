; Установщик BoardForge.
;
; Собирается программой Inno Setup 6 (https://jrsoftware.org/isdl.php):
; открыть этот файл и нажать Compile. Ожидает, что PyInstaller уже отработал
; и положил результат в dist\BoardForge.
;
; Результат — dist\BoardForge-Setup-1.0.exe: один файл, который человек
; скачивает, запускает и трижды нажимает «Далее».
;
; PrivilegesRequired=lowest — установка в папку пользователя, без прав
; администратора. Мастеру не придётся просить айтишника, а SmartScreen ругается
; на неподписанное приложение одинаково в обоих случаях.

; Inno Setup считает относительные пути от каталога этого файла, а сборка
; лежит в корне проекта. SourcePath — каталог скрипта, с завершающей обратной
; косой чертой; отсюда путь на уровень выше.
#define Root SourcePath + "..\\"

#define AppName "BoardForge"
#define AppVersion "1.0"
#define AppExe "BoardForge.exe"
#define AppPublisher "BoardForge"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Root}dist
OutputBaseFilename=BoardForge-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Files]
Source: "{#Root}dist\BoardForge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent
