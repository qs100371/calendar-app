# 1. 基础镜像
FROM python:3.10-slim

# 2. 设置时区
ENV TZ=Asia/Shanghai

# 3. 更换为国内 apt 源（清华源），并安装工具
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null; \
    apt-get update && apt-get install -y --no-install-recommends \
    cron \
    tzdata \
    nano \
    procps \
    vim \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 4. 设置时区软链接
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 5. 业务代码
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .

# 6. 配置 crontab（每天 20:00 执行提醒）
RUN echo "0 20 * * * root /usr/local/bin/python /app/notify.py >> /proc/1/fd/1 2>&1" > /etc/cron.d/my-cron \
    && chmod 0644 /etc/cron.d/my-cron

# 7. 启动脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "app.py"]