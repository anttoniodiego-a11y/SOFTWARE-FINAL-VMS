@echo off
title Instalador de Dependencias - INTERFACE SOFTWARE VMS
cd /d "%~dp0"

echo ========================================================
echo       Instalando Dependencias do SOFTWARE VMS
echo ========================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao foi encontrado no sistema ou nao esta no PATH.
    echo.
    echo Para continuar, instale o Python 3.10, 3.11 ou 3.12:
    echo 1. Baixe em: https://www.python.org/downloads/
    echo 2. ATENCAO: Marque a opcao "Add python.exe to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

echo Python detectado:
python --version
echo.

echo [1/2] Atualizando o pip...
python -m pip install --upgrade pip

echo.
echo [2/2] Instalando bibliotecas necessarias (PyQt6, OpenCV, NumPy)...
python -m pip install -r requirements.txt

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo   [SUCESSO] Todas as dependencias foram instaladas!
    echo   Para abrir o sistema, execute o arquivo: iniciar_vms.bat
    echo ========================================================
) else (
    echo.
    echo [ERRO] Ocorreu uma falha durante a instalacao das dependencias.
    echo Verifique sua conexao com a internet e tente novamente.
)

echo.
pause
