# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)

# Conexión por defecto a la BD MySQL del comedor. Se puede sobreescribir con
# parámetros del sistema (Ajustes técnicos ▸ Parámetros del sistema):
#   l10n_pe_comedor.host / .user / .password / .database / .port
_COMEDOR_DB = {
    'host': '172.16.64.13',
    'user': 'comedor',
    'password': 'Xy5e49@2y7x',
    'database': 'johnadm7_comedor',
    'port': 3306,
}


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _pe_comedor_conn_params(self):
        icp = self.env['ir.config_parameter'].sudo()
        return {
            'host': icp.get_param('l10n_pe_comedor.host', _COMEDOR_DB['host']),
            'user': icp.get_param('l10n_pe_comedor.user', _COMEDOR_DB['user']),
            'password': icp.get_param('l10n_pe_comedor.password', _COMEDOR_DB['password']),
            'database': icp.get_param('l10n_pe_comedor.database', _COMEDOR_DB['database']),
            'port': int(icp.get_param('l10n_pe_comedor.port', _COMEDOR_DB['port'])),
        }

    def _pe_comedor_descuento(self):
        """Descuento de comedor del recibo: suma de 'precio' de los consumos NO
        pagados (item 2,3,20) de la ventana de corte, menos el subsidio de la
        empresa por cada registro de item 2 o 3. Consulta la BD MySQL del comedor
        por el DNI del trabajador. Devuelve 0 si no hay DNI/datos o si falla la
        conexión (no rompe el cálculo de la planilla)."""
        self.ensure_one()
        dni = (self.employee_id.identification_id or '').strip()
        if not dni or not self.date_to:
            return 0.0
        try:
            import mysql.connector
        except ImportError:
            _logger.warning("Comedor: falta 'mysql-connector-python'; descuento = 0.")
            return 0.0

        subsidio = self._rule_parameter('l10n_pe_comedor_subsidio') or 0.0

        # Las fechas vienen del registro de Corte de Comedor cuyo fin cae dentro
        # del período del recibo. Si no hay corte, NO se calcula el descuento.
        corte = self.env['l10n.pe.comedor.corte']._corte_for_payslip(self)
        if not corte:
            return 0.0
        start, end = corte.date_from, corte.date_to

        rows = []
        conn = None
        try:
            conn = mysql.connector.connect(connection_timeout=10, **self._pe_comedor_conn_params())
            cur = conn.cursor()
            cur.execute(
                "SELECT item, precio FROM estado_diario "
                "WHERE codigo = %s AND fecha >= %s AND fecha <= %s "
                "AND item IN (2, 3, 20) AND pago = 0",
                (dni, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')))
            rows = cur.fetchall()
            cur.close()
        except Exception as e:  # noqa: BLE001
            _logger.warning("Comedor: error consultando MySQL para DNI %s: %s", dni, e)
            return 0.0
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

        total = 0.0
        subsid_count = 0
        for item, precio in rows:
            total += float(precio or 0.0)
            if int(item) in (2, 3):
                subsid_count += 1
        descuento = total - (subsidio * subsid_count)
        return max(descuento, 0.0)

    def _pe_apply_comedor_input(self):
        """Coloca el descuento de comedor en el input DSCT_COMEDOR del recibo
        (solo si la estructura usa ese input)."""
        self.ensure_one()
        itype = self.env.ref('idtx_hr_payroll_pe.input_type_dsct_comedor', raise_if_not_found=False)
        # Solo si la estructura usa la regla "Descuento Comedor" (COMEDOR_PE).
        if not itype or not self.struct_id.rule_ids.filtered(lambda r: r.code == 'COMEDOR_PE'):
            return
        amount = self._pe_comedor_descuento()
        line = self.input_line_ids.filtered(lambda l: l.input_type_id == itype)[:1]
        if line:
            line.amount = amount
        elif amount:
            self.input_line_ids = [(0, 0, {'input_type_id': itype.id, 'amount': amount})]

    def compute_sheet(self):
        for slip in self:
            try:
                slip._pe_apply_comedor_input()
            except Exception as e:  # noqa: BLE001
                _logger.exception("Comedor: no se pudo aplicar el descuento: %s", e)
        return super().compute_sheet()
