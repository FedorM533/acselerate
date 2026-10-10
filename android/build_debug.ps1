# Сборка отладочного APK. Android Gradle Plugin не принимает пути с кириллицей,
# поэтому исходники копируются в ASCII-папку, собираются там, а APK возвращается сюда.
# Запуск: powershell -File build_debug.ps1   (нужны JAVA_HOME и ANDROID_HOME)
param([string]$Work = "C:\fs-build")

$src = $PSScriptRoot
robocopy $src $Work /E /XD build .gradle .idea /XF local.properties *.apk /NFL /NDL /NJH /NJS | Out-Null
Push-Location $Work
try {
    & .\gradlew.bat --console=plain testDebugUnitTest assembleDebug
    if ($LASTEXITCODE -ne 0) { throw "Сборка не удалась" }
    Copy-Item "$Work\app\build\outputs\apk\debug\app-debug.apk" "$src\FocusShield-debug.apk" -Force
    Write-Host "Готово: $src\FocusShield-debug.apk"
} finally {
    Pop-Location
}
