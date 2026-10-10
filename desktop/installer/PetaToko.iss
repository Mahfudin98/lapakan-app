; Installer Peta Toko untuk Windows (Inno Setup 6).
; Build: lihat desktop\build.ps1. Parameter wajib: /DStageDir=<folder hasil staging> /DOutDir=<folder keluaran>
; Per-pengguna (tanpa hak administrator). Database dibuat saat instalasi.

#define AppName "Peta Toko"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef StageDir
  #error StageDir belum diberikan (gunakan build.ps1)
#endif
#ifndef OutDir
  #define OutDir "..\dist"
#endif
#define Launcher "runtime\PetaToko.exe"
#define PythonExe "runtime\python.exe"

[Setup]
AppId={{341D125E-EEFF-4051-9D25-C45D815AE522}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Peta Toko
DefaultDirName={autopf}\PetaToko
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutDir}
OutputBaseFilename=PetaToko-Setup-{#AppVersion}
SetupIconFile=..\assets\petatoko.ico
UninstallDisplayIcon={app}\assets\petatoko.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
UsePreviousAppDir=yes
CloseApplications=no
RestartApplications=no
ExtraDiskSpaceRequired=1073741824
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} - instalasi
UninstallDisplayName={#AppName}

[Languages]
Name: "id"; MessagesFile: "Indonesian.isl"

[CustomMessages]
id.DataPageTitle=Lokasi data
id.DataPageDesc=Di mana database dan hasil pencarian disimpan?
id.DataPageHint=Data Anda (database toko dan log) disimpan di folder ini, terpisah dari program sehingga aman saat aplikasi diperbarui. Disarankan membiarkan lokasi bawaan.
id.DataDirPlaceholder=Lokasi bawaan (nama folder memuat karakter khusus)
id.DataDirInvalid=Folder data tidak valid atau tidak dapat ditulis:%n%1%n%nPilih folder lain.
id.DataDirInside=Folder data tidak boleh berada di dalam folder program.
id.TaskDesktop=Buat pintasan di Desktop
id.TaskAutostart=Jalankan Peta Toko di latar belakang saat Windows dimulai
id.StatusDb=Menyiapkan database (hanya sekali, 1-2 menit)...
id.DbFailed=Database belum berhasil disiapkan:%n%n%1%n%nPeta Toko sudah terpasang dan akan mencoba lagi otomatis saat dibuka pertama kali (perlu koneksi internet bila Chromium harus diunduh).%n%nRincian: %2
id.RunApp=Buka Peta Toko sekarang
id.KeepDeleteData=Hapus juga data Anda (database toko dan hasil pencarian) di:%n%1%n%nPilih Tidak untuk menyimpannya (disarankan bila Anda berniat memasang ulang).

[Tasks]
Name: "desktopicon"; Description: "{cm:TaskDesktop}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:TaskAutostart}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; pembaruan: buang file versi lama agar tidak ada sisa (data pengguna ada di folder terpisah)
Type: filesandordirs; Name: "{app}\backend"
Type: filesandordirs; Name: "{app}\frontend"
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\pgsql"
Type: filesandordirs; Name: "{app}\assets"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#Launcher}"; Parameters: "-m app.desktop.launcher"; WorkingDir: "{app}\backend"; IconFilename: "{app}\assets\petatoko.ico"; Comment: "Cari dan telusuri data toko dari Google Maps"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#Launcher}"; Parameters: "-m app.desktop.launcher"; WorkingDir: "{app}\backend"; IconFilename: "{app}\assets\petatoko.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PetaToko"; ValueData: """{app}\{#Launcher}"" -m app.desktop.launcher --background"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#Launcher}"; Parameters: "-m app.desktop.launcher"; WorkingDir: "{app}\backend"; Description: "{cm:RunApp}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#PythonExe}"; Parameters: "-m app.desktop.launcher --stop"; WorkingDir: "{app}\backend"; Flags: runhidden waituntilterminated; RunOnceId: "StopPetaToko"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  SEE_MASK_NOCLOSEPROCESS = $00000040;
  SEE_MASK_FLAG_NO_UI = $00000400;  { tanpa dialog galat sistem: mode senyap tidak boleh menunggu klik }
  WAIT_TIMEOUT = $00000102;
  SETUP_TIMEOUT_MS = 1500000; { 25 menit: batas atas yang sangat longgar }

type
  TShellExecuteInfo = record
    cbSize: DWORD;
    fMask: DWORD;
    Wnd: HWND;
    lpVerb: String;
    lpFile: String;
    lpParameters: String;
    lpDirectory: String;
    nShow: Integer;
    hInstApp: THandle;
    lpIDList: DWORD;
    lpClass: String;
    hkeyClass: THandle;
    dwHotKey: DWORD;
    hMonitor: THandle;
    hProcess: THandle;
  end;

function ShellExecuteEx(var lpExecInfo: TShellExecuteInfo): BOOL;
  external 'ShellExecuteExW@shell32.dll stdcall';
function WaitForSingleObject(hHandle: THandle; dwMilliseconds: DWORD): DWORD;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function GetExitCodeProcess(hProcess: THandle; var lpExitCode: DWORD): BOOL;
  external 'GetExitCodeProcess@kernel32.dll stdcall';
function CloseHandle(hObject: THandle): BOOL;
  external 'CloseHandle@kernel32.dll stdcall';

var
  DataPage: TInputDirWizardPage;
  UninstallDataDir: String;
  DataDirInitial: String;  { nilai awal sebenarnya (Unicode utuh) }
  DataEditInitial: String; { apa yang ditampilkan kontrol input untuk nilai awal itu (mungkin lossy) }

{ ---------- util ----------
  PERINGATAN: di Pascal Script Inno, Copy(), Trim(), dan Lowercase() MENGUBAH karakter non-Latin menjadi '?'
  (teruji: nama folder berhuruf Sirilik). Pos, penyambungan, akses per karakter, RemoveBackslashUnlessRoot, FmtMessage
  dan StringChangeEx aman. Untuk teks yang dapat memuat path pengguna, pakai pembantu di bawah, bukan fungsi itu. }
function SubStr(const S: String; From: Integer): String;  { dari karakter ke-From sampai akhir }
var
  I: Integer;
begin
  Result := '';
  for I := From to Length(S) do
    Result := Result + S[I];
end;

function IsBlank(C: Char): Boolean;
begin
  Result := (C = ' ') or (C = #9) or (C = #13) or (C = #10);
end;

function TrimUni(const S: String): String;
var
  First, Last, I: Integer;
begin
  First := 1;
  Last := Length(S);
  while (First <= Last) and IsBlank(S[First]) do First := First + 1;
  while (Last >= First) and IsBlank(S[Last]) do Last := Last - 1;
  Result := '';
  for I := First to Last do
    Result := Result + S[I];
end;

function FoldAscii(C: Char): Char;
begin
  if (C >= 'A') and (C <= 'Z') then Result := Chr(Ord(C) + 32) else Result := C;
end;

{ awalan path tanpa memedulikan huruf besar/kecil ASCII (karakter lain dibandingkan apa adanya) }
function PathStartsWith(const Path, Prefix: String): Boolean;
var
  I: Integer;
begin
  Result := Length(Path) >= Length(Prefix);
  if not Result then Exit;
  for I := 1 to Length(Prefix) do
    if FoldAscii(Path[I]) <> FoldAscii(Prefix[I]) then
    begin
      Result := False;
      Exit;
    end;
end;

function ParamPresent(const Name: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Name) = 0 then
      Result := True;
end;

function ReadFirstLine(const FileName: String): String;
var
  Lines: TArrayOfString;
begin
  Result := '';
  if LoadStringsFromFile(FileName, Lines) and (GetArrayLength(Lines) > 0) then
    Result := TrimUni(Lines[0]);
end;

function DefaultDataDir: String;
begin
  Result := ExpandConstant('{localappdata}\PetaToko');
end;

{ Mengisi nilai awal folder data. Kontrol input mengubah karakter non-Latin menjadi '?', yang ditolak validasi
  bawaan; bila nilai tidak bisa ditampilkan utuh, tampilkan teks pengganti yang aman dan simpan nilai sebenarnya. }
procedure SetDataDirInitial(const Path: String);
begin
  DataDirInitial := Path;
  DataPage.Values[0] := Path;
  DataEditInitial := DataPage.Values[0];
  if DataEditInitial <> DataDirInitial then
  begin
    DataEditInitial := ExpandConstant('{cm:DataDirPlaceholder}');
    DataPage.Values[0] := DataEditInitial;
  end;
end;

{ nilai parameter baris perintah /NAMA=nilai (untuk instalasi senyap), atau Default }
function CmdParam(const Name, Default: String): String;
var
  I, J, P: Integer;
  Arg, Key: String;
begin
  Result := Default;
  for I := 1 to ParamCount do
  begin
    Arg := ParamStr(I);
    P := Pos('=', Arg);
    if P > 0 then
    begin
      Key := '';
      for J := 1 to P - 1 do
        Key := Key + Arg[J];  { nama parameter selalu ASCII }
      if CompareText(Key, Name) = 0 then
        Result := TrimUni(SubStr(Arg, P + 1));
    end;
  end;
end;

function SelectedDataDir: String;
begin
  { pengguna tidak mengubah isian: pakai nilai awal yang utuh; bila diubah: pakai isian pengguna }
  if DataPage.Values[0] = DataEditInitial then
    Result := RemoveBackslashUnlessRoot(TrimUni(DataDirInitial))
  else
    Result := RemoveBackslashUnlessRoot(TrimUni(DataPage.Values[0]));
end;

{ Menjalankan program tersembunyi dan menunggu selesai sambil memberi kesempatan UI memperbarui progres. }
function RunHiddenWithProgress(const FileName, Params, WorkDir, ProgressFile: String; var ExitCode: DWORD): Boolean;
var
  Info: TShellExecuteInfo;
  Elapsed: Integer;
  Lines: TArrayOfString;
  I, P1, P2, Step, Total: Integer;
  Line, Msg, Rest: String;
begin
  Result := False;
  ExitCode := 1;
  Info.cbSize := SizeOf(Info);
  Info.fMask := SEE_MASK_NOCLOSEPROCESS or SEE_MASK_FLAG_NO_UI;
  Info.Wnd := 0;
  Info.lpVerb := 'open';
  Info.lpFile := FileName;
  Info.lpParameters := Params;
  Info.lpDirectory := WorkDir;
  Info.nShow := SW_HIDE;
  Info.hInstApp := 0;
  Info.lpIDList := 0;
  Info.lpClass := '';
  Info.hkeyClass := 0;
  Info.dwHotKey := 0;
  Info.hMonitor := 0;
  Info.hProcess := 0;
  if not ShellExecuteEx(Info) then Exit;
  if Info.hProcess = 0 then Exit;

  Elapsed := 0;
  while WaitForSingleObject(Info.hProcess, 0) = WAIT_TIMEOUT do
  begin
    Elapsed := Elapsed + 250;
    if Elapsed > SETUP_TIMEOUT_MS then Break;
    { baca baris STEP|n|total|pesan terakhir dari berkas progres }
    if LoadStringsFromFile(ProgressFile, Lines) then
    begin
      for I := GetArrayLength(Lines) - 1 downto 0 do
      begin
        Line := TrimUni(Lines[I]);
        if Pos('STEP|', Line) = 1 then
        begin
          Rest := SubStr(Line, 6);
          P1 := Pos('|', Rest);
          Step := StrToIntDef(Copy(Rest, 1, P1 - 1), 0);  { angka: ASCII, Copy aman }
          Rest := SubStr(Rest, P1 + 1);
          P2 := Pos('|', Rest);
          Total := StrToIntDef(Copy(Rest, 1, P2 - 1), 8);
          Msg := SubStr(Rest, P2 + 1);
          WizardForm.StatusLabel.Caption := ExpandConstant('{cm:StatusDb}');
          WizardForm.FilenameLabel.Caption := '(' + IntToStr(Step) + '/' + IntToStr(Total) + ') ' + Msg;
          if Total > 0 then
          begin
            WizardForm.ProgressGauge.Max := Total;
            WizardForm.ProgressGauge.Position := Step;
          end;
          Break;
        end;
      end;
    end;
    Sleep(250);  { memberi jendela instalasi kesempatan menggambar ulang }
  end;
  if WaitForSingleObject(Info.hProcess, 0) = WAIT_TIMEOUT then
    Result := False  { melewati batas waktu }
  else
    Result := GetExitCodeProcess(Info.hProcess, ExitCode);
  CloseHandle(Info.hProcess);
end;

function LastErrorLine(const ProgressFile: String): String;
var
  Lines: TArrayOfString;
  I: Integer;
begin
  Result := '';
  if LoadStringsFromFile(ProgressFile, Lines) then
    for I := GetArrayLength(Lines) - 1 downto 0 do
      if Pos('ERROR|', TrimUni(Lines[I])) = 1 then
      begin
        Result := SubStr(TrimUni(Lines[I]), 7);
        Exit;
      end;
end;

procedure RunDatabaseSetup;
var
  ProgressFile, Params, DataDir: String;
  ExitCode: DWORD;
  Ran: Boolean;
begin
  DataDir := SelectedDataDir;
  ProgressFile := ExpandConstant('{tmp}\peta-toko-setup.txt');
  DeleteFile(ProgressFile);
  Params := '-m app.desktop.setup --progress-file "' + ProgressFile + '"';
  WizardForm.StatusLabel.Caption := ExpandConstant('{cm:StatusDb}');
  WizardForm.ProgressGauge.Min := 0;
  WizardForm.ProgressGauge.Max := 8;
  WizardForm.ProgressGauge.Position := 0;
  Log('Menjalankan setup database: ' + Params);
  Ran := RunHiddenWithProgress(ExpandConstant('{app}\{#PythonExe}'), Params, ExpandConstant('{app}\backend'),
                               ProgressFile, ExitCode);
  Log('Setup database selesai: ran=' + IntToStr(Integer(Ran)) + ' exit=' + IntToStr(ExitCode));
  if (not Ran) or (ExitCode <> 0) then
  begin
    if not WizardSilent then
      MsgBox(FmtMessage(ExpandConstant('{cm:DbFailed}'), [LastErrorLine(ProgressFile), DataDir + '\logs\setup.log']),
             mbInformation, MB_OK);
  end;
end;

{ ---------- halaman data ---------- }
procedure InitializeWizard;
begin
  DataPage := CreateInputDirPage(wpSelectDir, ExpandConstant('{cm:DataPageTitle}'),
    ExpandConstant('{cm:DataPageDesc}'), ExpandConstant('{cm:DataPageHint}'), False, '');
  DataPage.Add('');
  SetDataDirInitial(CmdParam('/DATADIR', DefaultDataDir));
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Previous: String;
begin
  { pembaruan: pakai kembali lokasi data pemasangan sebelumnya }
  if CurPageID = DataPage.ID then
  begin
    Previous := ReadFirstLine(WizardDirValue + '\data-location.txt');
    if (Previous <> '') and (DataDirInitial = DefaultDataDir) and (SelectedDataDir = DefaultDataDir) then
    begin
      SetDataDirInitial(Previous);
    end;
  end;
end;

function DataDirWritable(const Dir: String): Boolean;
var
  Probe: String;
begin
  Result := False;
  if (Length(Dir) < 4) or (Pos(':\', Dir) <> 2) then Exit;  { harus path absolut berdrive }
  if not ForceDirectories(Dir) then Exit;
  Probe := Dir + '\.tulis-uji';
  Result := SaveStringToFile(Probe, 'ok', False);
  if Result then DeleteFile(Probe);
end;

{ Kosong bila valid; selain itu pesan galat untuk pengguna. }
function ValidateDataDir(const Dir, AppDir: String): String;
begin
  Result := '';
  if PathStartsWith(Dir + '\', RemoveBackslashUnlessRoot(AppDir) + '\') then
    Result := ExpandConstant('{cm:DataDirInside}')
  else if not DataDirWritable(Dir) then
    Result := FmtMessage(ExpandConstant('{cm:DataDirInvalid}'), [Dir]);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Msg: String;
begin
  Result := True;
  if CurPageID = DataPage.ID then
  begin
    Msg := ValidateDataDir(SelectedDataDir, WizardDirValue);
    if Msg <> '' then
    begin
      MsgBox(Msg, mbError, MB_OK);
      Result := False;
    end;
  end;
end;

{ ---------- instalasi ---------- }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  PythonPath: String;
begin
  Result := ValidateDataDir(SelectedDataDir, WizardDirValue);
  if Result <> '' then Exit;
  { pembaruan: hentikan Peta Toko yang sedang berjalan sebelum file diganti }
  PythonPath := ExpandConstant('{app}\{#PythonExe}');
  if FileExists(PythonPath) then
  begin
    Log('Menghentikan instance yang berjalan');
    Exec(PythonPath, '-m app.desktop.launcher --stop', ExpandConstant('{app}\backend'), SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Lines: TArrayOfString;
begin
  if CurStep = ssPostInstall then
  begin
    { lokasi data dipakai oleh peluncur, setup, dan uninstaller. UTF-8 agar nama folder berkarakter non-Latin aman. }
    SetArrayLength(Lines, 1);
    Lines[0] := SelectedDataDir;
    SaveStringsToUTF8File(ExpandConstant('{app}\data-location.txt'), Lines, False);
    RunDatabaseSetup;
  end;
end;

{ ---------- uninstall ---------- }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Answer: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    UninstallDataDir := ReadFirstLine(ExpandConstant('{app}\data-location.txt'));
    if UninstallDataDir = '' then UninstallDataDir := DefaultDataDir;
  end
  else if CurUninstallStep = usPostUninstall then
  begin
    if not DirExists(UninstallDataDir) then Exit;
    if ParamPresent('/DELETEDATA') then
      DelTree(UninstallDataDir, True, True, True)
    else if not UninstallSilent then
    begin
      Answer := MsgBox(FmtMessage(ExpandConstant('{cm:KeepDeleteData}'), [UninstallDataDir]),
                       mbConfirmation, MB_YESNO or MB_DEFBUTTON2);
      if Answer = IDYES then
        DelTree(UninstallDataDir, True, True, True);
    end;
  end;
end;
