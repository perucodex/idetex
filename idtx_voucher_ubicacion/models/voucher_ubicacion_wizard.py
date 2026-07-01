# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, _
from odoo.exceptions import UserError
from odoo.addons.idtx_mrp.models.mrp_routing_workcenter_operation import (
    _texplus_writes_enabled,
)

_logger = logging.getLogger(__name__)


class VoucherUbicacionWizard(models.TransientModel):
    _name = 'voucher.ubicacion.wizard'
    _description = 'Ubicar piezas de un voucher TEXPLUS por talla'

    technical_sheet_id = fields.Many2one(
        'technical.sheet', string='Ficha Técnica', required=True, readonly=True)
    voucher_number = fields.Char(
        'N° Voucher', required=True,
        help="Número completo de la hoja de ruta, p. ej. 3319242. El último "
             "dígito es el reproceso (BarCodReo); el resto es el BarCod.")

    @staticmethod
    def _fmt_num(value):
        """50.0 -> '50' ; 50.5 -> '50.5'."""
        try:
            f = float(value or 0.0)
        except (TypeError, ValueError):
            return '0'
        return str(int(f)) if f == int(f) else ('%g' % f)

    def action_apply(self):
        self.ensure_one()
        sheet = self.technical_sheet_id
        if sheet.weave_type != 'rect':
            raise UserError(_(
                "Esta acción es solo para productos rectos (weave_type = 'rect')."))

        raw = (self.voucher_number or '').strip()
        if not raw.isdigit() or len(raw) < 2:
            raise UserError(_(
                "El N° de voucher debe ser numérico, p. ej. 3319242."))
        barcod = int(raw[:-1])
        barcodreo = int(raw[-1])

        # Mapa talla -> "largo/ancho" desde la pestaña Tallas (ALRPIELOC es char(10)).
        size_map = {}
        for line in sheet.size_chart_ids:
            key = (line.size or '').strip().upper()
            if not key:
                continue
            size_map[key] = ('%s/%s' % (self._fmt_num(line.length),
                                        self._fmt_num(line.width)))[:10]
        if not size_map:
            raise UserError(_(
                "La ficha técnica no tiene tallas cargadas en la pestaña 'Tallas'."))

        writes_enabled = _texplus_writes_enabled()
        conn = self.env['mrp.routing.workcenter.operation'].sudo()._get_texplus_sql_connection()
        cursor = conn.cursor()
        matched_by_talla = {}
        updated = 0
        no_talla = []
        no_match = set()
        try:
            # Validación: el producto del voucher (BARCAD.BarSer) sin su primer
            # carácter debe coincidir con el product_code de la ficha técnica.
            cursor.execute(
                "SELECT DISTINCT RTRIM(BarSer) FROM BARCAD (NOLOCK) "
                "WHERE BarCod = ? AND BarCodReo = ?", barcod, barcodreo)
            barcad_rows = cursor.fetchall()
            if not barcad_rows:
                raise UserError(_(
                    "El voucher %(v)s no existe en TEXPLUS (BARCAD).") % {'v': raw})
            barser = (barcad_rows[0][0] or '').strip()
            voucher_code = barser[1:].upper()          # sin el primer carácter
            sheet_code = (sheet.product_code or '').strip().upper()
            if voucher_code != sheet_code:
                raise UserError(_(
                    "El producto del voucher NO coincide con el de la ficha técnica; "
                    "no se modificó nada.\n"
                    "• Voucher %(v)s → BarSer=%(b)s → %(vc)s\n"
                    "• Ficha %(s)s → product_code=%(sc)s") % {
                        'v': raw, 'b': barser, 'vc': voucher_code,
                        's': sheet.name, 'sc': sheet_code or '(vacío)'})

            cursor.execute(
                "SELECT EmprCod, AlbRecCod, RTRIM(BarPieCod) "
                "FROM BARPIE (NOLOCK) WHERE BarCod = ? AND BarCodReo = ?",
                barcod, barcodreo)
            pieces = cursor.fetchall()
            if not pieces:
                raise UserError(_(
                    "El voucher %(v)s (BarCod=%(c)s, BarCodReo=%(r)s) no tiene "
                    "piezas en TEXPLUS (BARPIE).") % {
                        'v': raw, 'c': barcod, 'r': barcodreo})
            for emprcod, albreccod, barpiecod in pieces:
                barpiecod = (barpiecod or '').strip()
                talla = (barpiecod.split('-', 1)[0].strip().upper()
                         if '-' in barpiecod else '')
                if not talla:
                    no_talla.append(barpiecod)
                    continue
                value = size_map.get(talla)
                if value is None:
                    no_match.add('%s (talla %s)' % (barpiecod, talla))
                    continue
                matched_by_talla[talla] = matched_by_talla.get(talla, 0) + 1
                cursor.execute(
                    "UPDATE ALBDET SET ALRPIELOC = ? "
                    "WHERE EmprCod = ? AND AlbRecCod = ? AND RTRIM(AlbRecPie) = ?",
                    value, emprcod, albreccod, barpiecod)
                updated += cursor.rowcount or 0
            conn.commit()
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

        matched = sum(matched_by_talla.values())
        detalle = ', '.join(
            '%s→%s (%s pza)' % (t, size_map[t], n)
            for t, n in sorted(matched_by_talla.items())
        ) or _('(ninguna talla coincidió)')
        if not writes_enabled:
            msg = _("MODO LECTURA (texplus_write_enabled=False): NO se escribió "
                    "nada. Coincidieron %(m)s piezas: %(d)s") % {
                        'm': matched, 'd': detalle}
            level = 'warning'
        else:
            msg = _("Actualizadas %(u)s de %(m)s piezas en ALBDET.ALRPIELOC. "
                    "Detalle: %(d)s") % {'u': updated, 'm': matched, 'd': detalle}
            level = 'success' if updated else 'warning'
        extra = []
        if no_match:
            extra.append(_("Piezas cuya talla no está en la ficha: %s")
                         % ', '.join(sorted(no_match)[:20]))
        if no_talla:
            extra.append(_("Piezas sin prefijo de talla: %s")
                         % ', '.join(no_talla[:20]))
        if extra:
            msg = msg + '\n' + '\n'.join(extra)

        _logger.info("voucher.ubicacion %s: matched=%s updated=%s writes=%s",
                     raw, matched, updated, writes_enabled)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Ubicación de piezas TEXPLUS'),
                'message': msg,
                'sticky': True,
                'type': level,
            },
        }
