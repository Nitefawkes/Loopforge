@echo off
echo LoopForge Execution Script
echo =======================

if "%1"=="" (
    echo No command specified. Available commands:
    echo.
    echo   setup         - Install Python dependencies
    echo   generate      - Generate prompts only
    echo   render        - Run the renderer only
    echo   process       - Run the video processor only
    echo   upload        - Run the uploader only
    echo   pipeline      - Run the entire pipeline
    echo   api           - Start the API prototype
    echo.
    echo Example usage: run_loopforge.bat generate --topic "minimalist lifestyle" --count 10
    exit /b 1
)

set COMMAND=%1
shift

if "%COMMAND%"=="setup" (
    echo Installing Python dependencies...
    pip install -r requirements.txt
    exit /b 0
)

if "%COMMAND%"=="generate" (
    echo Running prompt generation...
    python src\run_pipeline.py --stage generate %*
    exit /b 0
)

if "%COMMAND%"=="render" (
    echo Running renderer...
    python src\run_pipeline.py --stage render %*
    exit /b 0
)

if "%COMMAND%"=="process" (
    echo Running video processor...
    python src\run_pipeline.py --stage process %*
    exit /b 0
)

if "%COMMAND%"=="upload" (
    echo Running uploader...
    python src\run_pipeline.py --stage upload %*
    exit /b 0
)

if "%COMMAND%"=="pipeline" (
    echo Running full pipeline...
    python src\run_pipeline.py --all %*
    exit /b 0
)

if "%COMMAND%"=="api" (
    echo Starting API prototype...
    python src\run_pipeline.py --stage api %*
    exit /b 0
)

echo Unknown command: %COMMAND%
echo Run without parameters to see available commands
exit /b 1
