# 日程管理

一个基于 Flask + SQLite 的轻量日程应用。

## 功能
- 日程 / 待办 / 打卡
- 学年周数显示
- 主题皮肤 + 背景图
- 多用户 + 管理员
- 企业微信 Webhook 提醒

## 快速开始

### 本地运行
\`\`\`bash
pip install -r requirements.txt
python app.py
\`\`\`

### Docker 运行

修改 docker-compose.yml中的 SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
生成的字符串粘贴到SECRET_KEY，不要引号

\`\`\`
docker compose up -d
\`\`\`
