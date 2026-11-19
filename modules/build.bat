@echo off
setlocal

set "PROJECT_ROOT=%~dp0.."
for %%I in ("%~dp0.") do set "BAT_DIR=%%~fI\"
set "TOOLCHAIN_ROOT=%PROJECT_ROOT%\toolchain"
set "ZIG_EXE="
set "ZIG_DIR="
set "SOURCE_FILE="
set "MODULE_NAME="
set "MODULE_ROOT="
set "OUTPUT_DIR="
set "BUILD_MODE="
set "DO_COMPILE=0"
set "DO_PACK=0"
set "PUSHED="
set "BUILD_EXIT_CODE="
set /a SOURCE_COUNT=0

echo Python files in %BAT_DIR%:
for %%F in ("%BAT_DIR%*.py") do if exist "%%~fF" call :list_source "%%~fF"
if "%SOURCE_COUNT%"=="0" (
    echo No Python source files were found beside this batch file.
    set "BUILD_EXIT_CODE=1"
    goto failed
)

echo.
set /p "SOURCE_CHOICE=Select a Python file by number: "
set /a SELECTED_SOURCE=0
for %%F in ("%BAT_DIR%*.py") do if exist "%%~fF" call :select_source "%%~fF"
if not defined SOURCE_FILE (
    echo Invalid Python file selection.
    set "BUILD_EXIT_CODE=1"
    goto failed
)

for %%I in ("%SOURCE_FILE%") do set "MODULE_NAME=%%~nI"
set "MODULE_ROOT=%BAT_DIR%%MODULE_NAME%"

echo.
echo Select build mode:
echo   1 / refresh - regenerate sources, update Python files in out\net48, remove packaged exe
echo   2 / compile - refresh + rebuild the C# DLL
echo   3 / pack    - compile + package the Python backend with Nuitka/Zig
set /p "MODE_CHOICE=Select mode (1/2/3 or refresh/compile/pack): "
if /I "%MODE_CHOICE%"=="1" set "BUILD_MODE=refresh"
if /I "%MODE_CHOICE%"=="refresh" set "BUILD_MODE=refresh"
if /I "%MODE_CHOICE%"=="2" set "BUILD_MODE=compile"
if /I "%MODE_CHOICE%"=="compile" set "BUILD_MODE=compile"
if /I "%MODE_CHOICE%"=="3" set "BUILD_MODE=pack"
if /I "%MODE_CHOICE%"=="pack" set "BUILD_MODE=pack"
if not defined BUILD_MODE (
    echo Invalid build mode selection.
    set "BUILD_EXIT_CODE=1"
    goto failed
)
if /I "%BUILD_MODE%"=="compile" set "DO_COMPILE=1"
if /I "%BUILD_MODE%"=="pack" (
    set "DO_COMPILE=1"
    set "DO_PACK=1"
)

if not exist "%MODULE_ROOT%" mkdir "%MODULE_ROOT%"
if errorlevel 1 goto failed
set "OUTPUT_DIR=%MODULE_ROOT%\out\net48"
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
if errorlevel 1 goto failed

pushd "%PROJECT_ROOT%"
if errorlevel 1 goto failed
set "PUSHED=1"

set "SOURCE_DATE_EPOCH=0"

rem Remove any executable packaged by a previous run before refreshing.
echo [%BUILD_MODE%] Removing stale packaged executable...
if exist "%OUTPUT_DIR%\%MODULE_NAME%_rpc.exe" del /Q "%OUTPUT_DIR%\%MODULE_NAME%_rpc.exe"
if exist "%MODULE_ROOT%\generated\python\%MODULE_NAME%_rpc.exe" del /Q "%MODULE_ROOT%\generated\python\%MODULE_NAME%_rpc.exe"

rem Every mode refreshes the generated sources first.
echo.
echo [%BUILD_MODE%] Refreshing generated sources for %MODULE_NAME%...
if "%DO_PACK%"=="1" (
    call :configure_zig
    if errorlevel 1 goto failed
    uv run --with nuitka python -m python_csharp_rpc_bridge.build_tools.build --source-file "%SOURCE_FILE%" --output-root "%MODULE_ROOT%" --nuitka --nuitka-zig
) else (
    uv run python -m python_csharp_rpc_bridge.build_tools.build --source-file "%SOURCE_FILE%" --output-root "%MODULE_ROOT%"
)
if errorlevel 1 goto failed

rem Copy the freshly generated Python sources into the output folder.
echo [%BUILD_MODE%] Updating Python source files in %OUTPUT_DIR%...
xcopy /Y /I /S "%MODULE_ROOT%\generated\python\*.py" "%OUTPUT_DIR%\" >nul
if errorlevel 1 goto failed

if "%DO_COMPILE%"=="1" (
    echo [%BUILD_MODE%] Building .NET Framework 4.8 DLL: %MODULE_NAME%.dll
    dotnet build src\csharp\ModulePlatform.csproj -c Release -o "%OUTPUT_DIR%" -p:PyfModuleName="%MODULE_NAME%" -p:PyfGeneratedDir="%MODULE_ROOT%\generated\csharp" -p:PyfBackendDir="%OUTPUT_DIR%"
    if errorlevel 1 goto failed
)

if "%DO_PACK%"=="1" (
    echo [%BUILD_MODE%] Copying Zig/Nuitka packaged executable to %OUTPUT_DIR%...
    copy /Y "%MODULE_ROOT%\generated\python\%MODULE_NAME%_rpc.exe" "%OUTPUT_DIR%\" >nul
    if errorlevel 1 goto failed
)

echo.
echo Build completed successfully (%BUILD_MODE%).
echo Generated sources: %MODULE_ROOT%\generated\
echo Build output:      %OUTPUT_DIR%\
if defined PUSHED popd
pause
exit /b 0

:list_source
set /a SOURCE_COUNT+=1
echo   %SOURCE_COUNT%. %~nx1
exit /b 0

:select_source
set /a SELECTED_SOURCE+=1
if "%SELECTED_SOURCE%"=="%SOURCE_CHOICE%" set "SOURCE_FILE=%~1"
exit /b 0

:configure_zig
set "ZIG_COUNT=0"
for /d %%D in ("%TOOLCHAIN_ROOT%\zig-*") do if exist "%%~fD\zig.exe" call :record_zig "%%~fD\zig.exe"
if "%ZIG_COUNT%"=="0" (
    echo No Zig compiler was found under %TOOLCHAIN_ROOT%\zig-*.
    echo Expected a path such as toolchain\zig-x86_64-windows-version\zig.exe.
    exit /b 1
)
if not "%ZIG_COUNT%"=="1" (
    echo Found %ZIG_COUNT% Zig compilers. Keep only one version under %TOOLCHAIN_ROOT%.
    exit /b 1
)
for %%I in ("%ZIG_EXE%") do set "ZIG_DIR=%%~dpI"
set "PATH=%ZIG_DIR%;%PATH%"
where zig.exe >nul 2>nul
if errorlevel 1 (
    echo Zig was not available on PATH after configuration.
    exit /b 1
)
exit /b 0

:record_zig
set /a ZIG_COUNT+=1
set "ZIG_EXE=%~1"
exit /b 0

:failed
if not defined BUILD_EXIT_CODE set "BUILD_EXIT_CODE=%errorlevel%"
if "%BUILD_EXIT_CODE%"=="0" set "BUILD_EXIT_CODE=1"
echo.
echo Build failed. Review the error messages above.
if defined PUSHED popd
pause
exit /b %BUILD_EXIT_CODE%