import pytest

from finn.sources.linked import LinkRefused, check_public_url


def public(_host: str) -> list[str]:
    return ["104.18.10.10"]


def test_public_https_host_is_allowed() -> None:
    assert check_public_url("https://glenmark.b-cdn.net/a.pdf", public) == "glenmark.b-cdn.net"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/a.pdf",
        "http://localhost/a.pdf",
        "http://127.0.0.1/a.pdf",
        "http://[::1]/a.pdf",
        "http://169.254.169.254/latest/meta-data",
        "https://user:pw@example.com/a.pdf",
        "https://example.com:8443/a.pdf",
        "https://intranet/a.pdf",
    ],
)
def test_refused_addresses(url: str) -> None:
    with pytest.raises(LinkRefused):
        check_public_url(url, public)


@pytest.mark.parametrize(
    "addr", ["10.0.0.5", "192.168.1.2", "127.0.0.1", "169.254.169.254", "fd00::1"]
)
def test_host_names_resolving_to_private_addresses_are_refused(addr: str) -> None:
    with pytest.raises(LinkRefused):
        check_public_url("https://files.example.com/a.pdf", lambda _h: ["1.1.1.1", addr])
