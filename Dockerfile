FROM python:3.11-slim

WORKDIR /app

# 先装依赖（利用缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 数据卷，持久化 SQLite 数据
VOLUME ["/app/data"]

# 默认数据库路径（会被 docker-compose 的 env 覆盖）
ENV DATABASE_PATH=/app/data/calendar.db

# SECRET_KEY 仅占位，请通过运行时环境变量传入真实值
# 生成方式：python -c "import secrets; print(secrets.token_hex(32))"
ENV SECRET_KEY=please-override-me-in-runtime

EXPOSE 5000

CMD ["python", "app.py"]