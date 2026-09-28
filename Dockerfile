# 1. 使用官方 Python 镜像
FROM python:3.10-slim

# 2. 安装 cron 和时区数据
RUN apt-get update && apt-get install -y cron tzdata && rm -rf /var/lib/apt/lists/*

# 3. 设置时区为北京时间
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 4. 设置工作目录并复制代码
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# 5. 配置 crontab (Debian/Ubuntu 系统路径是 /etc/cron.d/)
# 假设你的提醒脚本是 /app/notify.py，并且你想每天 20:00 执行
RUN echo "0 20 * * * root /usr/local/bin/python /app/notify.py >> /proc/1/fd/1 2>&1" > /etc/cron.d/my-cron
RUN chmod 0644 /etc/cron.d/my-cron

# 6. 复制启动脚本并赋予权限
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 7. 使用 entrypoint.sh 启动
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "app.py"]