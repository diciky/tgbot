#!/bin/bash

# 进入容器
echo "进入tgbot-app容器..."
docker exec -it tgbot-app /bin/bash -c "
echo '修改app/templates/base.html中的axios配置...'
sed -i 's/axios.defaults.baseURL = .*/axios.defaults.baseURL = \"\";/g' /app/app/templates/base.html
echo '完成修改！'
"

echo "脚本执行完成" 