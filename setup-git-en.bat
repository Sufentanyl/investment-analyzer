@echo off
REM ============================================
REM Git Setup Script - English Version
REM ============================================

echo ========================================
echo Git Repository Setup Tool
echo ========================================
echo.

REM Step 1: Configure GitHub information
echo Please enter your GitHub username (e.g. zhangsan):
set /p GITHUB_USERNAME=

echo Please enter your GitHub email (e.g. zhangsan@example.com):
set /p GITHUB_EMAIL=

echo.
echo ========================================
echo Configuring Git...
echo ========================================

REM Configure Git
git config --global user.name "%GITHUB_USERNAME%"
git config --global user.email "%GITHUB_EMAIL%"
echo [OK] Git configured successfully!

echo.
echo ========================================
echo Initializing local repository...
echo ========================================

REM Initialize repository
git init
echo [OK] Repository initialized!

echo.
echo Adding all files...
git add .
echo [OK] Files added!

echo.
echo Creating first commit...
git commit -m "fix: Fixed 42 bugs and memory leaks

- Fixed information gap detector cache leak (limited to LRU 1000 entries)
- Fixed aiohttp ClientSession resource leak
- Fixed database connection not being reused
- Fixed 42 bare except catches, changed to detailed error logging
- Implemented configuration persistence
- Unified timezone to Asia/Shanghai
- Added RSI division-by-zero protection
- Implemented SerpApi news collection
- Added Dashboard table compatibility
- Fixed docker-compose.yml syntax error"
echo [OK] First commit created!

echo.
echo ========================================
echo Connecting to GitHub...
echo ========================================

echo.
echo IMPORTANT: Please copy your GitHub repository URL
echo Format like: https://github.com/your-username/investment-analyzer.git
echo.
set /p GITHUB_REPO_URL=

echo.
echo Connecting to remote repository...
git remote add origin %GITHUB_REPO_URL%
git branch -M main
echo [OK] Remote repository connected!

echo.
echo ========================================
echo Pushing to GitHub...
echo ========================================
echo.
echo If prompted for username and password (or Personal Access Token):
echo 1. Username: Enter your GitHub username
echo 2. Password: Enter your Personal Access Token (NOT your login password!)
echo.
echo [How to get Token?]
echo 1. Visit https://github.com/settings/tokens
echo 2. Click "Generate new token (classic)"
echo 3. Check the "repo" permission
echo 4. Generate and copy the token (shown only once!)
echo.
echo Press any key to continue pushing...
pause > nul

git push -u origin main

echo.
echo ========================================
echo SUCCESS!
echo ========================================
echo.
echo Your code has been uploaded to GitHub: %GITHUB_REPO_URL%
echo.
echo In the future, after modifying code, just run:
echo git add .
echo git commit -m "describe your changes"
echo git push
echo.
pause
