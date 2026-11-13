[Setup]
AppId={{612B6D70-B3F7-4C97-96E5-188651D38103}
AppName=TonyPlotPy
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\TonyPlotPy
DefaultGroupName=TonyPlotPy
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=TonyPlotPy-Setup-{#AppVersion}-x64
SetupIconFile={#ProjectDir}\imgs\tonyplotpy.ico
UninstallDisplayIcon={app}\TonyPlotPy.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ProjectDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\TonyPlotPy"; Filename: "{app}\TonyPlotPy.exe"
Name: "{autodesktop}\TonyPlotPy"; Filename: "{app}\TonyPlotPy.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TonyPlotPy.exe"; Description: "Launch TonyPlotPy"; Flags: nowait postinstall skipifsilent
