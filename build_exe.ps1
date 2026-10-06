# Builds dist\TeamsCaptionLogger.exe (single file, no Python needed to run it).
# Run from the repo folder:  powershell -ExecutionPolicy Bypass -File build_exe.ps1
$ErrorActionPreference = 'Stop'
$python = '.\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    py -m venv .venv
    & $python -m pip install -r requirements.txt
}
& $python -m pip install --quiet pyinstaller
& $python -m unittest test_caption_logic.py test_caption_uia.py
if ($LASTEXITCODE) { throw 'Tests failed; not building.' }
# mss/Pillow are only used by the OCR version; leaving them out keeps the exe smaller.
& $python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name TeamsCaptionLogger `
    --collect-all uiautomation `
    --collect-data docx `
    --exclude-module PIL --exclude-module mss `
    teams_caption_gui.py
if ($LASTEXITCODE) { throw 'PyInstaller failed.' }
Get-Item dist\TeamsCaptionLogger.exe | Select-Object FullName, @{n='MB'; e={[math]::Round($_.Length / 1MB, 1)}}
