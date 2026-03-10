import pyodbc
import os
import base64
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ControlPedidoLine(models.Model):
    _inherit = 'control.pedido.line'

    diagram_ids = fields.One2many('diagram.orgatex', 'pedido_line_id', string='Diagramas')

    def action_create_diagram(self):
        self.ensure_one()
        if not self.route:
            raise UserError(_("No hay una ruta definida para esta partida."))

        # 1. Obtener la conexión a Orgatex
        connection_string = self.env['ir.config_parameter'].sudo().get_param('idtx_diagram_orgatex.connection_string')
        if not connection_string:
            connection_string = (
                "DSN=ORGATEX_DSN;"
                "DATABASE=ORGATEX-INTEG;"
                "UID=orgatex;"
                "PWD=orgatex;"
                "TDS_Version=7.3;"
            )

        conn = None
        try:
            conn = pyodbc.connect(connection_string, timeout=5)
            cursor = conn.cursor()

            # 2. Consultar Dyelots
            search_dyelot = f"{self.route or ''}{self.barcodreo or ''}"
            query = "SELECT Dyelot, DyelotRefNo FROM Dyelots WHERE Dyelot = ?"
            _logger.info("Consultando Orgatex Dyelot exacto: %s", search_dyelot)
            cursor.execute(query, (search_dyelot,))
            rows = cursor.fetchall()

            if not rows:
                raise UserError(_("No se encontró el dyelot en Orgatex para: %s") % search_dyelot)

            shared_path = self.env['ir.config_parameter'].sudo().get_param('idtx_diagram_orgatex.shared_path')
            if not shared_path:
                shared_path = '/mnt/sysvol/OT/HISTORY'

            if not os.path.exists(shared_path):
                raise UserError(_("La ruta compartida %s no es accesible.") % shared_path)

            created_count = 0
            from . import diagram_parser

            for row in rows:
                dyelot = row.Dyelot
                ref_no = row.DyelotRefNo
                _logger.info("Procesando Dyelot: %s, DyelotRefNo: %s", dyelot, ref_no)

                ref_str = str(ref_no)
                folder_name = f"HS{ref_str[:3]}xxx"
                target_dir = os.path.join(shared_path, folder_name)

                if not os.path.isdir(target_dir):
                    _logger.warning("No se encontró el directorio: %s", target_dir)
                    continue

                prg_path = None
                log_path = None
                try:
                    prg_path = target_dir + '/BP' + ref_str + '.prg'
                    log_path = target_dir + '/PR' + ref_str + '.log'
                except Exception as e:
                    _logger.warning("Error al leer directorio %s: %s", target_dir, e)
                    continue

                if prg_path and log_path:
                    try:
                        with open(prg_path, 'rb') as f_prg, open(log_path, 'rb') as f_log:
                            prg_data = f_prg.read()
                            log_data = f_log.read()
                            
                        # Generar imagen con el parser
                        img_bytes = diagram_parser.generate_diagram_from_files(prg_data, log_data)
                        
                        existing = self.diagram_ids.filtered(lambda d: d.ref_no == ref_str)
                        vals = {
                            'pedido_line_id': self.id,
                            'dyelot': dyelot,
                            'ref_no': ref_str,
                            'diagram_image': base64.b64encode(img_bytes),
                        }
                        if existing:
                            existing.write(vals)
                        else:
                            self.env['diagram.orgatex'].create(vals)
                        created_count += 1
                        
                    except Exception as parse_err:
                        _logger.error("Error al generar diagrama para ref %s: %s", ref_no, parse_err)
                else:
                    _logger.warning("Faltan archivos PRG o LOG para ref_no: %s en %s (PRG: %s, LOG: %s)", ref_no, target_dir, prg_path, log_path)

            if created_count == 0:
                raise UserError(_("No se encontraron archivos de diagrama validos para los registros de Orgatex."))

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Diagramas Actualizados'),
                    'message': _('Se han actualizado %s diagramas para la ruta %s.') % (created_count, self.route),
                    'type': 'success',
                }
            }

        except pyodbc.Error as e:
            _logger.error("Error de base de datos Orgatex: %s", str(e))
            raise UserError(_("Error al conectar con la base de datos de Orgatex: %s") % str(e))
        except Exception as e:
            _logger.error("Error inesperado en acción de diagrama: %s", str(e))
            raise UserError(_("Error al procesar el diagrama: %s") % str(e))
        finally:
            if conn:
                conn.close()
