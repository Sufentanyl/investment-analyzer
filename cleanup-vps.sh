#!/bin/bash
# ========================================
# VPS 清理脚本 - 安全版本 ⚠️
# 永远不会删除配置文件！
# ========================================

echo "========================================"
echo "  VPS 清理脚本（安全版）"
echo "========================================"
echo ""

cd ~/investment-analyzer

# ⚠️ 安全检查：确保重要文件存在
echo "🔒 安全检查..."
if [ ! -f .env ]; then
    echo "❌ 错误：.env 文件不存在！取消清理操作。"
    exit 1
fi

if [ ! -f docker-compose.yml ]; then
    echo "❌ 错误：docker-compose.yml 文件不存在！取消清理操作。"
    exit 1
fi

echo "✅ 安全检查通过"
echo ""

echo "📊 当前磁盘使用情况："
du -sh . 2>/dev/null || echo "计算中..."
echo ""

echo "🗑️ 清理不必要的文件..."
echo ""

# 1. 删除文档文件（但保留重要的）
echo "1️⃣ 删除文档文件..."
rm -f VPS部署指南.md Git设置图文指南.md BUGFIX_SUMMARY.md EMERGENCY-SECURITY-FIX.md 2>/dev/null && echo "   ✅ 已删除文档文件" || echo "   ⚠️ 没有找到文档文件"

# 2. 删除备份目录（但保留最近的一个）
echo "2️⃣ 删除旧备份目录（保留最新一个）..."
BACKUP_COUNT=$(ls -d ../backup-* 2>/dev/null | wc -l)
if [ $BACKUP_COUNT -gt 1 ]; then
    ls -td ../backup-* | tail -n +2 | xargs rm -rf
    echo "   ✅ 已删除旧备份"
else
    echo "   ⚠️ 没有足够的备份目录"
fi

# 3. 清理Python缓存
echo "3️⃣ 清理Python缓存..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null && echo "   ✅ 已删除 __pycache__" || echo "   ⚠️ 没有找到缓存文件"

# 4. 清理旧的日志文件（保留最近7天）
echo "4️⃣ 清理旧日志（保留最近7天）..."
find logs/ -name "*.log.*" -mtime +7 -delete 2>/dev/null && echo "   ✅ 已删除7天前的日志" || echo "   ⚠️ 没有旧日志"

# 5. 清理Docker镜像和容器
echo "5️⃣ 清理Docker资源..."
docker system prune -f > /dev/null 2>&1 && echo "   ✅ 已清理Docker缓存" || echo "   ⚠️ Docker清理失败"

# 6. 显示清理后的空间
echo ""
echo "========================================"
echo "✅ 清理完成！重要文件已保留"
echo "========================================"
echo ""
echo "📊 清理后磁盘使用情况："
du -sh . 2>/dev/null
echo ""

echo "🔒 保留的配置文件："
ls -lh .env config.yaml 2>/dev/null | awk '{print "   " $9 " (" $5 ")"}'
echo ""

echo "💡 提示：此脚本永远不会删除 .env、config.yaml、data/ 等重要文件"
echo ""
