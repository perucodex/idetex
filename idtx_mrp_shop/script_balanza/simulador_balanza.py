# simulador_balanza.py
# -*- coding: utf-8 -*-
"""Simulador de balanza por puerto serie (para pruebas del Taller sin hardware).

Emite tramas con el mismo formato que parsean balanza.py y el diálogo
"Selecciona una balanza" del shop floor (select_scale_dialog.js):

    ST,GS,+   22.50 KG      <- peso estable
    US,GS,+   13.72 KG      <- peso inestable (subiendo/bajando)

Se usa junto con el módulo de kernel tty0tty, que crea pares null-módem
virtuales /dev/tnt0 <-> /dev/tnt1 (lo escrito en uno sale por el otro) y se
registra como driver tipo "serial", por lo que Chrome SÍ lo muestra en el
selector de Web Serial (a diferencia de un pty de socat):

    sudo insmod /home/jpc/tty0tty/module/tty0tty.ko
    sudo chmod 666 /dev/tnt*
    python3 simulador_balanza.py /dev/tnt1      # el Taller se conecta a tnt0

Ciclo simulado (se repite): balanza en 0 -> se carga el rollo (peso sube,
inestable) -> se estabiliza en el peso objetivo -> se retira el rollo.
Solo usa la librería estándar (no requiere pyserial).
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import termios
import time


def abrir_puerto(ruta: str) -> int:
    fd = os.open(ruta, os.O_WRONLY | os.O_NOCTTY)
    try:
        attrs = termios.tcgetattr(fd)
        # crudo: sin postprocesado (que no convierta \n ni corte la trama)
        attrs[1] &= ~termios.OPOST  # oflag
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except termios.error:
        pass  # si no es un tty real, se escribe igual
    return fd


def enviar(fd: int, estable: bool, peso: float, mostrar: bool = True) -> None:
    prefijo = "ST" if estable else "US"
    linea = f"{prefijo},GS,+{peso:8.2f} KG\r\n"
    os.write(fd, linea.encode("ascii"))
    if mostrar:
        sys.stdout.write(f"\r-> {linea.strip():<28}")
        sys.stdout.flush()


def ciclo(fd: int, objetivo: float, intervalo: float) -> None:
    # 1) vacía y estable
    for _ in range(int(2 / intervalo)):
        enviar(fd, True, 0.0)
        time.sleep(intervalo)
    # 2) se carga el rollo: sube con ruido, inestable
    pasos = max(1, int(3 / intervalo))
    for i in range(1, pasos + 1):
        peso = objetivo * i / pasos + random.uniform(-0.4, 0.4)
        enviar(fd, False, max(0.0, peso))
        time.sleep(intervalo)
    # 3) estable en el objetivo (aquí el Taller permite Confirmar)
    for _ in range(int(8 / intervalo)):
        enviar(fd, True, objetivo + random.choice((0.0, 0.0, 0.01, -0.01)))
        time.sleep(intervalo)
    # 4) se retira el rollo
    for _ in range(int(1 / intervalo)):
        enviar(fd, False, random.uniform(0.0, objetivo / 3))
        time.sleep(intervalo)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador de balanza serie")
    parser.add_argument("puerto", nargs="?", default="/dev/tnt1",
                        help="puerto donde escribir (default /dev/tnt1; el Taller lee del par, tnt0)")
    parser.add_argument("--peso", type=float, default=None,
                        help="peso objetivo fijo en kg (default: aleatorio entre --min y --max)")
    parser.add_argument("--min", type=float, default=18.0, dest="peso_min")
    parser.add_argument("--max", type=float, default=24.0, dest="peso_max")
    parser.add_argument("--intervalo", type=float, default=0.2,
                        help="segundos entre tramas (default 0.2 = 5 tramas/s)")
    parser.add_argument("--estatico", action="store_true",
                        help="emitir siempre el mismo peso estable (sin ciclo de carga)")
    args = parser.parse_args()

    fd = abrir_puerto(args.puerto)
    print(f"Simulando balanza en {args.puerto} (Ctrl+C para salir)")
    try:
        if args.estatico:
            peso = args.peso if args.peso is not None else 22.5
            while True:
                enviar(fd, True, peso)
                time.sleep(args.intervalo)
        while True:
            objetivo = args.peso if args.peso is not None else round(
                random.uniform(args.peso_min, args.peso_max), 2)
            ciclo(fd, objetivo, args.intervalo)
    except KeyboardInterrupt:
        print("\nfin")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
