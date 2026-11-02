#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
医学术语规范化：将口语化通用医学记录转换为标准化、规范化的医学记录。
LLM 调用使用公司内部医疗大模型。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_ROOT = SCRIPT_DIR.parents[3]
PREPROCESS_DIR = SKILLS_ROOT / "_shared" / "doc-preprocess" / "scripts"
if str(PREPROCESS_DIR) not in sys.path:
    sys.path.insert(0, str(PREPROCESS_DIR))

from preprocess import PreprocessError, SUPPORTED_FILE_TYPES, detect_input_type, load_input_artifact


DEFAULT_LLM_BASE = "https://maas-api.hivoice.cn/v1"
DEFAULT_LLM_MODEL = "u2-med"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input JSON 必须是对象")
    return payload


def extract_text(path: Path, input_type: str, encoding: str, sheet: str) -> str:
    artifact = load_input_artifact(path, input_type, encoding, sheet, pdf_as_single_text=True)
    kind = artifact["kind"]
    if kind == "text":
        return str(artifact.get("text") or "")
    if kind == "json":
        data = artifact["data"]
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("record", "text", "content", "records"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            if "records" in data and isinstance(data["records"], list):
                return json.dumps(data, ensure_ascii=False)
        return json.dumps(data, ensure_ascii=False)
    if kind == "tables":
        rows_text: list[str] = []
        for table in artifact.get("tables", []):
            for row in table.get("rows", []):
                rows_text.append("\t".join(str(cell) for cell in row))
        return "\n".join(rows_text)
    raise PreprocessError(f"Unsupported artifact kind: {kind}")


def build_prompt(payload: dict[str, Any]) -> str:
    raw_prompt = str(payload.get("prompt") or "").strip()
    if raw_prompt:
        return raw_prompt

    records = payload.get("records")
    if records:
        records_text = []
        current_section = ""
        for idx, record in enumerate(records):
            section = str(record.get("section") or "").strip()
            content = str(record.get("content") or record.get("text") or "").strip()
            
            if section and section != current_section:
                current_section = section
                records_text.append(f"{section}:\n")
            
            if content:
                records_text.append(f"{content}\n")
            records_text.append("\n")
        
        return f"""请你作为医学术语规范化专家，将提供的口语化通用医学记录（涵盖门诊、住院日常场景）转换为标准化、规范化的医学记录。转换需严格遵循以下规则，确保符合临床病历书写规范，术语准确，表述严谨，无口语化、不规范表述，同时完整保留原始记录的核心信息，不遗漏、不新增、不篡改，适配各类通用医学记录场景。
核心规范化要求：
1.  术语规范：将口语化、通俗化表述替换为标准医学术语（例："肚子"→"腹部"、"发烧"→"发热"、"拉肚子"→"腹泻"、"打针"→"静脉注射"、"消炎药"→"抗生素"），确保术语使用符合临床标准，无错别字、无随意简写，必要时规范简写（如"冠状动脉粥样硬化性心脏病"不简写为"冠心病"以外的表述）。
2.  表述严谨：删除口语化语气词、冗余表述、口语化句式，调整为规范的医学书面句式，逻辑清晰，语句简洁（例："患者今天状态还行，没什么不舒服"→"患者当日一般情况可，无明显不适"；"烧退了，不怎么咳嗽了"→"发热症状缓解，咳嗽症状减轻"）。
3.  数据规范：生命体征、检查结果、时间、剂量等数据表述统一，保留原始数据，格式规范（例："体温 37 度 2"→"体温 37.2℃"、"血压 140/90"→"血压 140/90mmHg"、"吃了 3 天药"→"规律用药 3 天"）。
4.  结构规范：保留原始记录的核心模块（患者基本情况、主诉、现病史、检查结果、处理建议等），模块顺序不变，每个模块表述规范、简洁，符合通用医学记录书写格式。
5.  核心原则：完全忠于原始口语化记录的核心信息，仅做"口语→规范"的转换，不改变原意、不遗漏关键信息、不新增任何原始记录未提及的内容。

待规范化医学记录：
{''.join(records_text)}

### 输出
""".strip()

    # 从 JSON 的 record 或 text 字段获取
    record_text = str(payload.get("record") or payload.get("text") or payload.get("content") or "").strip()
    if not record_text.strip():
        raise ValueError("输入缺少 records 或 prompt")

    return f"""请你作为医学术语规范化专家，将提供的口语化通用医学记录（涵盖门诊、住院日常场景）转换为标准化、规范化的医学记录。转换需严格遵循以下规则，确保符合临床病历书写规范，术语准确，表述严谨，无口语化、不规范表述，同时完整保留原始记录的核心信息，不遗漏、不新增、不篡改，适配各类通用医学记录场景。
核心规范化要求：
1.  术语规范：将口语化、通俗化表述替换为标准医学术语（例："肚子"→"腹部"、"发烧"→"发热"、"拉肚子"→"腹泻"、"打针"→"静脉注射"、"消炎药"→"抗生素"），确保术语使用符合临床标准，无错别字、无随意简写，必要时规范简写（如"冠状动脉粥样硬化性心脏病"不简写为"冠心病"以外的表述）。
2.  表述严谨：删除口语化语气词、冗余表述、口语化句式，调整为规范的医学书面句式，逻辑清晰，语句简洁（例："患者今天状态还行，没什么不舒服"→"患者当日一般情况可，无明显不适"；"烧退了，不怎么咳嗽了"→"发热症状缓解，咳嗽症状减轻"）。
3.  数据规范：生命体征、检查结果、时间、剂量等数据表述统一，保留原始数据，格式规范（例："体温 37 度 2"→"体温 37.2℃"、"血压 140/90"→"血压 140/90mmHg"、"吃了 3 天药"→"规律用药 3 天"）。
4.  结构规范：保留原始记录的核心模块（患者基本情况、主诉、现病史、检查结果、处理建议等），模块顺序不变，每个模块表述规范、简洁，符合通用医学记录书写格式。
5.  核心原则：完全忠于原始口语化记录的核心信息，仅做"口语→规范"的转换，不改变原意、不遗漏关键信息、不新增任何原始记录未提及的内容。

待规范化医学记录：
{record_text}

### 输出
""".strip()


def build_payload_from_input(
    path: Path,
    *,
    input_type: str,
    encoding: str,
    sheet: str,
) -> dict[str, Any]:
    resolved_type = detect_input_type(path, input_type)
    if resolved_type == "json":
        try:
            payload = _read_json(path)
            if payload.get("prompt") or "records" in payload or payload.get("record") or payload.get("text"):
                return payload
        except Exception:
            pass

    record_text = extract_text(path, resolved_type, encoding, sheet)
    if not record_text.strip():
        raise PreprocessError("预处理后病历文本为空")
    return {
        "record": record_text,
    }


def payload_to_prepared_text(payload: dict[str, Any]) -> str:
    raw_prompt = str(payload.get("prompt") or "").strip()
    if raw_prompt:
        return raw_prompt

    records = payload.get("records")
    if records:
        records_text = []
        current_section = ""
        for idx, record in enumerate(records):
            section = str(record.get("section") or "").strip()
            content = str(record.get("content") or record.get("text") or "").strip()
            
            if section and section != current_section:
                current_section = section
                records_text.append(f"{section}:\n")
            
            if content:
                records_text.append(f"{content}\n")
            records_text.append("\n")
        
        return ''.join(records_text)

    record_text = str(payload.get("record") or payload.get("text") or payload.get("content") or "").strip()
    return record_text


def save_prepared(payload: dict[str, Any], output_path: str, input_path: Path) -> None:
    save_dir = Path(output_path).parent if output_path else SCRIPT_DIR.parents[1] / "runs" / "medical-term-normalization"
    save_dir.mkdir(parents=True, exist_ok=True)
    prepared_path = save_dir / f"{input_path.stem}.prepared.txt"
    prepared_path.write_text(payload_to_prepared_text(payload), encoding="utf-8")
    print(f"Prepared text saved to: {prepared_path}", file=sys.stderr)


def _http_post(url: str, payload: dict[str, Any], headers: dict[str, str], *, timeout: int = 0) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", **{key: value for key, value in headers.items() if value}},
    )
    try:
        opener = urllib.request.urlopen(req) if not timeout else urllib.request.urlopen(req, timeout=timeout)
        with opener as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc}") from exc


def call_llm(prompt: str, *, base: str, model: str, appkey: str, timeout: int) -> str:
    url = f"{base.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {appkey}"} if appkey else {}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    response = _http_post(url, payload, headers, timeout=timeout)
    try:
        return str(response["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LLM response: {response}") from exc


def run(payload: dict[str, Any], *, base: str, model: str, appkey: str, timeout: int) -> str:
    prompt = build_prompt(payload)
    return call_llm(prompt, base=base, model=model, appkey=appkey, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description="医学术语规范化统一入口：支持 pdf/doc/docx/xls/xlsx/csv/txt/json 输入。")
    parser.add_argument("--input", required=True, help="输入病历文件路径。")
    parser.add_argument("--input-type", default="auto", choices=["auto", *sorted(SUPPORTED_FILE_TYPES)], help="输入类型；默认 auto。")
    parser.add_argument("--sheet", default="", help="读取 Excel 时指定 sheet（可选）。")
    parser.add_argument("--encoding", default="utf-8", help="txt/csv 编码（默认：utf-8）。")
    parser.add_argument("--base", default=DEFAULT_LLM_BASE, help=f"内部大模型 base URL（默认：{DEFAULT_LLM_BASE}）。")
    parser.add_argument("--model", default=DEFAULT_LLM_MODEL, help=f"模型名称（默认：{DEFAULT_LLM_MODEL}）。")
    parser.add_argument("--timeout", type=int, default=0, help="HTTP 超时秒数；0 表示一直等待（默认：0）。")
    parser.add_argument("--appkey", required=True, help="必须传入。内部医疗大模型鉴权 key，使用 Bearer 方式认证。")
    parser.add_argument("--output-json", default="", help="输出 JSON 文件路径（可选）。")
    parser.add_argument("--output", default="", help="输出规范化记录文本文件路径（可选）。")
    parser.add_argument("--save-prepared", action="store_true", help="保存预处理后的文本，便于调试。")
    args = parser.parse_args()

    try:
        input_path = Path(args.input)
        payload = build_payload_from_input(
            input_path,
            input_type=args.input_type,
            encoding=args.encoding,
            sheet=args.sheet,
        )
        if args.save_prepared:
            save_prepared(payload, args.output, input_path)
        response = run(
            payload,
            base=args.base,
            model=args.model,
            appkey=args.appkey,
            timeout=args.timeout,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output_path = args.output or args.output_json
    if output_path:
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(response, encoding="utf-8")
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
