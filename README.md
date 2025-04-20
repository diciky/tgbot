# Telegram Bot 管理系统

一个集成Web管理界面的Telegram Bot应用，可以通过Web界面管理Telegram机器人。

## 功能特点

- Telegram Bot功能
  - 处理文本、图片、文档等消息
  - 自动保存消息记录
  - 支持自动删除消息
  - 管理员命令支持
  - 关键词自动回复
  - 欢迎新成员
  - 消息翻译
  - 用户积分系统
  - 签到功能
  - 群组统计分析

- Web管理界面
  - 用户管理
  - 消息查看与发送
  - 实时统计
  - 关键词管理
  - 自定义命令管理
  - 群组管理
  - 响应式设计

## Bot指令列表

### 通用指令

- `/start` - 开始使用机器人
- `/help` - 显示帮助信息
- `/web [URL]` - 网页转Telegraph链接
- `/qd` - 每日签到，获取积分
- `/zt` - 查看个人信息
- `/fy [语言代码] [文本]` - 翻译功能
  - 例如：`/fy en 你好` 翻译成英文
  - 例如：`/fy zh hello` 翻译成中文
- `/tu [时间段]` - 聊天热力图
  - `d` - 日热力图
  - `m` - 月热力图
  - `y` - 年热力图

### 管理员指令

- `/admin` - 访问管理员功能
- `/jf` - 积分排行榜，或查看指定用户积分
  - 格式：`/jf` 或 `/jf @用户名`
- `/jfxx` - 查看积分详情
  - 格式：`/jfxx` 或 `/jfxx @用户名`
- `/ban @用户名` - 踢出用户
- `/jy @用户名` - 禁言用户
- `/stats` - 显示统计信息

## Web管理界面功能

### 仪表盘

- 显示系统概览和关键统计数据
- 显示今日消息活跃度
- 显示本月消息趋势
- 用户增长统计

### 用户管理

- 查看所有用户列表
- 查看用户详细信息
- 搜索特定用户
- 删除用户
- 查看用户消息历史

### 消息管理

- 查看所有消息记录
- 按群组筛选消息
- 按用户筛选消息
- 搜索特定消息
- 发送新消息到指定群组

### 关键词管理

- 添加、编辑、删除关键词
- 设置关键词类型：一般关键词、敏感关键词、严禁关键词
- 设置关键词触发动作：回复消息、提醒用户、删除消息、删除并警告

### 自定义命令

- 添加、编辑、删除自定义命令
- 设置命令权限：所有用户、仅管理员、仅超级管理员
- 设置命令类型：回复固定文本、回复图片、执行操作、自定义脚本
- 查看命令使用统计和响应时间

### 群组管理

- 查看所有群组、已加入群组、管理的群组
- 查看群组详细信息：成员数、消息数、活跃度等
- 设置群组配置：欢迎新成员、关键词过滤、自动删除命令、收集统计信息
- 查看群组消息统计和活跃用户统计

### 设置

- 配置Bot和系统参数
- 修改管理员账户密码
- 设置自动删除消息时间
- 开启/关闭调试模式

## 技术栈

- Python 3.11
- python-telegram-bot
- FastAPI
- MongoDB
- Bootstrap 5
- Docker & Docker Compose

## 安装与部署

### 环境要求

- Docker & Docker Compose
- 有效的Telegram Bot Token

### 使用Docker部署

1. 克隆代码库

```bash
git clone https://github.com/your-username/tgbot.git
cd tgbot
```

2. 配置环境变量

修改`.env`文件，设置必要的环境变量：

```
# Telegram Bot配置
BOT_TOKEN=your_bot_token
ADMIN_IDS=your_admin_id  # 管理员ID，用逗号分隔

# MongoDB配置
MONGO_USERNAME=admin
MONGO_PASSWORD=your_password
MONGO_DB=tgbot

# Web配置
WEB_PORT=7000
WEB_HOST=0.0.0.0
SECRET_KEY=your_secret_key
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin

# 日志配置
LOG_FILE=bot.log
LOG_LEVEL=INFO
DEBUG=false

# 消息自动删除配置
AUTO_DELETE_MESSAGES=true
AUTO_DELETE_INTERVAL=30
```

3. 启动服务

```bash
docker-compose up -d
```

服务将在后台启动，Web管理界面将在 `http://localhost:7000` 提供访问。

### 开发环境设置

1. 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 运行应用

```bash
python main.py
```

## 使用说明

### 管理员登录

访问 `http://your-server:7000/login` 并使用以下默认凭据登录：
- 用户名：admin
- 密码：admin

建议登录后立即修改默认密码。

## 安全注意事项

- 部署到生产环境前请修改所有默认密码
- 建议使用HTTPS保护Web管理界面
- 定期备份数据库

## 许可证

MIT 