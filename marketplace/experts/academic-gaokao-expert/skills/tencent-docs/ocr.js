#!/usr/bin/env node
/**
 * 腾讯文档 MCP 本地图片 OCR 辅助脚本（跨平台）
 *
 * 功能：
 *   自动将本地图片 base64 编码后调用 ocr.* 工具，支持三种操作：
 *   - extract: 识别图片中的文字
 *   - toword:  将图片转为 Word 文档
 *   - toexcel: 将图片转为 Excel 文档
 *
 * 用法：
 *   node ocr.js extract <image> [--accurate|--efficient] [--positions]
 *   node ocr.js toword  <image> [<image2> ...] [--title "标题"]
 *   node ocr.js toexcel <image> [<image2> ...] [--title "标题"]
 *
 * 依赖：
 *   - Node.js (>= 14)
 *   - mcporter（已配置 tencent-docs 服务）
 */

"use strict";

const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

// ── 常量 ──────────────────────────────────────────────────────────────────
const MCP_SERVICE = "tencent-docs";
const SUPPORTED_EXTS = new Set(["png", "jpg", "jpeg", "bmp", "webp"]);
const MAX_SINGLE_SIZE = 10 * 1024 * 1024;
const MAX_TOTAL_SIZE = 50 * 1024 * 1024;
const MAX_IMAGE_COUNT = 9;

// ── 工具函数 ──────────────────────────────────────────────────────────────

function die(msg) {
  console.error("ERROR: " + msg);
  process.exit(1);
}

function validateImage(filePath) {
  if (!fs.existsSync(filePath)) die("文件不存在: " + filePath);

  var stat = fs.statSync(filePath);
  if (!stat.isFile()) die("不是文件: " + filePath);

  var ext = path.extname(filePath).slice(1).toLowerCase();
  if (!SUPPORTED_EXTS.has(ext)) {
    die("不支持的格式 ." + ext + "，支持: " + Array.from(SUPPORTED_EXTS).join(", "));
  }
  if (stat.size === 0) die("文件为空: " + filePath);
  if (stat.size > MAX_SINGLE_SIZE) die("文件超过 10MB: " + filePath);

  return stat.size;
}

function encodeBase64(filePath) {
  return fs.readFileSync(filePath).toString("base64");
}

// ── mcporter 调用封装 ────────────────────────────────────────────────────
// 使用 execFileSync 直接传参数数组，绕过 shell，兼容 Windows 且无命令行长度限制
function mcpCall(tool, argsObj) {
  var argsJson = JSON.stringify(argsObj);
  try {
    var stdout = execFileSync(
      "mcporter",
      ["call", MCP_SERVICE, tool, "--args", argsJson],
      { encoding: "utf-8", timeout: 120000 }
    );
    return stdout.trim();
  } catch (err) {
    var msg = err.stderr || err.stdout || err.message || "unknown error";
    throw new Error("mcporter call " + tool + " failed: " + msg);
  }
}

// ── 参数解析 ──────────────────────────────────────────────────────────────

function parseArgs() {
  var args = process.argv.slice(2);

  if (args.length === 0) {
    console.log("用法:");
    console.log("  node ocr.js extract <image> [--accurate|--efficient] [--positions]");
    console.log('  node ocr.js toword  <image> [<image2> ...] [--title "标题"]');
    console.log('  node ocr.js toexcel <image> [<image2> ...] [--title "标题"]');
    process.exit(1);
  }

  var action = args[0];
  if (["extract", "toword", "toexcel"].indexOf(action) === -1) {
    die("未知操作 '" + action + "'，支持: extract, toword, toexcel");
  }

  return { action: action, rest: args.slice(1) };
}

// ── extract ──────────────────────────────────────────────────────────────

function handleExtract(args) {
  var image = "";
  var extractType = "basic";
  var withPositions = false;

  for (var i = 0; i < args.length; i++) {
    switch (args[i]) {
      case "--accurate":  extractType = "accurate";  break;
      case "--efficient": extractType = "efficient"; break;
      case "--positions": withPositions = true;       break;
      default:
        if (args[i].charAt(0) === "-") die("未知选项 '" + args[i] + "'");
        if (image) die("extract 只支持单张图片");
        image = args[i];
        break;
    }
  }
  if (!image) die("未指定图片路径");
  validateImage(image);

  console.log("⏳ 正在识别 " + path.basename(image) + " ...");

  var result = mcpCall("ocr.extract", {
    image_base64: encodeBase64(image),
    extract_type: extractType,
    with_positions: withPositions,
  });
  console.log(result);
}

// ── toword / toexcel ─────────────────────────────────────────────────────

function handleConvert(action, args) {
  var images = [];
  var title = "";

  for (var i = 0; i < args.length; i++) {
    if (args[i] === "--title") {
      if (i + 1 >= args.length) die("--title 需要值");
      title = args[++i];
    } else if (args[i].charAt(0) === "-") {
      die("未知选项 '" + args[i] + "'");
    } else {
      images.push(args[i]);
    }
  }
  if (images.length === 0) die("未指定图片路径");
  if (images.length > MAX_IMAGE_COUNT) die("图片数量超过 " + MAX_IMAGE_COUNT + " 张限制");

  var totalSize = 0;
  for (var j = 0; j < images.length; j++) {
    totalSize += validateImage(images[j]);
  }
  if (totalSize > MAX_TOTAL_SIZE) die("图片总大小超过 50MB");

  console.log("⏳ 正在处理 " + images.length + " 张图片 ...");

  var callArgs = {
    images: images.map(function (img) { return { image_base64: encodeBase64(img) }; }),
  };
  if (title) callArgs.title = title;

  var result = mcpCall("ocr." + action, callArgs);
  console.log(result);
}

// ── 主流程 ────────────────────────────────────────────────────────────────

function main() {
  var parsed = parseArgs();
  if (parsed.action === "extract") {
    handleExtract(parsed.rest);
  } else {
    handleConvert(parsed.action, parsed.rest);
  }
}

main();
