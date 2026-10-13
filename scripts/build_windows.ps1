# Сборка Carpo для Windows: папка dist\Carpo, zip и (если установлен Inno Setup) Carpo-Setup.exe.
# Запуск из корня проекта:  powershell -File scripts\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Нет .venv: сначала запусти run.bat один раз" }

& $py -m pip install --quiet pyinstaller
& $py -m pip install --quiet -r requirements.txt

$version = (Select-String -Path "focusfarm\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Собираю Carpo $version..."

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $py -m PyInstaller carpo.spec --noconfirm --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller не справился" }

$zip = "dist\Carpo-$version-windows.zip"
Compress-Archive -Path "dist\Carpo" -DestinationPath $zip -Force
Write-Host "Готов zip: $zip"

$iscc = @("$env:ProgramFiles (x86)\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc "/DAppVersion=$version" "installer\carpo.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup не справился" }
    Write-Host "Готов установщик: dist\Carpo-Setup-$version.exe"
} else {
    Write-Host "Inno Setup не найден: установщик не собран (скачай с jrsoftware.org/isdl.php). Zip готов."
}
