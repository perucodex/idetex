# scale_server.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from flask import Flask, jsonify, request
import re
import sys
import time
import threading
from typing import Optional
import serial

# ===== Configuración de la balanza / puerto serie =====
SERIAL_PORT = "COM1"      # En Linux sería "/dev/ttyUSB0" o "/dev/ttyS0"
BAUDRATE   = 9600
BYTESIZE   = serial.EIGHTBITS
PARITY     = serial.PARITY_NONE
STOPBITS   = serial.STOPBITS_ONE
TIMEOUT_S  = 0.3          # segundos
# Si tu balanza requiere comando para responder (modo demanda), ponlo aquí:
READ_COMMAND: Optional[bytes] = None  # ej: b'W\r\n'  si necesitas pedir lectura
READ_INTERVAL_S = 0.2     # periodo entre lecturas

# ===== Config HTTP =====
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 5001

app = Flask(__name__)

# ===== Estado compartido =====
_last_raw = None           # última línea cruda recibida (str)
_last_weight = None        # último peso parseado (float)
_last_ts = 0.0
_lock = threading.Lock()
_stop = False
_ser: Optional[serial.Serial] = None

# Expresión para extraer un número con decimales (y signo) de la línea
NUM_RE = re.compile(r"(-?\d+(?:\.\d+)?)")

def _open_serial() -> Optional[serial.Serial]:
    """Abre el puerto serie con la configuración dada."""
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            bytesize=BYTESIZE,
            parity=PARITY,
            stopbits=STOPBITS,
            timeout=TIMEOUT_S,
        )
        return ser
    except Exception as e:
        print(f"[BALANZA] No se pudo abrir {SERIAL_PORT}: {e}", file=sys.stderr)
        return None

def _parse_weight(line: str) -> Optional[float]:
    """Devuelve el primer número float encontrado en la línea, o None."""
    if not line:
        return None
    m = NUM_RE.search(line.replace(",", "."))
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

def reader_loop():
    """Hilo lector: mantiene lectura continua y guarda la última lectura válida."""
    global _ser, _last_raw, _last_weight, _last_ts, _stop
    while not _stop:
        if _ser is None or not _ser.is_open:
            _ser = _open_serial()
            if _ser is None:
                time.sleep(1.0)
                continue

        try:
            # Si la balanza es “por demanda”, se envía un comando antes de leer
            if READ_COMMAND:
                _ser.reset_input_buffer()
                _ser.write(READ_COMMAND)
                _ser.flush()
                time.sleep(0.05)

            # Leer una línea (muchas balanzas envían CR/LF)
            raw_bytes = _ser.readline()
            line = raw_bytes.decode(errors="ignore").strip()

            weight = _parse_weight(line)
            with _lock:
                _last_raw = line
                if weight is not None:
                    _last_weight = weight
                    _last_ts = time.time()

        except Exception as e:
            print(f"[BALANZA] Error de lectura: {e}", file=sys.stderr)
            # Reintento simple: cerrar y reabrir
            try:
                if _ser:
                    _ser.close()
            except Exception:
                pass
            _ser = None
            time.sleep(1.0)
            continue

        time.sleep(READ_INTERVAL_S)

# ===== CORS simple =====
@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return resp

# ===== Rutas =====
@app.route("/peso", methods=["GET"])
def peso():
    """Devuelve el último peso conocido (cacheado)."""
    max_age = float(request.args.get("max_age", "3"))  # segundos de “vigencia”
    with _lock:
        data = {
            "ok": _last_weight is not None and (time.time() - _last_ts) <= max_age,
            "peso": _last_weight,
            "unidad": "kg",   # ajusta si tu balanza usa otras unidades
            "raw": _last_raw or '',
            "ts": _last_ts,
            "port": SERIAL_PORT,
            "baudrate": BAUDRATE,
        }
    return jsonify(data)

@app.route("/status", methods=["GET"])
def status():
    """Estado del puerto serie."""
    open_ok = _ser is not None and _ser.is_open
    return jsonify({
        "serial_open": open_ok,
        "port": SERIAL_PORT,
        "baudrate": BAUDRATE,
        "parity": PARITY,
        "stopbits": STOPBITS,
        "bytesize": BYTESIZE,
        "timeout": TIMEOUT_S,
    })

def main():
    # Iniciar hilo lector
    th = threading.Thread(target=reader_loop, daemon=True)
    th.start()
    try:
        # Servidor HTTP
        app.run(host=HTTP_HOST, port=HTTP_PORT)
        # Para producción puedes usar waitress:
        # from waitress import serve
        # serve(app, host=HTTP_HOST, port=HTTP_PORT)
    finally:
        global _stop
        _stop = True
        if _ser and _ser.is_open:
            try:
                _ser.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()

