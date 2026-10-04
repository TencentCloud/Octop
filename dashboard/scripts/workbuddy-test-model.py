"""Local controlled model for disposable UI acceptance; never imported by Octop.

Only the model boundary is fixed. Octop auth, chat, tools, HITL, workspace and
persistence still run normally. No credentials, prompts or headers are logged.
"""

import argparse
import hashlib
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL = "octop-ui-acceptance"
EMBEDDING_MODEL = "octop-ui-embedding"
PARTS = [
    "这是",
    "隔离实例",
    "中的",
    "聊天验收",
    "固定模型回复。",
    "\n\n",
    "消息经由 Octop ",
    "现有业务链路",
    "流式传递。",
]


def requested_tool(messages, workspace_root):
    last_user = next(
        (i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "user"),
        -1,
    )
    if last_user < 0 or any(m.get("role") == "tool" for m in messages[last_user + 1 :]):
        return None
    content = messages[last_user].get("content", "")
    text = (
        "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
        if isinstance(content, list)
        else str(content)
    ).split("\n\n<memory-context>", 1)[0]
    if "验收审批" in text:
        return {
            "name": "write_file",
            "arguments": json.dumps(
                {
                    "file_path": str(workspace_root / "round2-acceptance.md"),
                    "content": "# Round 2 UI acceptance\nDisposable isolated workspace file.\n",
                }
            ),
        }
    if "验收提问" in text:
        return {
            "name": "ask_user_question",
            "arguments": json.dumps(
                {
                    "questions": [
                        {
                            "question": "Choose the acceptance result",
                            "header": "Acceptance",
                            "options": [
                                {"label": "Continue", "description": "Resume the isolated task"},
                                {"label": "Cancel", "description": "Stop the isolated task"},
                            ],
                            "multi_select": False,
                        }
                    ]
                }
            ),
        }
    if "验收工具" in text:
        return {"name": "current_time", "arguments": json.dumps({"tz": "Asia/Shanghai"})}
    return None


def handler_for(workspace_root, chunk_delay, evidence):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            pass

        def send_json(self, value, status=200):
            payload = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path.split("?", 1)[0] not in {"/models", "/v1/models"}:
                self.close_connection = True
                self.send_json({"error": "Unsupported acceptance endpoint"}, status=404)
                return
            self.send_json(
                {
                    "object": "list",
                    "data": [
                        {"id": name, "object": "model", "owned_by": "local-test"}
                        for name in (MODEL, EMBEDDING_MODEL)
                    ],
                }
            )

        def do_POST(self):
            endpoint = self.path.split("?", 1)[0]
            if endpoint not in {
                "/chat/completions",
                "/v1/chat/completions",
                "/embeddings",
                "/v1/embeddings",
            }:
                self.close_connection = True
                self.send_json({"error": "Unsupported acceptance endpoint"}, status=404)
                return
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            if endpoint.endswith("/embeddings"):
                inputs = body.get("input", [])
                inputs = [inputs] if isinstance(inputs, str) else inputs
                # Deterministic protocol fixture only; does not model semantic relevance.
                data = []
                for index, value in enumerate(inputs):
                    digest = hashlib.sha256(json.dumps(value).encode()).digest()
                    vector = [(byte - 127.5) / 127.5 for byte in digest]
                    norm = sum(number * number for number in vector) ** 0.5
                    data.append(
                        {
                            "object": "embedding",
                            "index": index,
                            "embedding": [number / norm for number in vector],
                        }
                    )
                self.send_json(
                    {
                        "object": "list",
                        "model": EMBEDDING_MODEL,
                        "data": data,
                        "usage": {"prompt_tokens": len(inputs), "total_tokens": len(inputs)},
                    }
                )
                return
            if evidence:
                record = {
                    "stream": bool(body.get("stream")),
                    "tools": [
                        tool.get("function", {}).get("name") for tool in body.get("tools", [])
                    ],
                }
                with evidence.open("a") as log:
                    log.write(json.dumps(record) + "\n")
            base = {
                "id": "chatcmpl-ui-acceptance",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": MODEL,
            }
            usage = {"prompt_tokens": 20, "completion_tokens": 20, "total_tokens": 40}
            if not body.get("stream"):
                self.send_json(
                    {
                        **base,
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": "".join(PARTS)},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": usage,
                    }
                )
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            def send(delta, finish_reason=None, token_usage=None):
                chunk = {
                    **base,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
                }
                if token_usage:
                    chunk["usage"] = token_usage
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.flush()

            try:
                call = requested_tool(body.get("messages", []), workspace_root)
                if call:
                    send(
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-ui-acceptance",
                                    "type": "function",
                                    "function": call,
                                }
                            ],
                        }
                    )
                    send({}, "tool_calls")
                else:
                    for part in PARTS:
                        send({"role": "assistant", "content": part})
                        time.sleep(chunk_delay)
                    send({}, "stop", usage)
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True

    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18090)
    parser.add_argument("--chunk-delay", type=float, default=1.5)
    parser.add_argument("--evidence-jsonl", type=Path)
    args = parser.parse_args()
    if args.chunk_delay < 0 or not args.workspace_root.is_absolute():
        parser.error("Use an absolute disposable workspace root and a non-negative delay")
    ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        handler_for(args.workspace_root, args.chunk_delay, args.evidence_jsonl),
    ).serve_forever()
