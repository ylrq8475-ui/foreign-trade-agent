[Setup]
#ifndef AppSourceDir
#define AppSourceDir "..\..\dist\CustomerAgent"
#endif

#ifndef BuildOutputDir
#define BuildOutputDir "..\..\dist"
#endif

AppId={{9A7EA630-22D1-4B67-B6C9-3A4B40E50654}
AppName=Customer Agent
AppVersion=1.0.0
AppPublisher=Your Company
DefaultDirName={autopf}\Customer Agent
DefaultGroupName=Customer Agent
DisableProgramGroupPage=yes
OutputDir={#BuildOutputDir}
OutputBaseFilename=CustomerAgentSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "{#AppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Customer Agent"; Filename: "{app}\CustomerAgent.exe"
Name: "{autodesktop}\Customer Agent"; Filename: "{app}\CustomerAgent.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CustomerAgent.exe"; Description: "Launch Customer Agent"; Flags: nowait postinstall skipifsilent
