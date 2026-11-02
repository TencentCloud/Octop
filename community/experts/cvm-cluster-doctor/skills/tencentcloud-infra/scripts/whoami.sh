#!/bin/bash
# 从腾讯云元数据服务获取实例ID
# 示例: instance-name 返回 lh-1251810746-lhins-dtx9e79f，提取 lhins-dtx9e79f

INSTANCE_NAME=$(curl -s http://metadata.tencentyun.com/meta-data/instance-name)

# 检查 instance-name 中是否包含 lhins- 开头的ID
LHINS_ID=$(echo "$INSTANCE_NAME" | grep -oE 'lhins-[a-zA-Z0-9]+')

if [ -n "$LHINS_ID" ]; then
    # 提取 lhins-xxx 格式的ID并输出
    echo "$LHINS_ID"
else
    # 回退到 instance-id，去除空白字符
    curl -s http://metadata.tencentyun.com/meta-data/instance-id | tr -d '[:space:]'
    echo
fi