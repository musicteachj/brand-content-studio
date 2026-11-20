"""The Dockerfile's CMD carries the serving flags the load balancer setup relies on."""
import json
import re
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"


def _cmd() -> list[str]:
    match = re.search(r"^CMD (\[.*\])\s*$", DOCKERFILE.read_text(), re.MULTILINE)
    assert match, "Dockerfile has no JSON-array CMD"
    return json.loads(match.group(1))


def _has_pair(cmd: list[str], flag: str, value: str) -> bool:
    return any(a == flag and b == value for a, b in zip(cmd, cmd[1:], strict=False))


def test_cmd_trusts_proxy_headers():
    assert "--proxy-headers" in _cmd()


def test_cmd_keeps_connections_alive_past_the_alb_idle_timeout():
    assert _has_pair(_cmd(), "--timeout-keep-alive", "130")


def test_cmd_stops_gracefully_inside_the_container_stop_window():
    assert _has_pair(_cmd(), "--timeout-graceful-shutdown", "25")


def test_cmd_takes_trusted_proxies_from_the_environment_and_runs_one_worker():
    cmd = _cmd()
    assert "--forwarded-allow-ips" not in cmd
    assert "--workers" not in cmd
