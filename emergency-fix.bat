@echo off
REM ============================================
REM 紧急安全修复脚本
REM 立即从 GitHub 删除敏感文件
REM ============================================

echo ========================================
echo   EMERGENCY SECURITY FIX
echo   Removing sensitive files from Git
echo ========================================
echo.

echo [Step 1/5] Creating .gitignore to prevent future leaks...
echo.

(
echo # ========================================
echo # 敏感配置文件（绝对不能上传）
echo # ========================================
echo .env
echo .env.local
echo .env.*.local
echo config.yaml
echo config.yml
echo user_config.json
echo secrets.yaml
echo secrets.yml
echo.
echo # ========================================
echo # 数据文件
echo # ========================================
echo data/
echo data/*
echo !data/.gitkeep
echo *.db
echo *.sqlite
echo *.sqlite3
echo.
echo # ========================================
echo # 日志文件
echo # ========================================
echo logs/
echo logs/*
echo *.log
echo.
echo # ========================================
echo # Python 相关
echo # ========================================
echo __pycache__/
echo *.py[cod]
echo venv/
echo .venv
) > .gitignore

echo [OK] .gitignore created
echo.

echo [Step 2/5] Removing sensitive files from Git tracking...
echo.

git rm --cached .env 2>nul
git rm --cached config.yaml 2>nul
git rm --cached data/user_config.json 2>nul
git rm --cached -r data/ 2>nul
git rm --cached -r logs/ 2>nul

echo [OK] Files removed from Git tracking
echo.

echo [Step 3/5] Committing the changes...
echo.

git add .gitignore
git commit -m "security: Remove sensitive files and add .gitignore

- Removed .env from Git tracking (contains API keys)
- Removed config.yaml from Git tracking
- Removed user_config.json from Git tracking
- Added comprehensive .gitignore to prevent future leaks"

echo [OK] Changes committed
echo.

echo [Step 4/5] Pushing to GitHub...
echo.

git push origin main

echo [OK] Pushed to GitHub
echo.

echo ========================================
echo   SECURITY FIX COMPLETED!
echo ========================================
echo.
echo IMPORTANT: Follow these steps NOW:
echo.
echo 1. Check your GitHub repository:
echo    https://github.com/Sufentanyl/investment-analyzer
echo.
echo 2. Verify these files are DELETED:
echo    - .env
echo    - config.yaml
echo    - data/user_config.json
echo.
echo 3. If still visible, your keys are COMPROMISED!
echo    You MUST regenerate all API keys:
echo.
echo    - Telegram Bot Token
echo    - DeepSeek API Key
echo    - Qwen API Key
echo    - Gemini API Keys
echo    - SerpApi Key
echo.
echo 4. After regenerating, update .env on VPS:
echo    ssh root@104.129.11.185
echo    cd ~/investment-analyzer
echo    nano .env
echo.
echo 5. Restart containers:
echo    docker compose restart
echo.
pause
