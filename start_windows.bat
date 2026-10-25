@echo off
chcp 65001 >nul
title STV SPORT - Installation et lancement
cd /d "%~dp0"
echo ========================================
echo          STV SPORT V3 - DEMARRAGE
echo ========================================
where python >nul 2>nul
if errorlevel 1 (
 echo Python est introuvable. Installez Python 3.11 ou 3.12 depuis python.org
 echo ^(cochez "Add Python to PATH"^)
 pause
 exit /b 1
)
if not exist .venv (
 echo Creation de l'environnement...
 python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installation des dependances...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
 echo Echec de l'installation des dependances.
 pause
 exit /b 1
)
echo.
echo STV SPORT demarre sur http://127.0.0.1:8000
echo Documentation API : http://127.0.0.1:8000/docs
echo.
echo Le mot de passe admin est dans ADMIN_MOT_DE_PASSE.txt (cree au 1er lancement).
echo Fermez cette fenetre pour arreter le serveur.
echo.
start "" http://127.0.0.1:8000
uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
