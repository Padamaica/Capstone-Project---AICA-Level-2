"""Data-localisation guardrails.

1. `assert_local_endpoint(url)`: refuses to send data to any host that is not loopback,
   a private network (RFC1918), or explicitly allow-listed as an in-country endpoint.
2. `enable_outbound_guard()`: process-wide socket guard. Any library that tries to
   "phone home" (telemetry, a foreign AI API, etc.) gets blocked.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from .config import settings


class DataLocalisationError(RuntimeError):
    """Raised when data would leave the approved (in-country / on-prem) boundary."""


def _is_private_host(host: str) -> bool:
    if host in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except ValueError:
        pass
    # Docker-compose service names (no dots), e.g. "ollama", "vllm"
    if "." not in host:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return all(_is_private_ip(info[4][0]) for info in infos)


def _is_private_ip(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except ValueError:
        return False


def is_approved_host(host: str) -> bool:
    host = (host or "").lower()
    return host in {h.lower() for h in settings.allowed_llm_hosts} or _is_private_host(host)


def assert_local_endpoint(url: str) -> None:
    host = urlparse(url).hostname or ""
    if not is_approved_host(host):
        raise DataLocalisationError(
            f"Blocked: '{host}' is not a local/private or allow-listed in-country endpoint. "
            "Add it to ALLOWED_LLM_HOSTS only if it is hosted inside your approved region."
        )


_original_create_connection = socket.create_connection
_guard_enabled = False


def enable_outbound_guard() -> None:
    """Monkey-patch socket.create_connection so only approved hosts can be reached."""
    global _guard_enabled
    if _guard_enabled:
        return

    def guarded_create_connection(address, *args, **kwargs):
        host = address[0]
        if not is_approved_host(str(host)):
            raise DataLocalisationError(f"Outbound connection to '{host}' blocked by data-localisation guard.")
        return _original_create_connection(address, *args, **kwargs)

    socket.create_connection = guarded_create_connection  # type: ignore[assignment]
    _guard_enabled = True


def disable_outbound_guard() -> None:
    global _guard_enabled
    socket.create_connection = _original_create_connection  # type: ignore[assignment]
    _guard_enabled = False
