#!/usr/bin/env python3
"""
Quality Monitor Webhook Server

Receives notifications from the backend when:
- A new digest is generated
- A batch of classifications is completed
- Email volume threshold is reached

This allows immediate analysis instead of waiting for polling interval.

Usage:
    python webhook_server.py --port 9000
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
LOG_FILE = SCRIPT_DIR / "webhook.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class WebhookHandler(BaseHTTPRequestHandler):
    """Handle webhook requests from backend"""

    def do_POST(self):
        """Handle POST requests"""
        if self.path == "/webhook/digest-generated":
            self.handle_digest_generated()
        elif self.path == "/webhook/classification-batch":
            self.handle_classification_batch()
        else:
            self.send_error(404, "Not Found")

    def handle_digest_generated(self):
        """Handle digest generation notification"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            session_id = data.get("session_id")
            email_count = data.get("email_count", 0)

            logger.info(f"Digest generated: session_id={session_id}, emails={email_count}")

            # Trigger quality analysis
            self.trigger_analysis("digest_generated", session_id, email_count)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())

        except Exception as e:
            logger.error(f"Error handling digest webhook: {e}")
            self.send_error(500, str(e))

    def handle_classification_batch(self):
        """Handle classification batch notification"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            email_count = data.get("email_count", 0)
            session_id = data.get("session_id")

            logger.info(f"Classification batch: session_id={session_id}, emails={email_count}")

            # Trigger analysis if threshold met
            self.trigger_analysis("classification_batch", session_id, email_count)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())

        except Exception as e:
            logger.error(f"Error handling batch webhook: {e}")
            self.send_error(500, str(e))

    def trigger_analysis(self, trigger_type: str, session_id: str, email_count: int):
        """Trigger quality analysis"""
        logger.info(
            f"Triggering analysis: type={trigger_type}, session={session_id}, emails={email_count}"
        )

        # Run quality monitor analysis in background
        try:
            quality_monitor_script = SCRIPT_DIR / "quality_monitor.py"
            # Pass session_id if available for targeted analysis
            args = ["python3", str(quality_monitor_script), "--analyze-now"]
            if session_id:
                args.extend(["--session-id", session_id])

            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Quality analysis triggered successfully for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to trigger analysis: {e}")

    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")


def main():
    parser = argparse.ArgumentParser(description="Quality Monitor Webhook Server")
    parser.add_argument("--port", type=int, default=9000, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), WebhookHandler)

    logger.info(f"Starting webhook server on {args.host}:{args.port}")
    logger.info("Endpoints:")
    logger.info(f"  POST http://{args.host}:{args.port}/webhook/digest-generated")
    logger.info(f"  POST http://{args.host}:{args.port}/webhook/classification-batch")
    logger.info("")
    logger.info("Waiting for webhooks...")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down webhook server...")
        server.shutdown()


if __name__ == "__main__":
    main()
