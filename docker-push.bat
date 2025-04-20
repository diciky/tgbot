@echo off
echo 上传Docker镜像到DockerHub

REM 设置您的DockerHub用户名
set DOCKER_USERNAME=diciky

REM 确认用户名
echo 您的DockerHub用户名是: %DOCKER_USERNAME%
set /p CONFIRM=确认继续? [Y/N]:
if /i not "%CONFIRM%"=="Y" exit /b

REM 重新打标签
echo 正在为镜像打标签...
docker tag tgbot %DOCKER_USERNAME%/tgbot:latest

REM 推送到DockerHub
echo 正在推送镜像到DockerHub...
docker push %DOCKER_USERNAME%/tgbot:latest

echo 操作完成! 