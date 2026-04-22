"""
SSE Bridge Proxy for NoDesk AI Gateway.

The AI Gateway doesn't support SSE streaming - it returns plain JSON even
when stream=true. OpenClaw requires SSE format. This proxy bridges the gap
by forwarding requests (with stream=false) and wrapping responses in SSE.

Usage:
    python3 sse-bridge.py --port 18083 --upstream http://127.0.0.1:18081
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread


class SSEBridgeHandler(BaseHTTPRequestHandler):
    upstream: str = ""

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        upstream_url = f"{self.upstream.rstrip('/')}{self.path}"

        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}

        wants_stream = payload.pop("stream", False)
        payload["stream"] = False

        forwarded_body = json.dumps(payload).encode("utf-8")

        auth = self.headers.get("Authorization", "")
        req = urllib.request.Request(
            upstream_url,
            data=forwarded_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": auth,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp_body = resp.read()
                resp_data = json.loads(resp_body)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(error_body.encode("utf-8"))
            return
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        if not wants_stream:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp_data).encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        choices = resp_data.get("choices", [])
        chunk_id = resp_data.get("id", "chatcmpl-bridge")
        model = resp_data.get("model", "unknown")
        created = resp_data.get("created", 0)

        for choice in choices:
            msg = choice.get("message", {})
            content = msg.get("content", "")
            finish_reason = choice.get("finish_reason")
            index = choice.get("index", 0)

            if content:
                chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [
                        {
                            "index": index,
                            "delta": {"role": "assistant", "content": content},
                            "finish_reason": None,
                        }
                    ],
                }
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
                self.wfile.flush()

            if finish_reason:
                done_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [
                        {
                            "index": index,
                            "delta": {},
                            "finish_reason": finish_reason,
                        }
                    ],
                }
                if "usage" in resp_data:
                    done_chunk["usage"] = resp_data["usage"]
                self.wfile.write(f"data: {json.dumps(done_chunk)}\n\n".encode("utf-8"))
                self.wfile.flush()

        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self):
        upstream_url = f"{self.upstream.rstrip('/')}{self.path}"
        auth = self.headers.get("Authorization", "")
        req = urllib.request.Request(
            upstream_url,
            headers={"Authorization": auth} if auth else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, format, *args):
        sys.stderr.write(f"[sse-bridge] {args[0]} {args[1]} {args[2]}\n")


def main():
    parser = argparse.ArgumentParser(description="SSE Bridge for NoDesk AI Gateway")
    parser.add_argument("--port", type=int, default=18083)
    parser.add_argument("--upstream", default="http://127.0.0.1:18081")
    parser.add_argument("--bind", default="0.0.0.0")
    args = parser.parse_args()

    SSEBridgeHandler.upstream = args.upstream

    server = HTTPServer((args.bind, args.port), SSEBridgeHandler)
    print(f"[sse-bridge] Listening on {args.bind}:{args.port} -> {args.upstream}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
