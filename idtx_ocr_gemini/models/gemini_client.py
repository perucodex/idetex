"""Cliente HTTP a Google Gemini API para extraccion de documentos.

Gemini acepta PDFs e imagenes directo via inlineData (hasta 20MB inline)
o via Files API (mayores). Para extractos bancarios PE estandar (~100KB
a 2MB) inline es suficiente.

Endpoint:
    POST https://generativelanguage.googleapis.com/v1beta/models/<MODEL>:generateContent

Free tier (2026):
    - gemini-2.5-flash:      15 req/min, 1500/dia, 1M tokens/dia
    - gemini-2.5-flash-lite:  ~igual, menor calidad
"""
import base64
import json
import logging
import re

import requests

_logger = logging.getLogger(__name__)


GEMINI_API_BASE = 'https://generativelanguage.googleapis.com/v1beta'


def _normalize_pdf_bytes(raw):
    """Strippea cualquier prefijo no-PDF antes del header %PDF.
    Bancos PE como BCP anteponen marcadores propios ($BOP$).
    """
    if not raw:
        return None
    idx = raw[:32].find(b'%PDF')
    if idx < 0:
        return None
    return raw[idx:] if idx > 0 else raw


def _detect_mimetype(raw_bytes, fallback_name=''):
    """Heuristica simple por magic bytes / extension."""
    if not raw_bytes:
        return 'application/octet-stream'
    head = raw_bytes[:16]
    name = (fallback_name or '').lower()
    if head.startswith(b'%PDF') or raw_bytes[:32].find(b'%PDF') >= 0:
        return 'application/pdf'
    if head.startswith(b'\x89PNG'):
        return 'image/png'
    if head[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image/webp'
    if name.endswith('.tiff') or name.endswith('.tif'):
        return 'image/tiff'
    if name.endswith('.bmp'):
        return 'image/bmp'
    if name.endswith('.gif'):
        return 'image/gif'
    # Fallback razonable
    return 'application/octet-stream'


def query_document(api_key, model, prompt, raw_bytes, filename='',
                   timeout=120, response_schema=None):
    """Envia el documento (PDF/imagen) a Gemini y devuelve el texto
    de respuesta.

    Args:
        api_key: clave de Google AI Studio.
        model: ej. 'gemini-2.5-flash'.
        prompt: instrucciones para el modelo.
        raw_bytes: bytes del PDF o imagen (sin base64 — la funcion lo
            encodea).
        filename: opcional, ayuda a detectar mimetype.
        timeout: segundos.
        response_schema: dict opcional con JSON Schema para que Gemini
            valide la salida (response_mime_type=application/json).

    Returns:
        str con la respuesta cruda del modelo (deberia ser JSON).
    """
    if not api_key:
        raise RuntimeError("idtx_ocr_gemini: api_key no configurada")
    if not raw_bytes:
        raise RuntimeError("idtx_ocr_gemini: bytes vacios")
    # Normaliza PDFs con prefijo de banco ($BOP$ etc).
    if raw_bytes[:32].find(b'%PDF') > 0:
        raw_bytes = _normalize_pdf_bytes(raw_bytes) or raw_bytes
    mime = _detect_mimetype(raw_bytes, filename)
    b64 = base64.b64encode(raw_bytes).decode('ascii')
    generation_config = {
        'temperature': 0.0,
        'response_mime_type': 'application/json',
    }
    if response_schema:
        generation_config['response_schema'] = response_schema
    payload = {
        'contents': [{
            'parts': [
                {'text': prompt},
                {'inline_data': {'mime_type': mime, 'data': b64}},
            ],
        }],
        'generationConfig': generation_config,
    }
    url = '%s/models/%s:generateContent' % (GEMINI_API_BASE, model)
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': api_key,
    }
    _logger.info(
        "idtx_ocr_gemini: POST %s mime=%s bytes=%s",
        url, mime, len(raw_bytes),
    )
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError("Gemini no responde (%s)" % e) from e
    if resp.status_code != 200:
        raise RuntimeError(
            "Gemini HTTP %s: %s" % (resp.status_code, resp.text[:500])
        )
    data = resp.json()
    # Estructura de respuesta: candidates[0].content.parts[0].text
    candidates = data.get('candidates') or []
    if not candidates:
        # Posibles razones: prompt blocked, safety filter, etc.
        block = data.get('promptFeedback', {}).get('blockReason')
        if block:
            raise RuntimeError("Gemini bloqueo el prompt: %s" % block)
        raise RuntimeError("Gemini sin candidates en respuesta: %s" % str(data)[:300])
    content = candidates[0].get('content') or {}
    parts = content.get('parts') or []
    if not parts:
        raise RuntimeError("Gemini sin parts en respuesta")
    text = parts[0].get('text', '')
    return text


def parse_json_response(raw_response):
    """El response_mime_type=application/json garantiza que Gemini
    devuelva JSON valido. Igual hacemos un parse defensivo y extraemos
    el primer objeto JSON si viene con texto envoltura.
    """
    raw_response = (raw_response or '').strip()
    if not raw_response:
        return None
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        pass
    m = re.search(r'\{[\s\S]*\}', raw_response)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        _logger.warning(
            "idtx_ocr_gemini: respuesta no parseable como JSON: %s",
            raw_response[:300],
        )
        return None
