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


def _env() -> dict[str, str]:
    env: dict[str, str] = {}
    text = DOCKERFILE.read_text().replace("\\\n", " ")
    for line in re.findall(r"^ENV (.+)$", text, re.MULTILINE):
        for pair in line.split():
            key, _, value = pair.partition("=")
            env[key] = value
    return env


def test_the_image_checks_liveness_and_sets_the_data_paths():
    text = DOCKERFILE.read_text()
    healthcheck = re.search(r"^HEALTHCHECK .*?CMD (.+)$", text.replace("\\\n", " "), re.MULTILINE)
    assert healthcheck, "Dockerfile has no HEALTHCHECK"
    # Liveness, never readiness: a Mongo blip must not get a healthy container killed.
    assert "/api/health/live" in healthcheck.group(1)

    env = _env()
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["STORAGE_LOCAL_DIR"] == "/app/storage"
    assert env["CHROMA_PATH"] == "/app/chroma"
    assert env["SEED_ON_STARTUP"] == "true"
    assert env["DATABASE_NAME"] == "folio"
    assert env["ENVIRONMENT"] == "production"

    # Both data directories exist in the image, owned by the runtime uid, so a new named
    # volume mounted there starts with that owner.
    assert re.search(r"mkdir -p /app/storage /app/chroma", text)
    assert re.search(r"useradd [^\n]*--uid 10001", text)
    assert "chown -R app:app /app" in text
    assert re.search(r"^USER app$", text, re.MULTILINE)
