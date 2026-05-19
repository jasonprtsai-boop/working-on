from __future__ import annotations

import ipaddress
from typing import Iterable

from flask import request

from backend.utils import config


def _configured_proxy_networks() -> Iterable[ipaddress._BaseNetwork]:
    configured = getattr(config, "TRUSTED_PROXY_IPS", ()) or ()
    if isinstance(configured, str):
        configured = [part.strip() for part in configured.split(",")]

    for raw_value in configured:
        value = str(raw_value).strip()
        if not value or value == "*":
            continue
        try:
            yield ipaddress.ip_network(value, strict=False)
        except ValueError:
            continue


def _is_trusted_proxy(remote_addr: str | None) -> bool:
    if not getattr(config, "TRUST_X_FORWARDED_FOR", False):
        return False
    if not remote_addr:
        return False
    try:
        peer = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False
    return any(peer in network for network in _configured_proxy_networks())


def _first_forwarded_for_ip() -> str | None:
    forwarded = request.headers.get("X-Forwarded-For") or ""
    for raw_value in forwarded.split(","):
        value = raw_value.strip()
        if not value:
            continue
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            return None
    return None


def client_ip() -> str:
    """Return the caller identity used for rate limits and security attribution."""
    remote_addr = request.remote_addr or "unknown"
    if _is_trusted_proxy(request.remote_addr):
        forwarded = _first_forwarded_for_ip()
        if forwarded:
            return forwarded
    return remote_addr
