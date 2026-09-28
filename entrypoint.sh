#!/bin/bash

# 启动 cron 服务（后台运行）
# 注意：在 Docker 中，必须让 cron 作为后台进程运行，否则它会阻塞后续命令
service cron start

# 打印时间，方便排查时区问题
echo "Cron service started at $(date)"

# 执行 CMD 传来的命令（即 python app.py）
# exec 的作用是用 python 进程替换当前 shell，成为 PID 1，这样容器才不会退出
exec "$@"