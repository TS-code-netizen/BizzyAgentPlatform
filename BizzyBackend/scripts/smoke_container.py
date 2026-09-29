import json
import sys
import time
import urllib.error
import urllib.request

endpoint = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9000/2015-03-31/functions/function/invocations"


def event(path):
    return {"version": "2.0", "routeKey": f"GET {path}", "rawPath": path, "rawQueryString": "", "headers": {"host": "localhost"},
        "requestContext": {"http": {"method": "GET", "path": path, "sourceIp": "127.0.0.1", "protocol": "HTTP/1.1"}}, "isBase64Encoded": False}


for attempt in range(20):
    try:
        request = urllib.request.Request(endpoint, data=json.dumps(event("/ready")).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.load(response)
        if payload.get("statusCode") != 200:
            raise RuntimeError(f"Readiness failed: {payload.get('statusCode')}")
        break
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        if attempt == 19:
            raise
        time.sleep(1)
for path in ("/api/v1/sales/summary", "/api/v1/inventory/status", "/api/v1/finance/summary"):
    request = urllib.request.Request(endpoint, data=json.dumps(event(path)).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    if payload.get("statusCode") != 200 or json.loads(payload["body"]).get("status") != "success":
        raise RuntimeError(f"Packaged-data smoke failed for {path}")
print("Lambda container readiness and packaged data smoke passed.")
