"""Extension de extract.mixin: cache de payload + helpers para los
3 modelos concretos (bank statement, invoice, expense).
"""
import base64
import logging
import uuid

from odoo import api, fields, models

from . import gemini_client

_logger = logging.getLogger(__name__)


def _config_param(env, key, default, cast=str):
    val = env['ir.config_parameter'].sudo().get_param(key, default)
    try:
        return cast(val)
    except (TypeError, ValueError):
        return cast(default)


# ----------------------------------------------------------------------
# Prompts por tipo de documento. Gemini con response_mime_type=
# application/json garantiza salida JSON parseable.
# ----------------------------------------------------------------------

PROMPT_BANK_STATEMENT = """Eres un parser experto de extractos bancarios de Peru.
Analiza el documento adjunto y devuelve JSON con esta estructura exacta:

{
  "balance_start": <numero, saldo inicial del periodo>,
  "balance_end": <numero, saldo final del periodo>,
  "currency": "PEN" | "USD" | "EUR",
  "statement_date": "YYYY-MM-DD",
  "transactions": [
    {"date": "YYYY-MM-DD", "amount": <numero firmado>, "description": "<texto>"}
  ]
}

REGLAS:
- amount POSITIVO para abonos/ingresos/depositos.
- amount NEGATIVO para cargos/gastos/debitos/retiros/comisiones.
- NO incluyas filas de SALDO/TOTAL/SUBTOTAL como transacciones.
- NO incluyas "SALDO ANTERIOR/PREVIO/INICIAL" como transaccion (eso es balance_start).
- NO incluyas "SALDO FINAL/CONTABLE AL/ACTUAL" como transaccion (eso es balance_end).
- Fechas DDMMM (ej. 23NOV) o DD/MM se resuelven al anio del periodo del extracto.
- Si un monto esta en columna CARGOS/DEBE/GASTOS -> negativo.
- Si esta en columna ABONOS/HABER/INGRESOS -> positivo.
- Devuelve TODAS las transacciones visibles en TODAS las paginas.
- Si el extracto tiene una pagina explicativa/educativa al final (ej.
  "Te ayudamos a conocer tu Estado de Cuenta"), IGNORA sus transacciones
  de ejemplo — solo cuentan las del extracto real."""


PROMPT_INVOICE = """Eres un parser experto de facturas peruanas (SUNAT) y boletas electronicas.
Analiza el documento adjunto y devuelve JSON con esta estructura:

{
  "invoice_id": "<numero completo, ej F001-00000123 o B003-00045678>",
  "supplier": "<razon social del emisor>",
  "VAT_Number": "<RUC del emisor, 11 digitos>",
  "client": "<razon social del receptor o null>",
  "client_VAT": "<RUC del receptor o null>",
  "date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD o null",
  "currency": "PEN" | "USD",
  "subtotal": <numero, base imponible u Op. Gravada>,
  "total_tax_amount": <numero, IGV / IVA>,
  "total": <numero, importe total>,
  "tax_rate": <numero, ej 18.0 o 0 si exonerado>,
  "lines": [
    {"description": "<texto>", "quantity": <numero>, "unit_price": <numero>, "total": <numero>}
  ]
}

REGLAS:
- Si la boleta es Op. Exonerada/Inafecta: subtotal=monto exonerado, total_tax_amount=0, tax_rate=0.
- invoice_id incluye prefijo letra (F=Factura, B=Boleta, E=Recibo) y guion (ej F001-00012345).
- VAT_Number peruano: 11 digitos, empieza con 10/15/16/17/20.
- Campos no presentes en el documento: usar null (no inventar)."""


PROMPT_EXPENSE = """Eres un parser de recibos / boletas / tickets para rendicion de gastos.
Analiza el documento adjunto y devuelve JSON:

{
  "description": "<comercio o servicio principal>",
  "supplier": "<razon social del emisor o null>",
  "VAT_Number": "<RUC si aparece, 11 digitos, o null>",
  "date": "YYYY-MM-DD",
  "currency": "PEN" | "USD",
  "total": <numero positivo, importe total a pagar>,
  "tax_rate": <numero, ej 18.0 o 0 si exonerado>
}

REGLAS:
- total siempre positivo.
- Si no hay RUC, VAT_Number=null."""


# ----------------------------------------------------------------------
# Conversion JSON Gemini -> formato IAP (selected_value / candidates).
# ----------------------------------------------------------------------

def _as_field(value, coords=None):
    if value is None or value == '':
        return {}
    sv = {'content': value}
    if coords is not None:
        sv['coords'] = coords
    return {'selected_value': sv, 'candidates': [{'content': value}]}


def gemini_bank_statement_to_iap(data):
    """Convierte el JSON del LLM al formato que extract.mixin espera
    para account.bank.statement.
    """
    if not data:
        return {}
    lines = []
    for tx in data.get('transactions') or []:
        amt = tx.get('amount')
        if amt is None:
            continue
        try:
            amt = float(amt)
        except (TypeError, ValueError):
            continue
        lines.append({
            'amount': amt,
            'date': tx.get('date'),
            'description': (tx.get('description') or 'OCR')[:120],
        })
    return {
        'balance_start': _as_field(data.get('balance_start') or 0.0),
        'balance_end': _as_field(data.get('balance_end') or 0.0),
        'date': _as_field(data.get('statement_date')),
        'bank_statement_lines': lines,
    }


def gemini_invoice_to_iap(data):
    if not data:
        return {}
    inv_lines = []
    rate = data.get('tax_rate') or 0
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        rate = 0.0
    for ln in data.get('lines') or []:
        try:
            qty = float(ln.get('quantity') or 1)
        except (TypeError, ValueError):
            qty = 1.0
        try:
            total = float(ln.get('total') or 0)
        except (TypeError, ValueError):
            total = 0.0
        try:
            unit = float(ln.get('unit_price') or (total / qty if qty else total))
        except (TypeError, ValueError):
            unit = total
        inv_lines.append({
            'description': ln.get('description') or 'OCR line',
            'quantity': qty,
            'unit_price': unit,
            'subtotal': total,
            'total': total * (1 + rate / 100.0) if rate else total,
            'taxes': [rate] if rate else [],
        })
    return {
        'invoice_id': _as_field(data.get('invoice_id')),
        'supplier': _as_field(data.get('supplier')),
        'VAT_Number': _as_field(data.get('VAT_Number')),
        'client': _as_field(data.get('client')),
        'date': _as_field(data.get('date')),
        'due_date': _as_field(data.get('due_date')),
        'currency': _as_field(data.get('currency') or 'PEN'),
        'subtotal': _as_field(data.get('subtotal')),
        'total': _as_field(data.get('total')),
        'total_tax_amount': _as_field(data.get('total_tax_amount')),
        'tax_rate': _as_field(data.get('tax_rate')),
        'payment_ref': _as_field(data.get('invoice_id')),
        'iban': _as_field(None),
        'SWIFT_code': _as_field('{}'),
        'country': _as_field('PE' if data.get('VAT_Number') else None),
        'email': {'candidates': []},
        'website': {'candidates': []},
        'phone': {'candidates': []},
        'invoice_lines': inv_lines,
        'type': 'invoice',
        'product_description': _as_field(
            (inv_lines[0].get('description') if inv_lines else None)
        ),
    }


def gemini_expense_to_iap(data):
    if not data:
        return {}
    return {
        'description': _as_field(data.get('description')),
        'supplier': _as_field(data.get('supplier')),
        'total': _as_field(data.get('total')),
        'date': _as_field(data.get('date')),
        'currency': _as_field(data.get('currency') or 'PEN'),
        'tax_rate': _as_field(data.get('tax_rate')),
        'VAT_Number': _as_field(data.get('VAT_Number')),
    }


# ----------------------------------------------------------------------
# Extension del extract.mixin
# ----------------------------------------------------------------------

class ExtractMixin(models.AbstractModel):
    _inherit = 'extract.mixin'

    idtx_ocr_gemini_payload = fields.Json(copy=False)

    def _idtx_gemini_config(self):
        env = self.env
        return {
            'api_key': _config_param(env, 'idtx_ocr_gemini.api_key', ''),
            'model': _config_param(env, 'idtx_ocr_gemini.model', 'gemini-2.5-flash'),
            'timeout': _config_param(env, 'idtx_ocr_gemini.timeout', '120', int),
        }

    def _idtx_gemini_run(self, params, prompt, post_process):
        """Comun a los 3 modelos.

        params: dict que extract.mixin pasa al _contact_iap_extract.
            Tiene la clave 'documents' (lista de strings base64).
        prompt: prompt del tipo de documento.
        post_process(json_data) -> dict con resultado IAP.
        """
        self.ensure_one()
        cfg = self._idtx_gemini_config()
        if not cfg['api_key'] or cfg['api_key'] == 'PEGAR_TU_API_KEY_AQUI':
            _logger.error(
                "idtx_ocr_gemini: api_key NO configurada. Settings > "
                "Technical > System Parameters > idtx_ocr_gemini.api_key"
            )
            return {'status': 'error_internal'}
        # extract.mixin._upload_to_extract pasa params['documents'] como
        # lista de strings base64. Tomamos el primero (siempre hay 1 —
        # el message_main_attachment_id).
        documents = params.get('documents') or []
        if not documents:
            _logger.warning("idtx_ocr_gemini: params['documents'] vacio: %s", list(params.keys()))
            return {'status': 'error_internal'}
        b64 = documents[0]
        try:
            raw = base64.b64decode(b64)
        except Exception:
            _logger.exception("idtx_ocr_gemini: base64 decode fallo")
            return {'status': 'error_internal'}
        filename = ''
        if self.message_main_attachment_id:
            filename = self.message_main_attachment_id.name or ''
        try:
            response_text = gemini_client.query_document(
                cfg['api_key'], cfg['model'], prompt, raw,
                filename=filename, timeout=cfg['timeout'],
            )
        except Exception as e:
            _logger.exception(
                "idtx_ocr_gemini: query_document fallo en %s id=%s: %s",
                self._name, self.id, e,
            )
            return {'status': 'error_internal'}
        parsed = gemini_client.parse_json_response(response_text)
        if parsed is None:
            _logger.warning(
                "idtx_ocr_gemini: respuesta no parseable. Raw:\n%s",
                response_text[:1000],
            )
            return {'status': 'error_internal'}
        iap_result = post_process(parsed)
        token = str(uuid.uuid4())
        self.idtx_ocr_gemini_payload = {
            'token': token,
            'raw_json': parsed,
            'results': [iap_result],
        }
        _logger.info(
            "idtx_ocr_gemini: extraccion OK %s id=%s",
            self._name, self.id,
        )
        return {'status': 'success', 'document_token': token}

    def _idtx_gemini_get_result(self, params):
        self.ensure_one()
        payload = self.idtx_ocr_gemini_payload or {}
        token = params.get('document_token')
        if token and payload.get('token') != token:
            return {'status': 'not_ready'}
        results = payload.get('results') or []
        if not results:
            return {'status': 'error_internal'}
        return {
            'status': 'success',
            'results': results,
            'full_text_annotation': '',
        }
