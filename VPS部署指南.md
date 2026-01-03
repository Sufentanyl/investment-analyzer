# 🚀 VPS Git 配置完整指南

> VPS: 104.129.11.185
> 项目: investment-analyzer + media-brain

---

## 📋 准备工作

**需要的信息**：
- [ ] VPS IP 地址：`104.129.11.185` ✅
- [ ] VPS root 密码：`__________`（你需要填写）
- [ ] GitHub 用户名：`Sufentanyl`（你需要填写）
- [ ] GitHub 邮箱：`__________`（你需要填写）
- [ ] GitHub 仓库地址：`https://github.com/Sufentanyl/investment-analyzer.git`
- [ ] GitHub Token（可选，用于推送代码）：`__________`

---

## 🎯 方案选择

### 方案 A：自动配置脚本（推荐）⭐
**适合**：想一次性完成所有配置

**优点**：
- ✅ 自动安装 Git
- ✅ 自动配置信息
- ✅ 自动更新代码
- ✅ 自动安装更新脚本

**缺点**：
- 需要复制脚本到 VPS

---

### 方案 B：手动分步配置
**适合**：想了解每一步做了什么

**优点**：
- ✅ 完全掌控每一步
- ✅ 出错容易定位

**缺点**：
- 需要执行多个命令

---

## 📝 方案 A：自动配置（5 分钟）

### 第一步：上传脚本到 VPS

**方法 1：使用 WinSCP（推荐新手）**
1. 打开 WinSCP
2. 连接到 VPS：
   - IP: `104.129.11.185`
   - 端口: `22`
   - 用户名: `root`
   - 密码: 你的 VPS 密码
3. 找到本地文件：
   - `setup-vps.sh`
   - `update-all.sh`
4. 拖拽到远程的 `/root/` 目录

**方法 2：使用 SCP 命令**
```bash
# 在本地项目目录打开 PowerShell/CMD
scp setup-vps.sh root@104.129.11.185:~/
scp update-all.sh root@104.129.11.185:~/
```

### 第二步：SSH 登录 VPS

```bash
ssh root@104.129.11.185
# 输入密码
```

### 第三步：运行配置脚本

```bash
cd ~
chmod +x setup-vps.sh
./setup-vps.sh
```

### 第四步：按提示输入信息

脚本会问你：

**提示 1**：
```
GitHub Username:
```
→ 输入你的 GitHub 用户名，按回车

**提示 2**：
```
GitHub Email:
```
→ 输入你的 GitHub 邮箱，按回车

**提示 3**：
```
GitHub Token (press Enter to skip):
```
→ 如果你不想从 VPS 推送代码，直接按回车跳过
→ 如果需要推送，粘贴你的 Token，按回车

**提示 4**：
```
Your GitHub repository URL:
```
→ 粘贴你的仓库地址：`https://github.com/你的用户名/investment-analyzer.git`

### 第五步：等待完成

脚本会自动：
- ✅ 检查/安装 Git
- ✅ 配置 Git 用户信息
- ✅ 保存 Token（如果提供）
- ✅ 更新 investment-analyzer 代码
- ✅ 重启容器
- ✅ 安装一键更新脚本

看到 "Setup Completed!" 就成功了！

---

## 📝 方案 B：手动分步配置（10 分钟）

### 第一步：SSH 登录 VPS

```bash
ssh root@104.129.11.185
```

### 第二步：安装 Git

```bash
# 检查是否已安装
git --version

# 如果显示 "command not found"，执行：
apt-get update
apt-get install -y git
```

### 第三步：配置 Git

```bash
# 替换成你的信息
git config --global user.name "你的GitHub用户名"
git config --global user.email "你的GitHub邮箱"
```

### 第四步：更新 investment-analyzer

```bash
cd ~/investment-analyzer

# 备份当前代码（以防万一）
cp -r src src.backup

# 如果已经是 Git 仓库
git remote set-url origin https://github.com/你的用户名/investment-analyzer.git
git pull origin main

# 如果还不是 Git 仓库
git init
git remote add origin https://github.com/你的用户名/investment-analyzer.git
git pull origin main

# 重启容器
docker compose restart
```

### 第五步：配置 media-brain（可选）

```bash
cd ~/media-brain

# 如果你想把 media-brain 也加入 Git 管理
git init
git add .
git commit -m "Initial commit"

# 然后在 GitHub 创建新仓库，关联并推送
git remote add origin https://github.com/你的用户名/media-brain.git
git push -u origin main
```

### 第六步：安装一键更新脚本

```bash
# 上传 update-all.sh 到 VPS（用 WinSCP 或 scp）
chmod +x ~/update-all.sh
```

---

## ✅ 验证配置成功

### 1. 检查 Git 状态

```bash
cd ~/investment-analyzer
git status
```

应该显示：
```
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
```

### 2. 检查容器运行状态

```bash
docker ps
```

应该看到：
```
CONTAINER ID   IMAGE                      STATUS
investment-analyzer      ...   Up X minutes
media-brain              ...   Up X minutes
```

### 3. 测试一键更新

```bash
~/update-all.sh
```

应该看到：
```
========================================
  Auto Update All Projects
========================================

[1/2] Updating investment-analyzer...
  ✓ Code updated
  ✓ Containers restarted
✓ investment-analyzer updated successfully!

[2/2] Updating media-brain...
  ✓ Containers restarted
✓ media-brain updated successfully!

========================================
All updates completed!
========================================
```

---

## 🎯 以后的使用（超简单！）

### 更新所有项目

```bash
~/update-all.sh
```

### 只更新 investment-analyzer

```bash
cd ~/investment-analyzer
git pull
docker compose restart
```

### 只更新 media-brain

```bash
cd ~/media-brain
docker compose restart
```

### 查看日志

```bash
# investment-analyzer
docker logs -f investment-analyzer

# media-brain
docker logs -f media-brain
```

---

## 💡 常见问题

### Q1: 提示 "Permission denied (publickey)"
**A**: Git 没有权限，检查 Token 是否正确配置

### Q2: 提示 "fatal: remote origin already exists"
**A**:
```bash
cd ~/investment-analyzer
git remote remove origin
git remote add origin https://github.com/你的用户名/investment-analyzer.git
```

### Q3: git pull 失败，提示代码冲突
**A**:
```bash
# 备份当前修改
cp -r src src.backup
# 强制更新
git fetch origin
git reset --hard origin/main
```

### Q4: 容器重启失败
**A**:
```bash
# 查看详细错误
docker compose logs
# 检查配置文件
docker compose config
```

---

## 📊 性能影响说明

Git 对你的 VPS 性能影响：

| 项目 | 占用 | 说明 |
|------|------|------|
| 磁盘 | +10MB | .git 目录大小 |
| 内存 | 0MB | 不运行时不占用 |
| CPU | 1-3秒 | 只在 git pull 时占用 |
| 网络 | 几KB/s | 只在更新时传输 |

**结论**：完全可以忽略，放心使用！✅

---

## 🎓 下一步学习

### 给 media-brain 也加上 Git

```bash
cd ~/media-brain
git init
git add .
git commit -m "Initial commit"

# 去 GitHub 创建新仓库
git remote add origin https://github.com/你的用户名/media-brain.git
git push -u origin main
```

### 添加更多项目

编辑 `~/update-all.sh`，在最后添加：

```bash
# 更新第三个项目
echo "[3/3] Updating third-project..."
cd ~/third-project
git pull
docker compose restart
```

---

**准备好配置了吗？选择方案 A（自动）或方案 B（手动）开始吧！** 🚀
