#!/usr/bin/env python3
"""Simple Vosk WebSocket server for continuous browser streaming.

Protocol:
- Client sends raw PCM16 mono @ 16kHz as binary websocket frames.
- Server responds with JSON messages:
  - {"type": "partial", "text": "..."}
  - {"type": "final", "text": "...", "confidence": 0.0..1.0}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import websockets
from vosk import KaldiRecognizer, Model


_logger = logging.getLogger("idtx.vosk_ws")


def _compute_confidence(result: dict[str, Any]) -> float:
    words = result.get("result") or []
    if not words:
        return 1.0
    confs = [w.get("conf", 0.0) for w in words if isinstance(w, dict)]
    if not confs:
        return 1.0
    return max(0.0, min(1.0, float(sum(confs) / len(confs))))


class VoskWsServer:
    def __init__(self, model_path: Path):
        _logger.info("Loading Vosk model from %s", model_path)
        self.model = Model(str(model_path))

    async def handler(self, websocket):
        recognizer = KaldiRecognizer(self.model, 16000)
        recognizer.SetWords(True)
        _logger.info("Client connected: %s", getattr(websocket, "remote_address", "?"))

        try:
            async for message in websocket:
                if isinstance(message, str):
                    text = message.strip().lower()
                    if text == "stop":
                        break
                    continue

                if recognizer.AcceptWaveform(message):
                    final = json.loads(recognizer.Result() or "{}")
                    transcript = (final.get("text") or "").strip()
                    if transcript:
                        payload = {
                            "type": "final",
                            "text": transcript,
                            "confidence": _compute_confidence(final),
                        }
                        await websocket.send(json.dumps(payload, ensure_ascii=True))
                else:
                    partial = json.loads(recognizer.PartialResult() or "{}")
                    transcript = (partial.get("partial") or "").strip()
                    if transcript:
                        payload = {"type": "partial", "text": transcript}
                        await websocket.send(json.dumps(payload, ensure_ascii=True))
        except websockets.ConnectionClosed:
            pass
        finally:
            _logger.info("Client disconnected")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Vosk WebSocket server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2700)
    parser.add_argument(
        "--model",
        default="extra-addons/idetex/idtx_batch_quality/models/vosk_models/vosk-model-small-es-0.42",
        help="Path to Vosk model directory",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    model_path = Path(args.model).expanduser().resolve()
    if not model_path.exists():
        raise SystemExit(f"Vosk model not found: {model_path}")

    server = VoskWsServer(model_path)

    async with websockets.serve(
        server.handler,
        args.host,
        args.port,
        max_size=None,
        ping_interval=20,
        ping_timeout=20,
    ):
        _logger.info("Vosk WS listening on ws://%s:%s/ws", args.host, args.port)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
