#!/bin/bash

# 进入容器
echo "进入tgbot-app容器..."
docker exec -it tgbot-app /bin/bash -c "
echo '修改app/models/user.py中的代码...'
sed -i 's/return await cursor.to_list(length=limit)/result = list(cursor)\\nreturn result/g' /app/app/models/user.py
echo '完成修改！'
"

echo "脚本执行完成" 