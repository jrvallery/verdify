# backend/scripts/wait_for_http.py
import sys, time, json, urllib.request, urllib.error

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/openapi.json"
expect = None
if "--expect" in sys.argv:
    idx = sys.argv.index("--expect")
    if idx + 1 < len(sys.argv):
        expect = sys.argv[idx + 1]

deadline = time.time() + 90  # up to 90s on cold envs
last_err = None

def body_contains(data: bytes, needle: str) -> bool:
    try:
        # Try JSON first, fall back to bytes search
        obj = json.loads(data.decode("utf-8", "ignore"))
        return needle in obj or needle in json.dumps(obj)
    except Exception:
        return needle.encode() in data

while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            if 200 <= resp.status < 500:
                if expect is None:
                    sys.exit(0)
                data = resp.read() or b""
                if body_contains(data, expect):
                    sys.exit(0)
    except Exception as e:
        last_err = e
    time.sleep(0.5)

print(f"Timed out waiting for {url} ({last_err})")
sys.exit(1)
