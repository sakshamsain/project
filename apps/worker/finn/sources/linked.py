"""Fetch a PDF that a filing links to on the company's own website.

Some companies file only a letter with a link to the earnings-call transcript. FINN
follows that one link, and nothing else, so the transcript can be read and cited. The
fetch is guarded because the address comes from a document: public HTTP(S) hosts only
(no IP literals, no private, loopback or link-local addresses, checked again on every
redirect), a size cap, and the response must be a PDF.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

USER_AGENT = "Mozilla/5.0 (compatible; FINN research; filings only)"
MAX_REDIRECTS = 4

Resolver = Callable[[str], list[str]]


class LinkRefused(ValueError):
    """The address is not one FINN will fetch."""


def _resolve(host: str) -> list[str]:
    return sorted({str(info[4][0]) for info in socket.getaddrinfo(host, None)})


def check_public_url(url: str, resolve: Resolver = _resolve) -> str:
    """Returns the host if `url` is http(s) on a public host name; raises LinkRefused."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise LinkRefused(f"not http(s): {url}")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host or "." not in host or host == "localhost" or host.endswith(".local"):
        raise LinkRefused(f"not a public host: {url}")
    if parts.username or parts.password:
        raise LinkRefused(f"credentials in link: {url}")
    if parts.port not in (None, 80, 443):
        raise LinkRefused(f"unusual port: {url}")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        raise LinkRefused(f"IP address instead of a host name: {url}")
    addrs = resolve(host)
    if not addrs:
        raise LinkRefused(f"host does not resolve: {url}")
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if not ip.is_global:
            raise LinkRefused(f"{host} resolves to a non-public address")
    return host


def fetch_linked_pdf(
    url: str, max_bytes: int = 30_000_000, resolve: Resolver = _resolve, timeout_s: float = 60.0
) -> bytes | None:
    """The PDF at `url`, or None when it is missing, too large or not a PDF."""
    import httpx

    with httpx.Client(
        follow_redirects=False, timeout=timeout_s, headers={"User-Agent": USER_AGENT}
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            check_public_url(url, resolve)
            with client.stream("GET", url) as r:
                if r.status_code in (301, 302, 303, 307, 308) and "location" in r.headers:
                    url = urljoin(url, r.headers["location"])
                    continue
                if r.status_code >= 400:
                    return None
                declared = r.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    return None
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > max_bytes:
                        return None
                data = bytes(buf)
                return data if data.lstrip()[:5] == b"%PDF-" else None
    return None
