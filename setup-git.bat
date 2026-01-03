@echo off
REM ============================================
REM Git 初始化脚本 - 请先填写下面的信息
REM ============================================

echo ========================================
echo Git 仓库初始化工具
echo ========================================
echo.

REM 【第一步】配置你的 GitHub 信息
echo 请输入你的 GitHub 用户名（比如：zhangsan）：
set /p GITHUB_USERNAME=

echo 请输入你的 GitHub 邮箱（比如：zhangsan@example.com）：
set /p GITHUB_EMAIL=

echo.
echo ========================================
echo 正在配置 Git...
echo ========================================

REM 配置 Git
git config --global user.name "%GITHUB_USERNAME%"
git config --global user.email "%GITHUB_EMAIL%"
echo ✅ Git 配置完成！

echo.
echo ========================================
echo 正在初始化本地仓库...
echo ========================================

REM 初始化仓库
git init
echo ✅ 仓库初始化完成！

echo.
echo 正在添加所有文件...
git add .
echo ✅ 文件添加完成！

echo.
echo 正在创建首次提交...
git commit -m "fix: 修复42个bug和内存泄漏

- 修复信息差检测缓存泄漏（内存从无限增长改为LRU 1000条）
- 修复 aiohttp ClientSession 资源泄漏
- 修复数据库连接未复用问题
- 修复42处裸except捕获，改为详细错误日志
- 实现配置持久化保存
- 统一时区为Asia/Shanghai
- 添加RSI除零保护
- 实现SerpApi新闻收集功能
- 添加Dashboard数据表兼容性
- 修复docker-compose.yml语法错误"
echo ✅ 首次提交完成！

echo.
echo ========================================
echo 准备连接到 GitHub...
echo ========================================

echo.
echo 【重要】请复制你的 GitHub 仓库地址，格式类似：
echo https://github.com/你的用户名/investment-analyzer.git
echo.
set /p GITHUB_REPO_URL=

echo.
echo 正在连接到远程仓库...
git remote add origin %GITHUB_REPO_URL%
git branch -M main
echo ✅ 远程仓库连接完成！

echo.
echo ========================================
echo 准备推送到 GitHub...
echo ========================================
echo.
echo 如果提示输入用户名和密码（或Personal Access Token）：
echo 1. 用户名：输入你的 GitHub 用户名
echo 2. 密码：输入你的 Personal Access Token（不是登录密码！）
echo.
echo 【如何获取 Token？】
echo 1. 访问 https://github.com/settings/tokens
echo 2. 点击 "Generate new token (classic)"
echo 3. 勾选 repo 权限
echo 4. 生成后复制 token（只显示一次！）
echo.
echo 按任意键继续推送...
pause > nul

git push -u origin main

echo.
echo ========================================
echo 🎉 完成！
echo ========================================
echo.
echo 你的代码已经上传到 GitHub：%GITHUB_REPO_URL%
echo.
echo 以后每次修改代码后，只需执行：
echo git add .
echo git commit -m "描述你的修改"
echo git push
echo.
pause
