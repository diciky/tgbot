#!/bin/bash
# 上传Docker镜像到DockerHub

# 设置您的DockerHub用户名
DOCKER_USERNAME="your-username"

# 确认
echo "您的DockerHub用户名是: $DOCKER_USERNAME"
read -p "确认继续? [y/N]: " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "操作取消"
  exit 1
fi

# 重新打标签
echo "正在为镜像打标签..."
docker tag tgbot $DOCKER_USERNAME/tgbot:latest

# 推送到DockerHub
echo "正在推送镜像到DockerHub..."
docker push $DOCKER_USERNAME/tgbot:latest

echo "操作完成!" 