// 创建应用数据库和用户
db = db.getSiblingDB('tgbot');

db.createUser({
  user: 'admin',
  pwd: '465465Daz',
  roles: [
    {
      role: 'readWrite',
      db: 'tgbot'
    }
  ]
});

// 创建集合
db.createCollection('users');
db.createCollection('messages');
db.createCollection('groups');
db.createCollection('settings');

// 创建索引
db.users.createIndex({ "user_id": 1 }, { unique: true });
db.messages.createIndex({ "message_id": 1 });
db.messages.createIndex({ "chat_id": 1 });
db.messages.createIndex({ "date": 1 });
db.groups.createIndex({ "group_id": 1 }, { unique: true });

// 插入默认设置
db.settings.insertOne({
  "_id": "bot_settings",
  "auto_delete_messages": true,
  "auto_delete_interval": 30,
  "welcome_message": "欢迎使用Telegram Bot!",
  "created_at": new Date()
}); 