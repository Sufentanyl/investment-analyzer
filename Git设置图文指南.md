# 🚀 Git 设置完整指南（新手友好版）

> 目标：把你本地的代码上传到 GitHub，实现一键同步

---

## 📋 准备工作检查清单

- [ ] 你的电脑已安装 Git ✅（已检测到 Git 2.52.0）
- [ ] 你有 GitHub 账号 ✅
- [ ] 你有科学上网环境 ✅
- [ ] 你知道自己的 GitHub 用户名和邮箱

---

## 🔐 第一步：获取 GitHub Personal Access Token（必须先做！）

### 为什么需要 Token？
GitHub 已经**不支持用密码**推送代码了，必须用 Token。

### 操作步骤（5 分钟）：

#### 1. 打开 Token 生成页面
- 访问：https://github.com/settings/tokens
- 如果提示登录，先登录你的 GitHub

#### 2. 点击生成新 Token
- 找到并点击按钮：**"Generate new token"** → **"Generate new token (classic)"**
- （可能在页面右上角或左侧）

#### 3. 填写 Token 信息
```
Name（名称）: investment-analyzer
Expiration（有效期）: 90 days  或  No expiration（永不过期）
```

#### 4. 勾选权限（重要！）
只勾选这一个就够了：
```
✅ repo  (这个会自动勾选下面的所有子选项)
   ✅ repo:status
   ✅ repo_deployment
   ✅ public_repo
   ✅ repo:invite
   ✅ security_events
```

⚠️ **不要**勾选 admin、gist等其他权限，安全第一！

#### 5. 生成并保存 Token
- 滚动到页面底部
- 点击绿色按钮：**"Generate token"**
- **重要**：复制显示的 Token（格式：`ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx`）
- 立即保存到记事本或密码管理器（**只显示一次！**）

💡 **Token 示例**：
```
ghp_1234567890abcdefghijklmnopqrstuvwxyz
```

---

## 🌐 第二步：在 GitHub 创建仓库

### 操作步骤（3 分钟）：

#### 1. 打开创建页面
- 访问：https://github.com/new

#### 2. 填写仓库信息
```
Repository name（仓库名）:
   investment-analyzer

Description（描述，可选）:
   AI 驱动的量化交易辅助系统

可见性（二选一）:
   ✅ Private  （私有仓库，推荐，别人看不到）
   或
   ✅ Public   （公开仓库，所有人可见）

下面的选项全部不要勾选：
   ❌ Add a README file
   ❌ Add .gitignore
   ❌ Choose a license
```

#### 3. 创建仓库
- 点击绿色按钮：**"Create repository"**

#### 4. 保存仓库地址
创建成功后，页面会显示你的仓库地址，格式类似：
```
https://github.com/你的用户名/investment-analyzer.git
```

**复制这个地址！** 一会儿要用到。

---

## 💻 第三步：运行自动化脚本

### 操作步骤（2 分钟）：

#### 1. 找到脚本文件
在你的项目文件夹中：
```
C:\Users\Jing\Desktop\CC\investment-analyzer\
```

找到文件：**`setup-git.bat`**

#### 2. 双击运行
- 直接双击 `setup-git.bat`
- 会弹出一个**黑色命令行窗口**

#### 3. 按提示输入信息

**提示1**：
```
请输入你的 GitHub 用户名（比如：zhangsan）：
```
→ 输入你的 GitHub 用户名，按回车

**提示2**：
```
请输入你的 GitHub 邮箱（比如：zhangsan@example.com）：
```
→ 输入你的 GitHub 邮箱，按回车

**提示3**：
```
请复制你的 GitHub 仓库地址：
```
→ 粘贴你在第二步复制的地址，按回车
→ 例如：`https://github.com/jingyibing/investment-analyzer.git`

**提示4**：
```
按任意键继续推送...
```
→ 按任意键继续

#### 4. 输入用户名和 Token

**窗口会提示**：
```
Username for 'https://github.com':
```
→ 输入你的 GitHub 用户名

**然后提示**：
```
Password for 'https://你的用户名@github.com':
```
→ ⚠️ **这里不要输入密码！**
→ 粘贴你刚才保存的 **Token**
→ （粘贴时看不到字符，这是正常的！）

#### 5. 等待完成

看到这些信息就成功了：
```
✅ Git 配置完成！
✅ 仓库初始化完成！
✅ 文件添加完成！
✅ 首次提交完成！
✅ 远程仓库连接完成！
🎉 完成！
```

---

## ✅ 第四步：验证上传成功

### 方法 1：在浏览器查看
- 访问：`https://github.com/你的用户名/investment-analyzer`
- 应该能看到你的所有文件

### 方法 2：检查本地 Git 状态
打开 Git Bash 或命令行，在项目目录执行：
```bash
git status
```
应该显示：
```
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
```

---

## 🎯 完成！以后的使用非常简单

### 📝 日常使用流程（修改代码后）

#### 在你的本地电脑：

1. **修改代码**（比如修改了 `main.py`）

2. **打开命令行**（Git Bash 或 CMD）

3. **执行这 3 条命令**：
```bash
git add .
git commit -m "描述你改了什么"
git push
```

**例子**：
```bash
git add .
git commit -m "优化了新闻收集逻辑"
git push
```

#### 在你的 VPS：

```bash
ssh root@your-vps-ip
cd ~/investment-analyzer
git pull
docker compose restart
```

**就这么简单！** 🎉

---

## ❓ 常见问题解答

### Q1: 脚本双击后一闪而过？
**A**: 右键点击 `setup-git.bat` → 选择"编辑"，确认最后一行是 `pause`，然后保存。

### Q2: 提示 "Permission denied（权限拒绝）"？
**A**:
- 检查 Token 是否正确复制
- 确认 Token 勾选了 `repo` 权限
- 重新生成一个 Token 试试

### Q3: 提示 "SSL certificate problem"？
**A**: 执行以下命令：
```bash
git config --global http.sslVerify false
```
然后重试 `git push`

### Q4: 忘记保存 Token 了？
**A**: Token 只显示一次，必须重新生成：
1. 访问 https://github.com/settings/tokens
2. 找到之前生成的 Token，点击 "Delete" 删除
3. 重新生成新的 Token

### Q5: Windows 凭据管理器记住的是旧密码？
**A**:
1. 打开"控制面板" → "用户账户" → "凭据管理器"
2. 找到 `git:https://github.com`
3. 删除或编辑，更新为新的 Token

---

## 📚 下一步学习（可选）

如果你想更深入了解 Git：
- **基础教程**：B 站搜索"Git 入门教程"
- **常用命令**：
  ```bash
  git log          # 查看提交历史
  git diff         # 查看修改了什么
  git reset        # 回退到之前的版本
  git branch       # 查看分支
  ```

---

## 🆘 遇到问题？

如果遇到任何问题，截图发给我，我会帮你解决！

**常见错误信息收集**：
- `fatal: Authentication failed` → Token 错误
- `fatal: remote origin already exists` → 远程仓库已存在
- `error: failed to push` → 网络或权限问题

---

**祝你顺利完成！** 💪
