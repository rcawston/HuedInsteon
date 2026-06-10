#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Small local Hue Bridge API helper for Zigbee pairing tests."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import ssl
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / ".hue_bridge.json"


class HueError(RuntimeError):
    pass


def load_config(path: Path) -> dict[str, str]:
    config: dict[str, str] = {}
    if path.exists():
        raw = json.loads(path.read_text())
        if isinstance(raw, dict):
            config.update({str(k): str(v) for k, v in raw.items()})

    if os.environ.get("HUE_BRIDGE_IP"):
        config["bridge"] = os.environ["HUE_BRIDGE_IP"]
    if os.environ.get("HUE_APP_KEY"):
        config["username"] = os.environ["HUE_APP_KEY"]

    return config


def save_config(path: Path, config: dict[str, str]) -> None:
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def bridge_base(bridge: str) -> str:
    if bridge.startswith(("http://", "https://")):
        return bridge.rstrip("/")
    return f"http://{bridge}"


def request_json(
    bridge: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15,
) -> Any:
    data = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    req = Request(
        bridge_base(bridge) + path,
        data=data,
        headers=request_headers,
        method=method,
    )
    context = ssl._create_unverified_context()
    try:
        with urlopen(req, timeout=timeout, context=context) as response:
            payload = response.read()
    except HTTPError as exc:
        raise HueError(f"{method} {path} failed: HTTP {exc.code}") from exc
    except URLError as exc:
        raise HueError(f"{method} {path} failed: {exc.reason}") from exc

    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def require_bridge(config: dict[str, str]) -> str:
    bridge = config.get("bridge")
    if not bridge:
        raise HueError("missing bridge IP; pass --bridge or set HUE_BRIDGE_IP")
    return bridge


def require_username(config: dict[str, str]) -> str:
    username = config.get("username")
    if not username:
        raise HueError("missing app key; run auth or set HUE_APP_KEY")
    return username


def hue_v1(config: dict[str, str], method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    bridge = require_bridge(config)
    username = require_username(config)
    return request_json(bridge, method, f"/api/{username}{path}", body)


def hue_v2(config: dict[str, str], method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    bridge = require_bridge(config)
    username = require_username(config)
    return request_json(
        bridge,
        method,
        f"/clip/v2/resource{path}",
        body,
        headers={"hue-application-key": username},
    )


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def cmd_auth(args: argparse.Namespace, config: dict[str, str]) -> int:
    bridge = require_bridge(config)
    body = {"devicetype": args.device_type, "generateclientkey": True}
    result = request_json(bridge, "POST", "/api", body)
    if not isinstance(result, list):
        print_json(result)
        return 1

    for item in result:
        if "success" in item and "username" in item["success"]:
            config["username"] = item["success"]["username"]
            if "clientkey" in item["success"]:
                config["clientkey"] = item["success"]["clientkey"]
            save_config(args.config, config)
            print(f"saved app key to {args.config}")
            return 0
        if "error" in item:
            print_json(item)
            return 1

    print_json(result)
    return 1


def cmd_config(args: argparse.Namespace, config: dict[str, str]) -> int:
    print_json(hue_v1(config, "GET", "/config"))
    return 0


def cmd_search(args: argparse.Namespace, config: dict[str, str]) -> int:
    print_json(hue_v1(config, "POST", "/lights", {}))
    return 0


def discovery_id(config: dict[str, str]) -> str:
    result = hue_v2(config, "GET", "/zigbee_device_discovery")
    data = result.get("data", [])
    if not data:
        raise HueError("bridge did not return a zigbee_device_discovery resource")
    return data[0]["id"]


def cmd_v2_discovery(args: argparse.Namespace, config: dict[str, str]) -> int:
    print_json(hue_v2(config, "GET", "/zigbee_device_discovery"))
    return 0


def cmd_v2_search(args: argparse.Namespace, config: dict[str, str]) -> int:
    body = {
        "type": "zigbee_device_discovery",
        "action": {"action_type": args.action_type},
    }
    print_json(hue_v2(config, "PUT", f"/zigbee_device_discovery/{discovery_id(config)}", body))
    return 0


def cmd_v2_resources(args: argparse.Namespace, config: dict[str, str]) -> int:
    print_json(hue_v2(config, "GET", f"/{args.resource}"))
    return 0


def cmd_new(args: argparse.Namespace, config: dict[str, str]) -> int:
    deadline = time.time() + args.watch
    while True:
        result = hue_v1(config, "GET", "/lights/new")
        print_json(result)
        if args.watch <= 0 or time.time() >= deadline:
            return 0
        time.sleep(args.interval)


def cmd_lights(args: argparse.Namespace, config: dict[str, str]) -> int:
    lights = hue_v1(config, "GET", "/lights")
    if args.json:
        print_json(lights)
        return 0

    for light_id, light in sorted(lights.items(), key=lambda item: int(item[0])):
        name = light.get("name", "")
        modelid = light.get("modelid", "")
        uniqueid = light.get("uniqueid", "")
        productname = light.get("productname", "")
        state = light.get("state", {})
        reachable = state.get("reachable", "?")
        print(
            f"{light_id:>3}  {name:<32} {modelid:<16} "
            f"reachable={reachable} uniqueid={uniqueid} product={productname}"
        )
    return 0


def cmd_delete(args: argparse.Namespace, config: dict[str, str]) -> int:
    ids = list(args.ids)
    if args.name_contains:
        lights = hue_v1(config, "GET", "/lights")
        ids.extend(
            light_id
            for light_id, light in lights.items()
            if args.name_contains.lower() in str(light.get("name", "")).lower()
        )

    seen: set[str] = set()
    for light_id in ids:
        if light_id in seen:
            continue
        seen.add(light_id)
        if not args.yes:
            raise HueError("delete requires --yes")
        print_json(hue_v1(config, "DELETE", f"/lights/{light_id}"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--bridge", help="Bridge IP address or base URL")

    subparsers = parser.add_subparsers(dest="command", required=True)

    auth = subparsers.add_parser("auth", help="Create and save a Hue app key.")
    auth.add_argument("--device-type", default="huedinsteon#codex")
    auth.set_defaults(func=cmd_auth)

    config = subparsers.add_parser("config", help="Read bridge config.")
    config.set_defaults(func=cmd_config)

    search = subparsers.add_parser("search", help="Start searching for new lights.")
    search.set_defaults(func=cmd_search)

    v2_discovery = subparsers.add_parser("v2-discovery", help="Read V2 Zigbee discovery state.")
    v2_discovery.set_defaults(func=cmd_v2_discovery)

    v2_search = subparsers.add_parser("v2-search", help="Start V2 Zigbee device discovery.")
    v2_search.add_argument(
        "--action-type",
        choices=["search", "search_allow_default_link_key"],
        default="search_allow_default_link_key",
    )
    v2_search.set_defaults(func=cmd_v2_search)

    v2_resources = subparsers.add_parser("v2-resource", help="Read a V2 resource collection.")
    v2_resources.add_argument("resource")
    v2_resources.set_defaults(func=cmd_v2_resources)

    new = subparsers.add_parser("new", help="Read /lights/new, optionally polling.")
    new.add_argument("--watch", type=float, default=0)
    new.add_argument("--interval", type=float, default=5)
    new.set_defaults(func=cmd_new)

    lights = subparsers.add_parser("lights", help="List bridge lights.")
    lights.add_argument("--json", action="store_true")
    lights.set_defaults(func=cmd_lights)

    delete = subparsers.add_parser("delete", help="Delete light ids from the bridge.")
    delete.add_argument("ids", nargs="*")
    delete.add_argument("--name-contains")
    delete.add_argument("--yes", action="store_true")
    delete.set_defaults(func=cmd_delete)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(args.config)
    if args.bridge:
        config["bridge"] = args.bridge
        save_config(args.config, config)

    try:
        return args.func(args, config)
    except HueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
