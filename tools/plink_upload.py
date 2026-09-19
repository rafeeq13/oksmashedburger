"""Upload a file to production when pscp fails (base64 chunks over plink)."""
import base64
import subprocess
import sys
from pathlib import Path

HOST = "root@2.24.192.10"
PORT = "3003"
PW = "FxSgigB@2JEL9w"
PLINK = r"C:\Program Files\PuTTY\plink.exe"
CHUNK = 2000


def plink(cmd: str) -> None:
    line = (
        f'echo y | "{PLINK}" -ssh {HOST} -P {PORT} -pw {PW} -batch "{cmd}"'
    )
    r = subprocess.run(line, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout or f"plink failed: {cmd[:80]}")


def main():
    local = Path(sys.argv[1])
    remote = sys.argv[2]
    data = local.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    plink(f"rm -f {remote}.b64 {remote}")
    for i in range(0, len(b64), CHUNK):
        part = b64[i : i + CHUNK]
        # base64 alphabet is shell-safe inside single quotes
        plink(f"printf '%s' '{part}' >> {remote}.b64")
    plink(f"base64 -d {remote}.b64 > {remote} && rm -f {remote}.b64 && wc -c {remote}")
    print("uploaded", local, "->", remote)


if __name__ == "__main__":
    main()
