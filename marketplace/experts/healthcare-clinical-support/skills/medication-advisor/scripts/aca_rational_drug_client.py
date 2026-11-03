#!/usr/bin/env python3
"""
Tencent Cloud ACA Rational Drug Use API client.

Usage examples:
    export TENCENTCLOUD_SECRET_ID=...
    export TENCENTCLOUD_SECRET_KEY=...

    # Or store credentials in JSON and pass --config:
    # {
    #   "secret_id": "...",
    #   "secret_key": "...",
    #   "region": "ap-guangzhou",
    #   "endpoint": "aca.tencentcloudapi.com"
    # }

    python scripts/aca_rational_drug_client.py MatchDrug \
        --region ap-guangzhou \
        --payload-json '{"Drugs":[{"DrugName":"诺氟沙星片"}],"DrugType":0}'

    python scripts/aca_rational_drug_client.py ReviewRationalDrugUse \
        --config ~/.config/medication-advisor/aca.json \
        --payload-file /path/to/payload.json

Use --dry-run to inspect the request without sending it.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SERVICE = "aca"
VERSION = "2021-03-23"
DEFAULT_ENDPOINT = "aca.tencentcloudapi.com"
DEFAULT_REGION = "ap-guangzhou"
SUPPORTED_ACTIONS = {
    "MatchDiagnosis",
    "MatchDrug",
    "MatchFrequency",
    "MatchRoute",
    "QueryAdverseReactionRisk",
    "QueryInteractionRisk",
    "ReviewRationalDrugUse",
}
DEFAULT_CONFIG_PATHS = (
    Path.home() / ".config" / "medication-advisor" / "aca.json",
    Path.home() / ".aca-rational-drug.json",
)


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload_json and args.payload_file:
        raise ValueError("Use only one of --payload-json or --payload-file.")
    if args.payload_json:
        return json.loads(args.payload_json)
    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as file:
            return json.load(file)
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            return json.loads(text)
    raise ValueError("Provide request payload with --payload-json, --payload-file, or stdin.")


def load_config(config_path: str | None) -> dict[str, Any]:
    paths: list[Path]
    if config_path:
        paths = [Path(config_path).expanduser()]
    elif os.getenv("ACA_CONFIG_FILE"):
        paths = [Path(os.environ["ACA_CONFIG_FILE"]).expanduser()]
    else:
        paths = list(DEFAULT_CONFIG_PATHS)

    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
        if not isinstance(config, dict):
            raise ValueError(f"Config file must contain a JSON object: {path}")
        return config

    if config_path:
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return {}


def resolve_setting(
    *,
    cli_value: str | None,
    env_name: str,
    config: dict[str, Any],
    config_key: str,
    default: str,
) -> str:
    if cli_value:
        return cli_value
    env_value = os.getenv(env_name)
    if env_value:
        return env_value
    config_value = config.get(config_key)
    if config_value:
        return str(config_value)
    return default


def resolve_secret(*, env_name: str, config: dict[str, Any], config_key: str) -> str:
    env_value = os.getenv(env_name)
    if env_value:
        return env_value
    config_value = config.get(config_key)
    return str(config_value) if config_value else ""


def build_headers(
    *,
    action: str,
    endpoint: str,
    region: str,
    payload: str,
    secret_id: str,
    secret_key: str,
    token: str | None = None,
    timestamp: int | None = None,
) -> dict[str, str]:
    timestamp = timestamp or int(time.time())
    date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))

    canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{endpoint}\n"
    signed_headers = "content-type;host"
    canonical_request = "\n".join(
        [
            "POST",
            "/",
            "",
            canonical_headers,
            signed_headers,
            sha256_hex(payload.encode("utf-8")),
        ]
    )

    credential_scope = f"{date}/{SERVICE}/tc3_request"
    string_to_sign = "\n".join(
        [
            "TC3-HMAC-SHA256",
            str(timestamp),
            credential_scope,
            sha256_hex(canonical_request.encode("utf-8")),
        ]
    )

    secret_date = sign(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = sign(secret_date, SERVICE)
    secret_signing = sign(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        "TC3-HMAC-SHA256 "
        f"Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": endpoint,
        "X-TC-Action": action,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": VERSION,
        "X-TC-Region": region,
    }
    if token:
        headers["X-TC-Token"] = token
    return headers


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = dict(headers)
    if "Authorization" in redacted:
        redacted["Authorization"] = "<redacted>"
    if "X-TC-Token" in redacted:
        redacted["X-TC-Token"] = "<redacted>"
    return redacted


def call_api(endpoint: str, headers: dict[str, str], payload: str, timeout: int) -> dict[str, Any]:
    request = Request(
        f"https://{endpoint}",
        data=payload.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body}") from error
    except URLError as error:
        raise RuntimeError(f"Network error: {error.reason}") from error
    return json.loads(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call Tencent Cloud ACA rational drug use APIs.")
    parser.add_argument("action", choices=sorted(SUPPORTED_ACTIONS), help="ACA API action name.")
    parser.add_argument("--payload-json", help="JSON request payload string.")
    parser.add_argument("--payload-file", help="Path to JSON request payload file.")
    parser.add_argument("--config", help="Path to JSON config file. Defaults to ACA_CONFIG_FILE or user config paths.")
    parser.add_argument("--region", help="Tencent Cloud region.")
    parser.add_argument("--endpoint", help="ACA API endpoint host.")
    parser.add_argument("--secret-id-env", default="TENCENTCLOUD_SECRET_ID", help="Env var containing SecretId.")
    parser.add_argument("--secret-key-env", default="TENCENTCLOUD_SECRET_KEY", help="Env var containing SecretKey.")
    parser.add_argument("--token-env", default="TENCENTCLOUD_TOKEN", help="Optional env var containing temporary token.")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Print redacted request and do not send it.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        payload_data = load_payload(args)
        payload = json.dumps(payload_data, ensure_ascii=False, separators=(",", ":"))

        region = resolve_setting(
            cli_value=args.region,
            env_name="ACA_REGION",
            config=config,
            config_key="region",
            default=DEFAULT_REGION,
        )
        endpoint = resolve_setting(
            cli_value=args.endpoint,
            env_name="ACA_ENDPOINT",
            config=config,
            config_key="endpoint",
            default=DEFAULT_ENDPOINT,
        )
        secret_id = resolve_secret(env_name=args.secret_id_env, config=config, config_key="secret_id")
        secret_key = resolve_secret(env_name=args.secret_key_env, config=config, config_key="secret_key")
        token = resolve_secret(env_name=args.token_env, config=config, config_key="token") or None

        if not secret_id or not secret_key:
            if not args.dry_run:
                raise ValueError(
                    "Missing credentials. Set environment variables, provide --config, "
                    "or use --dry-run."
                )
            secret_id = "DRY_RUN_SECRET_ID"
            secret_key = "DRY_RUN_SECRET_KEY"

        headers = build_headers(
            action=args.action,
            endpoint=endpoint,
            region=region,
            payload=payload,
            secret_id=secret_id,
            secret_key=secret_key,
            token=token,
        )

        if args.dry_run:
            output = {
                "url": f"https://{endpoint}",
                "headers": redact_headers(headers),
                "payload": payload_data,
            }
        else:
            output = call_api(endpoint, headers, payload, args.timeout)

        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty or args.dry_run else None))
        return 0
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
