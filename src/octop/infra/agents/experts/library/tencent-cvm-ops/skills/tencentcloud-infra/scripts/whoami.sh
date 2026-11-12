#!/bin/bash
# 从腾讯云元数据服务获取实例 ID
# 示例: instance-name 返回 lh-1251810746-lhins-dtx9e79f，提取 lhins-dtx9e79f
#
# 元数据服务是链路本地地址，非腾讯云环境会一直挂到默认超时；
# 这里统一加短超时并给出明确错误，避免 Agent 卡住。

WITH_REGION=0
if [ "${1:-}" = "--with-region" ]; then
    WITH_REGION=1
fi

META_BASE="http://metadata.tencentyun.com/meta-data"

meta_get() {
    curl -s --connect-timeout 1 --max-time 2 "$META_BASE/$1"
}

INSTANCE_NAME=$(meta_get "instance-name")
if [ -z "$INSTANCE_NAME" ]; then
    echo "ERROR: 无法访问腾讯云元数据服务（当前机器可能不是腾讯云实例，或元数据服务不可达）" >&2
    exit 1
fi

# 检查 instance-name 中是否包含 lhins- 开头的 ID（轻量应用服务器）
LHINS_ID=$(printf '%s' "$INSTANCE_NAME" | grep -oE 'lhins-[a-zA-Z0-9]+')

print_id() {
    printf '%s\n' "$1"
    if [ "$WITH_REGION" -eq 1 ]; then
        ZONE=$(meta_get "placement/zone" | tr -d '[:space:]')
        # 标准可用区是 <region>-<数字>，例如 ap-guangzhou-3 → ap-guangzhou
        REGION=$(printf '%s' "$ZONE" | sed -E 's/-[0-9]+$//')
        printf 'zone=%s\n' "$ZONE"
        printf 'region=%s\n' "$REGION"
    fi
}

if [ -n "$LHINS_ID" ]; then
    print_id "$LHINS_ID"
else
    # 回退到 instance-id（CVM），去除空白字符
    INSTANCE_ID=$(meta_get "instance-id" | tr -d '[:space:]')
    if [ -z "$INSTANCE_ID" ]; then
        echo "ERROR: 元数据服务未返回 instance-id" >&2
        exit 1
    fi
    print_id "$INSTANCE_ID"
fi
