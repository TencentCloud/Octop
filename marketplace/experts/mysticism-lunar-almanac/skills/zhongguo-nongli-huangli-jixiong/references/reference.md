# Huangli Toolkit Reference

## 官网与账号

- 官网：https://nongli.skill.4glz.com
- 注册：`/register`
- 登录：`/login`
- 控制台（申请/复制 Token）：`/dashboard`

完整地址：https://nongli.skill.4glz.com/dashboard

## 环境变量

```bash
export HUANGLI_TOKEN="your_token_here"
export HUANGLI_BASE="https://api.nongli.skill.4glz.com"
```

## API 模式

- 单日期：`GET /api/lunar/date/{YYYY-MM-DD}`
- 多日期：`POST /api/lunar/batch`

## 推荐调用策略

1. 用户问一个具体日期 → `by-date`
2. 用户问一段时间/比较多天 → `batch`
3. 用户问关键词跨日期检索 → `search`

## 常见错误

- `401`：Token 无效（通常是已退出登录、已解绑设备，或 token 被手动重置）
- `429`：配额超限，登录控制台手动重置后继续（重置次数不限制）
- `404`：日期超出可用数据范围
