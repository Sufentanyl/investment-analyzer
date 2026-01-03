#!/bin/bash
# ========================================
# VPS 清理脚本 - 删除不必要的文件
# ========================================

echo "========================================"
echo "  VPS 清理脚本"
echo "========================================"
echo ""

cd ~/investment-analyzer

echo "📊 当前磁盘使用情况："
du -sh . 2>/dev/null || echo "计算中..."
echo ""

echo "🗑️ 清理不必要的文件..."
echo ""

# 1. 删除文档文件（保留README.md在GitHub，VPS不需要）
echo "1️⃣ 删除文档文件..."
rm -f *.md 2>/dev/null && echo "   ✅ 已删除所有 .md 文件" || echo "   ⚠️ 没有找到 .md 文件"

# 2. 删除备份目录
echo ""
echo "2️⃣ 删除备份目录..."
rm -rf src.backup.* 2>/dev/null && echo "   ✅ 已删除 src.backup 目录" || echo "   ⚠️ 没有找到备份目录"

# 3. 删除agent.sh（如果不再使用）
echo ""
echo "3️⃣ 删除旧脚本..."
rm -f agent.sh 2>/dev/null && echo "   ✅ 已删除 agent.sh" || echo "   ⚠️ 没有找到 agent.sh"

# 4. 清理Python缓存
echo ""
echo "4️⃣ 清理Python缓存..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null && echo "   ✅ 已删除 __pycache__" || echo "   ⚠️ 没有找到缓存文件"

# 5. 清理旧的日志文件（保留最近7天）
echo ""
echo "5️⃣ 清理旧日志（保留最近7天）..."
find logs/ -name "*.log.*" -mtime +7 -delete 2>/dev/null && echo "   ✅ 已删除7天前的日志" || echo "   ⚠️ 没有旧日志"

# 6. 清理Docker镜像和容器
echo ""
echo "6️⃣ 清理Docker资源..."
docker system prune -f > /dev/null 2>&1 && echo "   ✅ 已清理Docker缓存" || echo "   ⚠️ Docker清理失败"

# 7. 显示清理后的空间
echo ""
echo "========================================"
echo "✅ 清理完成！"
echo "========================================"
echo ""
echo "📊 清理后磁盘使用情况："
du -sh . 2>/dev/null
echo ""

echo "💾 当前目录文件列表："
ls -lh | grep -v "^d"
echo ""

echo "🔄 提示：以后在本地更新代码后，执行以下命令同步到VPS："
echo "   git pull"
echo "   docker compose restart"
echo ""
