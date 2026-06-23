; Script Inno Setup — MacroDeck
; Généré automatiquement par le CI/CD GitHub Actions

#define MyAppName      "MacroDeck"
#define MyAppVersion   "15.1"
#define MyAppPublisher "Arthur"
#define MyAppURL       "https://github.com"
#define MyAppExeName   "MacroDeck.exe"
#define MyAppDataDir   "{userappdata}\MacroDeck"

[Setup]
AppId={{8F3C2A1B-4D5E-4F6A-9B0C-1D2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Pas de droits admin requis — installation dans Program Files si dispo, sinon AppData
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer_output
OutputBaseFilename=MacroDeck_Setup
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Désinstalleur enregistré dans Paramètres Windows > Applications
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; Créer un entrée "Ajouter/Supprimer des programmes"
CreateUninstallRegKey=yes
; Ne pas redémarrer Windows après install
RestartIfNeededByRun=no
; Architecture x64
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Cases à cocher pendant l'installation
Name: "desktopicon";    Description: "Créer un raccourci sur le Bureau";          GroupDescription: "Raccourcis :"; Flags: unchecked
Name: "startmenuicon";  Description: "Créer un raccourci dans le Menu Démarrer";  GroupDescription: "Raccourcis :"; Flags: checkedonce
Name: "startup";        Description: "Lancer MacroDeck au démarrage de Windows";  GroupDescription: "Options :";    Flags: unchecked

[Files]
; Tout le dossier PyInstaller --onedir
Source: "dist\MacroDeck\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Menu Démarrer
Name: "{group}\{#MyAppName}";            Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}";          Tasks: startmenuicon
; Bureau
Name: "{autodesktop}\{#MyAppName}";      Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Lancement automatique au démarrage Windows (HKCU — pas besoin d'admin)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#MyAppName}"; \
  ValueData: """{app}\{#MyAppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: startup

[Run]
; Proposer de lancer l'app à la fin de l'installation
Filename: "{app}\{#MyAppExeName}"; \
  Description: "Lancer {#MyAppName} maintenant"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Tuer le processus avant désinstallation si il tourne
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillMacroDeck"

[UninstallDelete]
; Nettoyer le dossier plugins créé à l'exécution (à côté de l'exe)
Type: filesandordirs; Name: "{app}\plugins"
