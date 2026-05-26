[Setup]
#ifndef AppSourceDir
#define AppSourceDir "..\..\dist\source-package"
#endif

#ifndef BuildOutputDir
#define BuildOutputDir "..\..\dist"
#endif

AppId={{F9D61BE7-0F93-4C60-8AD6-9B18A1DFB027}
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
Name: "{autoprograms}\Customer Agent"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\portable_launcher.pyw"""; WorkingDir: "{app}"
Name: "{autodesktop}\Customer Agent"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\portable_launcher.pyw"""; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\portable_launcher.pyw"""; WorkingDir: "{app}"; Description: "Launch Customer Agent"; Flags: nowait postinstall skipifsilent
