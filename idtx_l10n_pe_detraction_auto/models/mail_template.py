# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import models

# Marcador del bloque (idempotencia entre upgrades). Si algún día cambia el
# contenido del bloque, subir la versión del marcador para que se reemplace.
DETRACTION_BLOCK_MARK = 'idtx-detraction-block'

# Bloque INLINE (vive dentro del <p> principal del correo, después de
# "Paga lo antes posible." y antes de la referencia de pago). El monto va
# SIN signo (abs) y en soles; el saldo en la moneda de la factura.
DETRACTION_BLOCK = (
    '<t t-if="object.l10n_pe_dt_amount"><br/><br/>'
    '<span class="idtx-detraction-block">'
    'Operación sujeta a detracción (<t t-out="int(object.l10n_pe_dt_percent or 0)"/>%): '
    '<strong t-out="format_amount(abs(object.l10n_pe_dt_amount), object.l10n_pe_dt_currency_id)"/><br/>'
    'Saldo a pagar: '
    '<strong t-out="format_amount(object.l10n_pe_dt_net_to_pay, object.currency_id)"/>'
    '</span></t>'
)

# Punto de inserción: la estructura qweb es idéntica en todas las
# traducciones del cuerpo (solo cambian los textos).
INSERT_ANCHOR = '<t t-if="object.payment_reference">'


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    def _idtx_inject_detraction_block(self):
        """Inserta en el correo estándar de factura el bloque de detracción y
        saldo a pagar (visible solo si la factura tiene detracción), después
        del párrafo principal. Aplica a TODAS las traducciones y es
        idempotente; además limpia las versiones viejas del bloque que se
        anexaban al final del cuerpo."""
        template = self.env.ref(
            'account.email_template_edi_invoice', raise_if_not_found=False)
        if not template:
            return
        langs = set(
            code for code, _name in self.env['res.lang'].get_installed())
        langs.add('en_US')
        for lang in langs:
            tmpl_lang = template.with_context(lang=lang)
            body = str(tmpl_lang.body_html or '')
            # Limpieza de versiones ANTERIORES (div al final del cuerpo,
            # bien o mal escapado): se cortaba desde su inicio hasta el fin.
            changed = False
            for token in ('<div class="%s"' % DETRACTION_BLOCK_MARK,
                          '&lt;div class="%s"' % DETRACTION_BLOCK_MARK):
                idx = body.find(token)
                if idx != -1:
                    body = body[:idx]
                    changed = True
                    break
            if DETRACTION_BLOCK_MARK in body:
                # Versión inline vigente ya presente.
                if changed:
                    tmpl_lang.body_html = Markup(body)
                continue
            if INSERT_ANCHOR in body:
                body = body.replace(
                    INSERT_ANCHOR, DETRACTION_BLOCK + INSERT_ANCHOR, 1)
            else:
                # Cuerpo personalizado sin el ancla: al final como respaldo.
                body = body + '<p>' + DETRACTION_BLOCK + '</p>'
            # Markup: concatenar str plano a un cuerpo Markup lo escaparía.
            tmpl_lang.body_html = Markup(body)
