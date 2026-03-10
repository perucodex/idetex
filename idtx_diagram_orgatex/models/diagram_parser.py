import io
import math
import re
import statistics
import struct
from collections import Counter
from datetime import datetime
from typing import Any, List, Dict, Optional

# Matplotlib might be required
import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

COMMON_PRG_VALUES = {
    1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0, 15.0,
    20.0, 22.0, 24.0, 25.0, 30.0, 35.0, 40.0, 42.0, 45.0, 50.0, 55.0,
    56.0, 58.0, 60.0, 63.0, 67.0, 68.0, 70.0, 73.0, 75.0, 80.0, 90.0,
    98.0, 100.0, 106.0, 120.0, 135.0,
}
DEFAULT_PALETTE = [40.0, 60.0, 70.0, 80.0]


def extract_ascii_runs(data: bytes, min_len: int = 4) -> List[Dict[str, Any]]:
    runs: List[Dict[str, Any]] = []
    start: Optional[int] = None
    for i, b in enumerate(data):
        ok = 32 <= b < 127 or b in (9, 10, 13)
        if ok:
            if start is None:
                start = i
        else:
            if start is not None and i - start >= min_len:
                raw = data[start:i]
                text = raw.decode("latin1", errors="ignore").strip("\x00\r\n\t ")
                if text:
                    runs.append({"offset": start, "text": text})
            start = None
    if start is not None and len(data) - start >= min_len:
        raw = data[start:]
        text = raw.decode("latin1", errors="ignore").strip("\x00\r\n\t ")
        if text:
            runs.append({"offset": start, "text": text})
    return runs


def candidate_values_from_window(data: bytes, start: int, end: int) -> List[float]:
    start = max(0, start)
    end = min(len(data), end)
    found: List[float] = []
    for i in range(start, end - 3):
        try:
            v = struct.unpack_from("<f", data, i)[0]
        except struct.error:
            continue
        if math.isfinite(v) and v in COMMON_PRG_VALUES and v not in found:
            found.append(v)
    return found


def parse_prg(data: bytes) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    for run in extract_ascii_runs(data, 4):
        text = run["text"]
        if not any(ch.isalpha() for ch in text):
            continue
        off = run["offset"]
        if off < 6:
            continue
        op_id = int.from_bytes(data[off - 6 : off - 4], "big", signed=False)
        step_id = int.from_bytes(data[off - 4 : off - 2], "big", signed=False)
        params = candidate_values_from_window(data, off - 96, off)
        steps.append(
            {
                "offset": off,
                "step_id": step_id,
                "operation_id": op_id,
                "name": text,
                "candidate_values": params,
            }
        )
    return {
        "size": len(data),
        "steps": steps,
    }


def parse_prg_temperature_palette(prg_data: Dict[str, Any]) -> List[float]:
    palette = set(DEFAULT_PALETTE)
    for step in prg_data.get("steps", []):
        for v in step.get("candidate_values", []):
            if 20.0 <= v <= 140.0:
                palette.add(float(v))
    return sorted(palette)


def guess_lot_from_strings(strings: List[Dict[str, Any]]) -> Optional[str]:
    counts = Counter()
    for item in strings:
        for m in re.finditer(r"\b\d{6}\b", item["text"]):
            counts[m.group(0)] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def parse_log_header(data: bytes) -> Dict[str, Any]:
    strings = extract_ascii_runs(data, 4)
    lot = guess_lot_from_strings(strings)
    machine = next((s["text"] for s in strings if re.fullmatch(r"[A-Z]{2}\d{2}", s["text"])), None)
    reference = None
    refs = [re.search(r"\b\d{7,8}\b", s["text"]) for s in strings[:30]]
    for m in refs:
        if m:
            reference = m.group(0)
            break
    return {
        "lot": lot,
        "machine": machine,
        "reference": reference,
        "top_strings": strings[:12],
    }


def is_ts6(buf: bytes, i: int) -> bool:
    if i + 6 > len(buf):
        return False
    y, m, d, hh, mm, ss = buf[i : i + 6]
    return 2000 <= 1900 + y <= 2090 and 1 <= m <= 12 and 1 <= d <= 31 and hh <= 23 and mm <= 59 and ss <= 59


def parse_log_temperature_family(data: bytes) -> List[Dict[str, Any]]:
    grouped: Dict[tuple[int, int], List[Dict[str, Any]]] = {}

    for i in range(4, len(data) - 14):
        if not is_ts6(data, i):
            continue

        pre0 = int.from_bytes(data[i - 4 : i - 2], "little")
        pre1 = int.from_bytes(data[i - 2 : i], "little")
        v1 = int.from_bytes(data[i + 6 : i + 8], "little")
        v2 = int.from_bytes(data[i + 8 : i + 10], "little")
        v3 = int.from_bytes(data[i + 10 : i + 12], "little")
        v4 = int.from_bytes(data[i + 12 : i + 14], "little")

        y, m, d, hh, mm, ss = data[i : i + 6]
        ts = datetime(1900 + y, m, d, hh, mm, ss)
        row = {
            "timestamp": ts,
            "actual_raw": v1,
            "setpoint_raw": v2,
            "step": v4,
            "counter": pre0,
            "marker_pre1": pre1,
            "marker_v3": v3,
            "offset": i,
        }
        grouped.setdefault((pre1, v3), []).append(row)

    def family_score(rows: List[Dict[str, Any]]) -> tuple[int, int, int]:
        if len(rows) < 80:
            return (0, 0, 0)
        setpoints = [int(r["setpoint_raw"]) for r in rows]
        actuals = [int(r["actual_raw"]) for r in rows]
        if not setpoints or not actuals:
            return (0, 0, 0)
        med_sp = statistics.median(setpoints)
        med_ac = statistics.median(actuals)
        if not (200 <= med_sp <= 9000 and 200 <= med_ac <= 9000):
            return (0, 0, 0)
        repeats = Counter(setpoints).most_common(1)[0][1]
        if repeats < 20:
            return (0, 0, 0)
        return (repeats, len(rows), -len(set(setpoints)))

    best_rows: List[Dict[str, Any]] = []
    best_score = (0, 0, 0)
    for key, rows in grouped.items():
        score = family_score(rows)
        if score > best_score:
            best_score = score
            best_rows = rows

    if not best_rows and (3, 200) in grouped:
        best_rows = grouped[(3, 200)]

    samples = best_rows

    samples.sort(key=lambda s: (s["timestamp"], s["offset"]))

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for s in samples:
        key = (s["timestamp"], s["actual_raw"], s["setpoint_raw"], s["step"], s["counter"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)
    return deduped


def infer_raw_divisor(samples: List[Dict[str, Any]]) -> float:
    if not samples:
        return 100.0
    med_sp = statistics.median(s["setpoint_raw"] for s in samples)
    return 100.0 if med_sp >= 1500 else 10.0


def infer_scale(samples: List[Dict[str, Any]], palette: List[float], raw_divisor: float = 100.0) -> float:
    repeated = Counter(round(s["setpoint_raw"] / raw_divisor, 2) for s in samples if s["setpoint_raw"] > 0)
    encoded = sorted(v for v, c in repeated.items() if c >= 20)
    if not encoded:
        return 1.0

    ratios: List[float] = []
    for e in encoded:
        for p in palette:
            if e > 0:
                ratios.append(p / e)
    candidates = sorted({round(r, 4) for r in ratios if 0.5 <= r <= 3.0})
    if not candidates:
        return 1.0

    def score(scale: float) -> float:
        total = 0.0
        for e in encoded:
            mapped = e * scale
            total += min(abs(mapped - p) for p in palette)
        return total

    return float(min(candidates, key=score))


def add_scaled_temperatures(samples: List[Dict[str, Any]], scale: float, raw_divisor: float = 100.0) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in samples:
        row = dict(s)
        row["timestamp"] = s["timestamp"].isoformat(sep=" ")
        row["actual_base"] = round(s["actual_raw"] / raw_divisor, 4)
        row["setpoint_base"] = round(s["setpoint_raw"] / raw_divisor, 4)
        row["actual_c"] = round((s["actual_raw"] / raw_divisor) * scale, 4)
        row["setpoint_c"] = round((s["setpoint_raw"] / raw_divisor) * scale, 4)
        out.append(row)
    return out


def smooth(values: List[float], window: int = 7) -> List[float]:
    if window <= 1 or len(values) < 3:
        return values[:]
    half = window // 2
    out = []
    for i in range(len(values)):
        a = max(0, i - half)
        b = min(len(values), i + half + 1)
        out.append(statistics.mean(values[a:b]))
    return out


def compress_setpoint(samples: List[Dict[str, Any]], min_seconds: int = 90) -> List[Dict[str, Any]]:
    if not samples:
        return []
    xs = [datetime.fromisoformat(s["timestamp"]) for s in samples]
    ys = [float(s["setpoint_c"]) for s in samples]
    out = [{"timestamp": samples[0]["timestamp"], "setpoint_c": round(ys[0], 3)}]
    last_ts = xs[0]
    last_sp = ys[0]
    for ts, sp in zip(xs[1:], ys[1:]):
        if abs(sp - last_sp) > 0.05 and (ts - last_ts).total_seconds() >= min_seconds:
            out.append({"timestamp": ts.isoformat(sep=" "), "setpoint_c": round(sp, 3)})
            last_ts = ts
            last_sp = sp
    return out


def plot_temperature_to_buffer(payload: Dict[str, Any], ymax: Optional[float] = None) -> bytes:
    samples = payload["temperature_samples"]
    if not samples:
        raise RuntimeError("No hay muestras de temperatura para graficar")

    xs = [datetime.fromisoformat(s["timestamp"]) for s in samples]
    actual = [float(s["actual_c"]) for s in samples]
    setpoint = [float(s["setpoint_c"]) for s in samples]
    actual_sm = smooth(actual, window=7)

    fig, ax = plt.subplots(figsize=(16, 7), constrained_layout=True)
    ax.step(xs, setpoint, where="post", linewidth=2.3, label="Temperatura programada")
    ax.plot(xs, actual_sm, linewidth=1.4, label="Temperatura real")
    ax.plot(xs, actual, linewidth=0.6, alpha=0.25, label="Temperatura real cruda")

    meta = payload["metadata"]
    ax.set_title(
        f"Orgatex | Lote {meta.get('lot') or '-'} | Ref {meta.get('reference') or '-'} | Máquina {meta.get('machine') or '-'}"
    )
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Temperatura (°C)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")

    if ymax is not None:
        ax.set_ylim(0, ymax)
    else:
        maxv = max(max(actual, default=0), max(setpoint, default=0))
        ax.set_ylim(0, max(90, round(maxv + 10)))

    locator = mdates.AutoDateLocator(minticks=6, maxticks=12)
    formatter = mdates.DateFormatter("%H:%M")
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)

    txt = (
        f"Muestras: {meta.get('sample_count', 0)}\n"
        f"Escala: {meta.get('inferred_scale')}\n"
        f"Rango: {meta.get('start_time')} -> {meta.get('end_time')}"
    )
    ax.text(
        0.01, 0.99, txt,
        transform=ax.transAxes,
        va="top", ha="left",
        fontsize=9,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
    )

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=180)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def build_payload(prg_data: bytes, log_data: bytes, force_scale: Optional[float] = None) -> Dict[str, Any]:
    prg = parse_prg(prg_data)
    log_header = parse_log_header(log_data)
    raw_samples = parse_log_temperature_family(log_data)
    if not raw_samples:
        raise RuntimeError(
            "No se encontró la familia de temperatura en el LOG. "
            "Este script está ajustado al patrón observado en PR132295.LOG."
        )

    palette = parse_prg_temperature_palette(prg)
    for needed in DEFAULT_PALETTE:
        if needed not in palette:
            palette.append(needed)
    palette = sorted(set(palette))

    raw_divisor = infer_raw_divisor(raw_samples)
    scale = float(force_scale) if force_scale else infer_scale(raw_samples, palette, raw_divisor=raw_divisor)
    temp_samples = add_scaled_temperatures(raw_samples, scale, raw_divisor=raw_divisor)

    payload = {
        "metadata": {
            "lot": log_header.get("lot"),
            "machine": log_header.get("machine"),
            "reference": log_header.get("reference"),
            "inferred_scale": round(scale, 6),
            "raw_divisor": raw_divisor,
            "temperature_family_signature": {
                "pre1": temp_samples[0]["marker_pre1"] if temp_samples else None,
                "v3": temp_samples[0]["marker_v3"] if temp_samples else None,
            },
            "prg_palette": palette,
            "sample_count": len(temp_samples),
            "start_time": temp_samples[0]["timestamp"] if temp_samples else None,
            "end_time": temp_samples[-1]["timestamp"] if temp_samples else None,
        },
        "prg": prg,
        "log_header": log_header,
        "temperature_samples": temp_samples,
        "setpoint_changes": compress_setpoint(temp_samples),
    }
    return payload

def generate_diagram_from_files(prg_data: bytes, log_data: bytes) -> bytes:
    payload = build_payload(prg_data, log_data)
    return plot_temperature_to_buffer(payload)
