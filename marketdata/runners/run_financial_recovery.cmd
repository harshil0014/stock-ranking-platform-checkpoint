@echo off
setlocal
cd /d "%~dp0\..\.."
set "RECOVERY_PACK=data\recovery_packs\official_financial_tail_20260908"
if not exist "%RECOVERY_PACK%\targets_manifest.json" (
  .venv-marketdata\Scripts\python.exe marketdata\runners\financial_recovery_pack.py init --pack "%RECOVERY_PACK%"
  if errorlevel 1 exit /b 1
)
.venv-marketdata\Scripts\python.exe marketdata\runners\financial_recovery_pack.py collect-financial --pack "%RECOVERY_PACK%" --limit 500
if errorlevel 1 exit /b 1
.venv-marketdata\Scripts\python.exe marketdata\runners\financial_recovery_pack.py collect-nse-cached --pack "%RECOVERY_PACK%" --catalogue data\company_facts\providers\official_exchange\official-backbone-20260822-07\raw\nse_financial_integrated.json --limit 10
if errorlevel 1 exit /b 1
.venv-marketdata\Scripts\python.exe marketdata\runners\financial_recovery_pack.py collect --pack "%RECOVERY_PACK%" --limit 500 --family shareholding
if errorlevel 1 exit /b 1
.venv-recovery\Scripts\python.exe marketdata\runners\review_recovery_ixbrl.py --pack "%RECOVERY_PACK%"
if errorlevel 1 exit /b 1
.venv-marketdata\Scripts\python.exe marketdata\runners\normalize_recovery_review.py --pack "%RECOVERY_PACK%"
if errorlevel 1 exit /b 1
.venv-marketdata\Scripts\python.exe marketdata\runners\check_recovery_numeric_transforms.py --pack "%RECOVERY_PACK%"
if errorlevel 1 exit /b 1
.venv-marketdata\Scripts\python.exe marketdata\runners\financial_recovery_pack.py report --pack "%RECOVERY_PACK%"
if errorlevel 1 exit /b 1
.venv-marketdata\Scripts\python.exe marketdata\runners\audit_financial_recovery_pack.py --pack "%RECOVERY_PACK%"
if errorlevel 1 exit /b 1
echo Recovery pack saved. Review-only: no data has been promoted to the website.
endlocal
