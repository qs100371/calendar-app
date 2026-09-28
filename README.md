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
\`\`\`bash
cp .env.example .env
# 修改 .env 中的 SECRET_KEY
docker compose up -d
\`\`\`

## 环境变量
| 变量 | 说明 | 默认值 |
|---|---|---|
| SECRET_KEY | Flask 会话密钥（必须设置） | dev-secret-key-change-me |
| DATABASE_PATH | SQLite 数据库路径 | calendar.db |