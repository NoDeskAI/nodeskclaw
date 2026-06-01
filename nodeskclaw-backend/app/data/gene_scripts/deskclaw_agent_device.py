#!/usr/bin/env python3
"""DeskClaw Agent Device Tool -- discover, lease, and invoke governed Agent Devices."""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse

from _api_client import _fatal, _output, api_call


def _json_arg(raw: str) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fatal(f"Invalid JSON: {exc}")
    if not isinstance(data, dict):
        _fatal("JSON value must be an object")
    return data


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deskclaw_agent_device", description="DeskClaw Agent Device Tool")
    sub = parser.add_subparsers(dest="action", required=True)

    reachable = sub.add_parser("list_reachable", help="List Agent Devices reachable by the current agent")
    reachable.add_argument("--instance-id", default=os.environ.get("DESKCLAW_INSTANCE_ID", ""))

    visibility = sub.add_parser("visibility", help="Inspect one device visibility and unavailable reasons")
    visibility.add_argument("--device-id", required=True)
    visibility.add_argument("--instance-id", default=os.environ.get("DESKCLAW_INSTANCE_ID", ""))

    acquire = sub.add_parser("acquire_lease", help="Acquire an exclusive lease")
    acquire.add_argument("--device-id", required=True)
    acquire.add_argument("--ttl-seconds", type=int, default=None)

    renew = sub.add_parser("renew_lease", help="Renew an active lease")
    renew.add_argument("--device-id", required=True)
    renew.add_argument("--lease-id", required=True)
    renew.add_argument("--ttl-seconds", type=int, default=None)

    release = sub.add_parser("release_lease", help="Release an active lease")
    release.add_argument("--device-id", required=True)
    release.add_argument("--lease-id", required=True)

    invoke = sub.add_parser("invoke", help="Invoke a device provider action")
    invoke.add_argument("--device-id", required=True)
    invoke.add_argument("--lease-id", required=True)
    invoke.add_argument("--provider-action", required=True)
    invoke.add_argument("--payload-json", default="{}")

    delegate = sub.add_parser("delegate", help="Delegate device scopes to another agent")
    delegate.add_argument("--device-id", required=True)
    delegate.add_argument("--agent-id", required=True)
    delegate.add_argument("--scopes", required=True, help="Comma-separated scopes: discover,lease,invoke,delegate")
    delegate.add_argument("--can-delegate", action="store_true")
    delegate.add_argument("--parent-grant-id", default=None)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.action == "list_reachable":
        qs = ""
        if args.instance_id:
            qs = "?instance_id=" + urllib.parse.quote(args.instance_id)
        _output(api_call("GET", f"/reachable-devices{qs}"))

    elif args.action == "visibility":
        qs = ""
        if args.instance_id:
            qs = "?instance_id=" + urllib.parse.quote(args.instance_id)
        _output(api_call("GET", f"/devices/{args.device_id}/visibility{qs}"))

    elif args.action == "acquire_lease":
        body = {}
        if args.ttl_seconds:
            body["ttl_seconds"] = args.ttl_seconds
        _output(api_call("POST", f"/devices/{args.device_id}/leases", body))

    elif args.action == "renew_lease":
        body = {}
        if args.ttl_seconds:
            body["ttl_seconds"] = args.ttl_seconds
        _output(api_call("POST", f"/devices/{args.device_id}/leases/{args.lease_id}/renew", body))

    elif args.action == "release_lease":
        _output(api_call("DELETE", f"/devices/{args.device_id}/leases/{args.lease_id}"))

    elif args.action == "invoke":
        _output(api_call("POST", f"/devices/{args.device_id}/invoke", {
            "lease_id": args.lease_id,
            "action": args.provider_action,
            "payload": _json_arg(args.payload_json),
        }))

    elif args.action == "delegate":
        scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
        _output(api_call("POST", f"/devices/{args.device_id}/grants", {
            "subject_type": "agent",
            "subject_id": args.agent_id,
            "scopes": scopes,
            "can_delegate": args.can_delegate,
            "parent_grant_id": args.parent_grant_id,
        }))


if __name__ == "__main__":
    main()
