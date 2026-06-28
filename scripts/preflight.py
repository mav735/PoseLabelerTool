import os
import re
import subprocess
import sys

_PUB = re.compile(r"0\.0\.0\.0:(\d+)->")


def parse_used_ports(docker_ps_output: str) -> set:
    return {int(m) for m in _PUB.findall(docker_ps_output)}


def _app_port() -> int:
    env = os.path.join(os.path.dirname(__file__), "..", ".env")
    port = 8080
    if os.path.exists(env):
        for line in open(env):
            if line.strip().startswith("APP_PORT="):
                try:
                    port = int(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
    return port


def main() -> int:
    port = _app_port()
    try:
        out = subprocess.run(["docker", "ps", "--format", "{{.Ports}}"],
                             capture_output=True, text=True, check=True).stdout
    except Exception as e:
        print(f"preflight: could not run docker ps ({e}); skipping check")
        return 0
    used = parse_used_ports(out)
    if port in used:
        print(f"preflight: ERROR - app port {port} is already published by another container.")
        print("Pick a free port: set APP_PORT in .env to an unused value, then `docker compose up` again.")
        return 1
    print(f"preflight: OK - app port {port} is free.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
