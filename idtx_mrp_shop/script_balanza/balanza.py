# scale_server.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from flask import Flask, jsonify, request, make_response
import re
import sys
import time
import threading
from typing import Optional
import serial

# ===============================
# Configuración de balanza / puerto serie
# ===============================
SERIAL_PORT = "COM1"      # Linux: "/dev/ttyUSB0" o "/dev/ttyS0"
BAUDRATE = 9600
BYTESIZE = serial.EIGHTBITS
PARITY = serial.PARITY_NONE
STOPBITS = serial.STOPBITS_ONE
TIMEOUT_S = 0.3
READ_INTERVAL_S = 0.2

# Si tu balanza necesita comando de lectura (modo demanda), ejemplo: b"W\r\n"
READ_COMMAND: Optional[bytes] = None

# ===============================
# Configuración HTTP (local/LAN)
# ===============================
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 5001

app = Flask(__name__)

# ===============================
# Estado compartido
# ===============================
_state_lock = threading.Lock()
_stop_event = threading.Event()

_last_raw: str = ""
_last_weight: Optional[float] = None
_last_stable: Optional[bool] = None
_last_ts_wall: float = 0.0      # time.time() (para exponer en API)
_last_ts_mono: float = 0.0      # time.monotonic() (para max_age)
_last_error: str = ""

_ser: Optional[serial.Serial] = None

WEIGHT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*KG", re.IGNORECASE)


def _set_error(msg: str) -> None:
    global _last_error
    with _state_lock:
        _last_error = msg


def _open_serial() -> Optional[serial.Serial]:
    """Abre el puerto serie."""
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            bytesize=BYTESIZE,
            parity=PARITY,
            stopbits=STOPBITS,
            timeout=TIMEOUT_S,
        )
        try:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except Exception:
            pass
        _set_error("")
        return ser
    except Exception as e:
        msg = f"No se pudo abrir {SERIAL_PORT}: {e}"
        print(f"[BALANZA] {msg}", file=sys.stderr)
        _set_error(msg)
        return None


def _parse_weight(line: str) -> Optional[float]:
    """
    Extrae el peso si la trama contiene KG.
    Soporta:
      ST,GS,    0.00KG
      US,GS,   12.35KG
      22.50 KG
    """
    if not line:
        return None

    clean = line.replace("\x00", "").replace(",", ".").strip()
    m = WEIGHT_RE.search(clean)
    if not m:
        return None

    try:
        return float(m.group(1))
    except Exception:
        return None


def _parse_stability(line: str) -> Optional[bool]:
    """ST = estable, US = inestable."""
    if not line:
        return None
    up = line.strip().upper()
    if up.startswith("ST"):
        return True
    if up.startswith("US"):
        return False
    return None


def reader_loop():
    """Hilo lector: mantiene el último peso en memoria."""
    global _ser, _last_raw, _last_weight, _last_stable, _last_ts_wall, _last_ts_mono, _last_error

    while not _stop_event.is_set():
        if _ser is None or not _ser.is_open:
            _ser = _open_serial()
            if _ser is None:
                _stop_event.wait(1.0)
                continue

        try:
            if READ_COMMAND:
                try:
                    _ser.reset_input_buffer()
                except Exception:
                    pass
                _ser.write(READ_COMMAND)
                _ser.flush()
                time.sleep(0.05)

            raw_bytes = _ser.readline()
            line = raw_bytes.decode(errors="ignore").strip() if raw_bytes else ""

            weight = _parse_weight(line)
            stable = _parse_stability(line)

            with _state_lock:
                _last_raw = line
                if stable is not None:
                    _last_stable = stable
                if weight is not None:
                    _last_weight = weight
                    _last_ts_wall = time.time()
                    _last_ts_mono = time.monotonic()
                    _last_error = ""

        except Exception as e:
            msg = f"Error de lectura: {e}"
            print(f"[BALANZA] {msg}", file=sys.stderr)
            _set_error(msg)
            try:
                if _ser:
                    _ser.close()
            except Exception:
                pass
            _ser = None
            _stop_event.wait(1.0)
            continue

        _stop_event.wait(READ_INTERVAL_S)

    try:
        if _ser and _ser.is_open:
            _ser.close()
    except Exception:
        pass


# ===============================
# Headers (sin caché)
# ===============================
@app.before_request
def _handle_options():
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        return _add_common_headers(resp)
    return None


@app.after_request
def _after_request(resp):
    return _add_common_headers(resp)


def _add_common_headers(resp):
    # CORS no es estrictamente necesario con el proxy vía Odoo,
    # pero lo dejamos por si pruebas directo desde navegador local.
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"

    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ===============================
# Endpoints
# ===============================
@app.route("/peso", methods=["GET", "OPTIONS"])
def peso():
    """
    Devuelve el último peso cacheado en memoria.

    Query params:
      - max_age: segundos máximos de vigencia (default 3)
    """
    try:
        max_age = float(request.args.get("max_age", "3"))
        if max_age < 0:
            max_age = 0.0
    except Exception:
        max_age = 3.0

    now_mono = time.monotonic()

    with _state_lock:
        age = (now_mono - _last_ts_mono) if _last_ts_mono else None
        ok = _last_weight is not None and age is not None and age <= max_age

        payload = {
            "ok": ok,
            "peso": _last_weight,
            "unidad": "kg",
            "stable": _last_stable,     # ✅ estabilidad para JS/Odoo
            "raw": _last_raw or "",
            "ts": _last_ts_wall,
            "age_s": round(age, 3) if age is not None else None,
            "port": SERIAL_PORT,
            "baudrate": BAUDRATE,
            "error": _last_error or "",
        }

    return jsonify(payload)


@app.route("/status", methods=["GET", "OPTIONS"])
def status():
    ser_open = False
    try:
        ser_open = _ser is not None and _ser.is_open
    except Exception:
        ser_open = False

    with _state_lock:
        payload = {
            "serial_open": ser_open,
            "port": SERIAL_PORT,
            "baudrate": BAUDRATE,
            "parity": str(PARITY),
            "stopbits": str(STOPBITS),
            "bytesize": int(BYTESIZE),
            "timeout": TIMEOUT_S,
            "last_weight": _last_weight,
            "last_stable": _last_stable,
            "last_raw": _last_raw,
            "last_ts": _last_ts_wall,
            "last_error": _last_error,
        }
    return jsonify(payload)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "scale_server"})


def main():
    th = threading.Thread(target=reader_loop, daemon=True, name="scale-reader")
    th.start()

    try:
        app.run(
            host=HTTP_HOST,
            port=HTTP_PORT,
            debug=False,
            use_reloader=False,  # evita doble hilo
            threaded=True,
        )
    finally:
        _stop_event.set()
        th.join(timeout=2.0)
        try:
            if _ser and _ser.is_open:
                _ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
