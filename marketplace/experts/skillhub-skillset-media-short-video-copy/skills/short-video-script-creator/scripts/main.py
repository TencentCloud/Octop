import argparse
import os
import datetime
import re
import asyncio
import aiohttp
import json
import sys
from pathlib import Path
from docx import Document
import PyPDF2

# Fix for Windows encoding issues
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 模型 API 地址
API_URL = "https://api2.aigcbest.top/v1/chat/completions"
API_KEY = "sk-uXiErnJimD8brHcWWzeL7tW5ILogfSFcNnTLGgel66j8y5c9"
DEFAULT_OUTPUT_DIR = Path(r"C:\Users\EDY\.openclaw\skills\short-video-script-creator\out_put")


def clean_text(text):
    """清理文本，去除无法用UTF-8编码的字符（如单独的代理项）"""
    if not isinstance(text, str):
        return text
    # 通过编码再解码来过滤非法字符
    return text.encode('utf-8', 'ignore').decode('utf-8')


async def model_gpt(message_list, model: str = "gemini-2.5-pro"):
    """调用大模型，返回生成的文本内容"""
    e = ""
    async with aiohttp.ClientSession() as session:
        for i in range(3):  # 最多重试3次
            try:
                async with session.post(
                        API_URL,
                        headers={
                            'Authorization': f'Bearer {API_KEY}',
                            'Content-Type': 'application/json'
                        },
                        data=json.dumps({
                            "model": model,
                            "messages": message_list,
                            "max_tokens": 12000,
                            "temperature": 0
                        }),
                        timeout=999
                ) as response:
                    data = await response.json()
                    if content := data.get('choices', [{}])[0].get('message', {}).get('content'):
                        return clean_text(content)  # 也清理模型返回的内容
            except Exception as e:
                await asyncio.sleep(i * 2)  # 指数退避
        return str(e)


def read_file_content(file_path):
    """读取文件内容，自动处理 .docx, .pdf 和 .txt/.md，并清理非法字符"""
    if not file_path or not os.path.exists(file_path):
        return ""

    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.docx':
            doc = Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
            return clean_text(text)
        elif ext == '.pdf':
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                return clean_text(text)
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
                return clean_text(text)
    except Exception as e:
        print(f"⚠️ 读取文件失败 {file_path}: {e}", file=sys.stderr)
        return ""


def load_prompt_template():
    """从 SKILL.md 中提取提示词模板（支持代码块带语言标识）"""
    skill_md_path = Path(__file__).parent.parent / "SKILL.md"
    if not skill_md_path.exists():
        print("❌ SKILL.md 不存在，无法提取提示词模板。", file=sys.stderr)
        sys.exit(1)

    with open(skill_md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 匹配 ``` 后可能跟语言标识，然后换行，然后以 "### **【启动模板】**" 开头的内容，直到结束的 ```
    pattern = r'```(?:markdown)?\s*\n(### \*\*【启动模板】\*\*.*?)\n```'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print("❌ SKILL.md 中未找到以 '### **【启动模板】**' 开头的提示词模板代码块。", file=sys.stderr)
        print("请确保 SKILL.md 中包含如下格式的代码块：", file=sys.stderr)
        print("```markdown\n### **【启动模板】**\n...\n```", file=sys.stderr)
        sys.exit(1)

    return clean_text(match.group(1).strip())  # 清理模板


def build_prompt(args):
    """根据命令行参数填充提示词模板"""
    template = load_prompt_template()

    # 读取所有文件内容
    battle_map_content = read_file_content(args.battle_map_file)
    meeting_notes_content = read_file_content(args.meeting_notes_file)
    product_info_content = read_file_content(args.product_info_file)
    benchmark_content = read_file_content(args.benchmark_script_file)
    competitor_content = read_file_content(args.competitor_script_file)

    historical_content = ""
    if args.historical_script_files:
        for f in args.historical_script_files:
            content = read_file_content(f)
            if content:
                historical_content += f"\n--- 历史文案: {os.path.basename(f)} ---\n{content}\n"

    # 替换占位符
    replacements = {
        "{{name}}": args.name if args.name else "待定",
        "{{customer_background}}": args.customer_background,
        "{{product_info}}": args.product_info if args.product_info else "",
        "{{product_info_content}}": product_info_content,
        "{{battle_map_content}}": battle_map_content,
        "{{meeting_notes_content}}": meeting_notes_content,
        "{{benchmark_content}}": benchmark_content,
        "{{competitor_content}}": competitor_content,
        "{{historical_content}}": historical_content,
        "{{count}}": str(args.count),
        "{{min_words}}": str(args.min_words),
        "{{max_words}}": str(args.max_words),
        "{{extra_requirements}}": args.extra_requirements if args.extra_requirements else "无额外要求。",
    }
    print(replacements)
    prompt = template
    for key, value in replacements.items():
        prompt = prompt.replace(key, value)
    return clean_text(prompt)  # 最终清理一次


def ensure_dir(path: Path):
    """确保目录存在，若不存在则创建"""
    path.mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="短视频脚本创作技能 (v2.1)")
    # 基础参数
    parser.add_argument("--count", type=int, required=True, help="脚本数量")
    parser.add_argument("--min-words", type=int, required=True, help="最少字数")
    parser.add_argument("--max-words", type=int, required=True, help="最多字数")
    parser.add_argument("--name", help="出镜人名称")
    parser.add_argument("--customer-background", required=True, help="客户背景描述")
    parser.add_argument("--product-info", help="核心产品信息简述")
    parser.add_argument("--extra-requirements", help="额外文案要求")
    parser.add_argument("--call-model", action="store_true", help="直接调用模型")

    # 文件参数 (v2.1)
    parser.add_argument("--battle-map-file", required=True, help="作战地图文件路径")
    parser.add_argument("--meeting-notes-file", help="会议纪要文件路径")
    parser.add_argument("--product-info-file", help="产品详细介绍文件路径")
    parser.add_argument("--benchmark-script-file", help="**口吻**对标脚本文件路径")
    parser.add_argument("--competitor-script-file", help="**内容**对标脚本文件路径")
    parser.add_argument("--historical-script-files", nargs="*", default=[], help="历史文案文件路径列表")

    args = parser.parse_args()
    print("args0",args)
    try:
        prompt = build_prompt(args)

        # 确保输出目录存在
        ensure_dir(DEFAULT_OUTPUT_DIR)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        ip_name_part = f"{args.name}_" if args.name else ""

        # 保存提示词（现在已经清理过了，但保留errors='ignore'以防万一）
        prompt_filename = f"prompt_{ip_name_part}{timestamp}.md"
        prompt_path = DEFAULT_OUTPUT_DIR / prompt_filename
        with open(prompt_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(prompt)
        print(f"✅ 提示词已保存至: {prompt_path}")

        if args.call_model:
            messages = [{"role": "user", "content": prompt}]
            try:
                generated_scripts = asyncio.run(model_gpt(messages))
            except Exception as e:
                print(f"模型调用失败: {e}")
                return

            # 保存生成的脚本
            script_filename = f"{ip_name_part}{timestamp}.md"
            script_path = DEFAULT_OUTPUT_DIR / script_filename
            with open(script_path, 'w', encoding='utf-8-sig', errors='ignore') as f:
                f.write(generated_scripts)
            print(f"✅ 短视频文案已保存至: {script_path}")

    except Exception as e:
        print(f"程序运行出错: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()