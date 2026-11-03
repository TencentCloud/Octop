import { execSync } from "node:child_process";

function readClipboard() {
  try {
    return execSync("pbpaste", { encoding: "utf8" }).trim();
  } catch {
    return "";
  }
}

const text = readClipboard();

if (!text) {
  console.error("剪贴板中没有可读取的文本。请先复制内容再调用此 skill。");
  process.exit(1);
}

console.log("===CLIPBOARD_TEXT_BEGIN===");
console.log(text);
console.log("===CLIPBOARD_TEXT_END===");