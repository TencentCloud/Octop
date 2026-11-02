#!/usr/bin/env node
// DailyHotApi 统一调用脚本
// 用法: node fetch_dailyhot.mjs <source> [key=value ...]
// 示例:
//   node fetch_dailyhot.mjs hupu
//   node fetch_dailyhot.mjs hupu type=6
//   node fetch_dailyhot.mjs baidu type=realtime
//   node fetch_dailyhot.mjs github type=weekly
//   node fetch_dailyhot.mjs weibo

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("用法: node fetch_dailyhot.mjs <source> [key=value ...]");
  console.error("示例: node fetch_dailyhot.mjs hupu type=1");
  process.exit(1);
}

const source = args[0];
const params = {};
for (const arg of args.slice(1)) {
  const [k, v] = arg.split("=");
  if (k && v !== undefined) params[k] = v;
}

async function main() {
  const mod = await import(`dailyhot-api/dist/routes/${source}.js`);
  const handleRoute = mod.handleRoute || mod.default;
  if (typeof handleRoute !== "function") {
    console.error(`错误: dailyhot-api/dist/routes/${source}.js 没有导出 handleRoute`);
    process.exit(1);
  }
  const ctx = { req: { query: (k) => params[k] } };
  const result = await handleRoute(ctx, false);
  console.log(JSON.stringify(result, null, 2));
  process.exit(0);
}

main().catch((e) => {
  console.error("Error:", e.message);
  process.exit(1);
});
