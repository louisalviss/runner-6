#!/usr/bin/env python3
"""One-shot, loopback-only OpenRouter budget rail for an opt-in DSH Flash canary.

Conservative reservation ceilings, not a guarantee of the provider's final bill.
No task, credential, generated text, or raw upstream response is logged.
"""
import http.server
import json
import os
import pathlib
import secrets
import sys
import urllib.error
import urllib.request

MODEL = "deepseek/deepseek-v4.1-flash-1017"
PORT = int(os.environ.get("DSH_GUARD_PORT", "18731"))
MAX_CALLS = int(os.environ.get("DSH_GUARD_MAX_CALLS", "10"))
MAX_BODY = int(os.environ.get("DSH_GUARD_MAX_BODY_BYTES", "150000"))
MAX_OUTPUT = int(os.environ.get("DSH_GUARD_MAX_OUTPUT_TOKENS", "2048"))
MAX_RESERVE = float(os.environ.get("DSH_GUARD_MAX_RESERVED_USD", "0.20"))
# Deliberately above the published direct DeepSeek price, with a safety margin.
INPUT_UPPER_PER_M = float(os.environ.get("DSH_GUARD_INPUT_UPPER_PER_M", "0.75"))
OUTPUT_UPPER_PER_M = float(os.environ.get("DSH_GUARD_OUTPUT_UPPER_PER_M", "1.50"))
RESULT = pathlib.Path(os.environ["DSH_GUARD_REPORT"])
KEY = os.environ["DSH_UPSTREAM_KEY"]
CLIENT_TOKEN = os.environ["DSH_GUARD_CLIENT_TOKEN"]
TEST = os.environ.get("DSH_GUARD_TEST_MODE") == "1"
UPSTREAM = os.environ.get("DSH_GUARD_UPSTREAM", "https://openrouter.ai/api/v1")
if not TEST and UPSTREAM != "https://openrouter.ai/api/v1":
    raise SystemExit("UNSAFE_UPSTREAM")
if not TEST and (MAX_CALLS > 12 or MAX_OUTPUT > 2048 or MAX_RESERVE > .20):
    raise SystemExit("LIMIT_TOO_HIGH")
if not KEY or not CLIENT_TOKEN or MAX_CALLS < 1 or MAX_BODY < 1024 or MAX_RESERVE <= 0:
    raise SystemExit("INVALID_CONFIG")

state = {"requests_accepted": 0, "requests_rejected": 0,
         "reserved_usd": 0.0, "observed_usage_cost_usd": 0.0,
         "usage_reported_requests": 0, "last_rejection": None}

def save():
    tmp = RESULT.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, separators=(",", ":")))
    tmp.replace(RESULT)

class Guard(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *_args):
        pass

    def send_error_json(self, status, reason):
        state["requests_rejected"] += 1
        state["last_rejection"] = reason
        save()
        payload = json.dumps({"error": {"message": reason, "type": "budget_guard"}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path != "/healthz":
            self.send_error_json(404, "NOT_FOUND")
            return
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        if self.path != "/api/v1/chat/completions":
            self.send_error_json(404, "INVALID_ROUTE")
            return
        if not secrets.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + CLIENT_TOKEN
        ):
            self.send_error_json(401, "LOCAL_AUTH_REJECTED")
            return
        try:
            count = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            count = 0
        if not 0 < count <= MAX_BODY:
            self.send_error_json(413, "PROMPT_BYTES_LIMIT")
            return
        raw = self.rfile.read(count)
        try:
            body = json.loads(raw)
            assert isinstance(body, dict) and body.get("model") == MODEL
            assert isinstance(body.get("messages"), list)
            ceiling = body.get("max_completion_tokens", body.get("max_tokens", MAX_OUTPUT))
            ceiling = int(ceiling)
            assert 1 <= ceiling <= MAX_OUTPUT
            # No multimodal payloads or external providers under this budget estimate.
            assert all(isinstance(x, dict) for x in body["messages"])
        except (AssertionError, TypeError, ValueError, KeyError):
            self.send_error_json(422, "MODEL_OR_TOKEN_LIMIT")
            return
        # UTF-8 byte count overestimates normal text token counts; +4096
        # reserves additional structural/hidden token overhead per request.
        reserve = ((count + 4096) * INPUT_UPPER_PER_M +
                   ceiling * OUTPUT_UPPER_PER_M) / 1_000_000
        if state["requests_accepted"] >= MAX_CALLS:
            self.send_error_json(429, "MAX_REQUESTS")
            return
        if state["reserved_usd"] + reserve > MAX_RESERVE:
            self.send_error_json(429, "LOCAL_BUDGET_RESERVED")
            return
        state["requests_accepted"] += 1
        state["reserved_usd"] = round(state["reserved_usd"] + reserve, 9)
        save()  # fail-closed, reserve BEFORE the remote call

        # Restrict endpoint prices without pinning an unavailable provider.
        # OpenRouter max_price uses USD per million tokens.
        body["provider"] = {"sort": "price", "max_price": {"prompt": INPUT_UPPER_PER_M, "completion": OUTPUT_UPPER_PER_M}}
        request = urllib.request.Request(
            UPSTREAM + "/chat/completions",
            data=json.dumps(body, separators=(",", ":")).encode(),
            headers={"Authorization": "Bearer " + KEY,
                     "Content-Type": "application/json",
                     "Accept": "text/event-stream, application/json"},
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=110)
        except urllib.error.HTTPError as exc:
            # Forward only the HTTP code and a generic body, not upstream errors.
            self.send_error_json(exc.code, "PROVIDER_HTTP_" + str(exc.code))
            return
        except Exception:
            self.send_error_json(502, "PROVIDER_NETWORK_FAILURE")
            return
        try:
            self.send_response(response.status)
            self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            buffer = b""
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
                # SSE messages may include the actual cost in final usage data.
                buffer = (buffer + chunk)[-65536:]
            try:
                text = buffer.decode("utf-8", "replace")
                blocks = [line[6:] for line in text.splitlines() if line.startswith("data: ")]
                if blocks:
                    for value in reversed(blocks):
                        if value == "[DONE]":
                            continue
                        obj = json.loads(value)
                        usage = obj.get("usage") or {}
                        if "cost" in usage:
                            state["observed_usage_cost_usd"] += float(usage["cost"])
                            state["usage_reported_requests"] += 1
                            break
                else:
                    obj = json.loads(text)
                    usage = obj.get("usage") or {}
                    if "cost" in usage:
                        state["observed_usage_cost_usd"] += float(usage["cost"])
                        state["usage_reported_requests"] += 1
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
            save()
        except (BrokenPipeError, ConnectionResetError):
            save()
        finally:
            response.close()
            self.close_connection = True

if __name__ == "__main__":
    save()
    http.server.HTTPServer(("127.0.0.1", PORT), Guard).serve_forever()
