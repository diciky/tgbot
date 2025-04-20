FROM python:3.11-slim

WORKDIR /app

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用程序代码
COPY . .

# 创建日志目录
RUN mkdir -p logs

# 暴露Web端口
ARG WEB_PORT=7000
ENV WEB_PORT=${WEB_PORT}
EXPOSE ${WEB_PORT}

# 设置入口点
CMD ["python", "main.py"] 