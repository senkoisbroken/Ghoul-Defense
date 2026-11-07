@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Ghoul Defense Setup

echo Running setup only. The helper will not be launched.
set "GHOUL_SETUP_ONLY=1"
set "GHOUL_FORCE_SETUP=1"
call "%~dp0start.bat"
exit /b %errorlevel%
