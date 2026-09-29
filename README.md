# 日程管理

一个基于 Flask + SQLite 的轻量级日程应用，支持多用户、主题皮肤、多渠道提醒。

## ✨ 功能特性

- 📅 **月历视图**：周一为第一天，支持学年周数或自然周数显示
- 📝 **三种事件类型**：日程 / 待办 / 打卡（打卡支持起止日期，可跨天追踪）
- 👥 **多用户系统**：第一个注册的用户自动成为管理员
- 🔐 **权限管理**：管理员可重置密码、设置管理员、删除用户
- 🎨 **主题皮肤**：内置 4 种配色（深邃暗夜 / 纯净白昼 / 护眼绿意 / 优雅紫罗兰）
- 🔔 **多渠道提醒**：企业微信 / 钉钉 / 飞书 / Bark / ntfy（可同时启用多个）
- 📱 **响应式布局**：电脑端左右分栏，手机端上下布局
- 🐳 **Docker 部署**：镜像自动构建，一条命令即可运行

---

## 🚀 快速开始

### 方式一：本地运行

```bash
pip install -r requirements.txt
python app.py
打开浏览器访问 http://localhost:5000

方式二：Docker 运行
bash
docker run -d \
  --name calendar \
  -p 8000:5000 \
  -v /path/to/data:/app/data \
  -e SECRET_KEY=你的随机密钥 \
  -e DATABASE_PATH=/app/data/calendar.db \
  --restart unless-stopped \
  ghcr.io/qs100371/calendar-app:latest
访问 http://localhost:8000

方式三：Docker Compose
docker-compose.yml：

yaml
services:
  calendar:
    image: ghcr.io/qs100371/calendar-app:latest
    container_name: calendar
    ports:
      - "8000:5000"
    volumes:
      - ./data:/app/data
    environment:
      - SECRET_KEY=你的随机密钥
      - DATABASE_PATH=/app/data/calendar.db
    restart: unless-stopped
bash
docker compose up -d
🔧 环境变量
变量名	说明	默认值
SECRET_KEY	Flask 会话密钥（部署必填）	dev-secret-key-change-me-in-production
DATABASE_PATH	SQLite 数据库文件路径	calendar.db
生成随机密钥：

bash
python -c "import secrets; print(secrets.token_hex(32))"
⚠️ 部署到公网前必须设置 SECRET_KEY，否则任何人都能伪造登录状态。
⚠️ SECRET_KEY 一旦上线不要随意更换，否则所有用户会被强制登出。

🔔 提醒渠道配置
所有渠道在「设置」弹窗中配置，可以同时启用多个，填了就发。留空则不启用该渠道。

1. 企业微信机器人
打开企业微信群 → 右上角 ⋯ → 群机器人 → 添加

选择「新创建一个机器人」，起个名字

复制生成的 Webhook 地址（形如 https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx）

粘贴到设置的「企业微信 Webhook」输入框中

2. 钉钉机器人
打开钉钉群 → 右上角 群设置 → 智能群助手 → 添加机器人 → 自定义

安全设置选 自定义关键词，关键词填 提醒（不要选加签）

复制 Webhook 地址（形如 https://oapi.dingtalk.com/robot/send?access_token=xxx）

粘贴到设置的「钉钉机器人 Webhook」输入框中

⚠️ 钉钉必须选「自定义关键词」模式，并在关键词中包含"提醒"，否则会发送失败。

3. 飞书机器人
打开飞书群 → 设置 → 群机器人 → 添加机器人 → 自定义机器人

复制 Webhook 地址（形如 https://open.feishu.cn/open-apis/bot/v2/hook/xxx）

粘贴到设置的「飞书机器人 Webhook」输入框中

4. Bark（iOS 推送）
iPhone 上从 App Store 安装 Bark App

打开 App，首页会显示一个专属推送地址（形如 https://api.day.app/xxxxxxxx）

复制这个地址，粘贴到设置的「Bark URL」输入框中

✅ 免费、无需注册、推送直达 iOS 系统通知。
⚠️ 仅支持 iOS。安卓用户请使用 ntfy。

5. ntfy（Android 推送）
在 Google Play 或 F-Droid 搜索并安装 ntfy App

打开 App，在订阅框输入一个只有你自己知道的 topic 名字，例如：

text
rili-qs100371-2026
点击订阅。

在设置的「ntfy Topic」输入框中填入同样的 topic 名（注意：只填名字，不填完整 URL）

✅ 免费、无需注册、安卓原生推送。
⚠️ topic 名字就是唯一凭证，建议用随机字符串（例如 rili-你的名字-日期），避免被陌生人订阅。
⚠️ 公共实例 ntfy.sh 每天限量 250 条消息，个人使用完全够。

📱 提醒渠道对比
渠道	平台	是否需要注册	免费额度	上手难度
企业微信	全平台	需要建群	无限制	⭐⭐
钉钉	全平台	需要建群	每分钟 20 条	⭐⭐
飞书	全平台	需要建群	无限制	⭐⭐
Bark	iOS	不需要	免费	⭐
ntfy	Android / iOS / Web	不需要	每天 250 条	⭐
推荐组合：

iOS 用户 → Bark（最省事）

Android 用户 → ntfy（最省事）

已有企业微信/钉钉/飞书团队 → 用对应机器人

📁 数据持久化
所有数据（用户、日程、打卡、设置）都保存在 SQLite 数据库文件里，位置由 DATABASE_PATH 决定。

Docker 部署时务必挂载数据卷：

yaml
volumes:
  - ./data:/app/data
备份：整个应用的所有数据都在一个 .db 文件里，直接复制即可：

bash
cp ./data/calendar.db ~/backup/calendar-$(date +%Y%m%d).db
恢复：

bash
cp ~/backup/calendar-20260929.db ./data/calendar.db
docker compose restart
👤 用户与权限
第一个注册的用户自动成为管理员

管理员功能：

查看所有用户列表

重置任意用户密码为 123456

设置/取消其他用户的管理员身份

删除任意用户（同时删除其所有数据）

普通用户功能：

修改自己的密码

删除自己的账号

系统保护：

不能修改自己的管理员身份

不能删除唯一的管理员

🎨 主题皮肤
设置中可在 4 种主题间切换：

深邃暗夜：默认，深灰色

纯净白昼：亮色模式

护眼绿意：深绿色调

优雅紫罗兰：深紫色调

主题偏好保存在用户设置中，每个用户独立。

🛠️ 技术栈
后端：Flask 3.x + SQLite

定时任务：APScheduler

密码加密：Werkzeug PBKDF2

前端：原生 HTML + CSS + JavaScript

部署：Docker + GitHub Actions + GHCR

📦 目录结构
text
calendar-app/
├── .github/
│   └── workflows/
│       └── docker.yml         # 自动构建 Docker 镜像
├── templates/
│   ├── index.html             # 主页面
│   └── login.html             # 登录/注册页
├── static/
│   └── style.css              # 样式
├── app.py                     # Flask 主程序
├── requirements.txt           # Python 依赖
├── Dockerfile                 # Docker 构建文件
├── docker-compose.yml         # Compose 配置
├── .dockerignore
├── .gitignore
└── README.md
🐳 镜像构建
推送到 GitHub 的 main 分支后，GitHub Actions 会自动：

构建 Docker 镜像

推送到 GitHub Container Registry

镜像地址：

text
ghcr.io/qs100371/calendar-app:latest
手动拉取（如果镜像是私有的，需要先登录）：

bash
echo $GITHUB_TOKEN | docker login ghcr.io -u qs100371 --password-stdin
docker pull ghcr.io/qs100371/calendar-app:latest
公开镜像（让任何人都能拉取）：
GitHub → 你的头像 → Packages → calendar-app → Package settings → Change visibility → Public

📄 License
MIT

text

---

## 主要新增的内容

相比之前的 README，这次加上了：

1. **✅ 功能特性**：明确列出 5 种提醒渠道
2. **🔔 提醒渠道配置**：**5 种渠道的详细步骤**（这是你要的重点）
   - 每种渠道都写了"从哪拿配置"、"填到哪"
   - 钉钉特别注意：必须用"自定义关键词"而不是"加签"
   - ntfy 特别注意：**只填 topic 名，不填 URL**
3. **📱 提醒渠道对比表**：帮用户快速选择
4. **🎨 主题皮肤说明**
5. **📁 数据持久化 + 备份恢复**

---
