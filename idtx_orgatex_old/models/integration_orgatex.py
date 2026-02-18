import pyodbc
from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)

class IntegrationOrgatex(models.Model):
    _name = "integration.orgatex"
    _description = "Integracion de SQL Server con Orgatex"

    product = fields.Char(string='Product')
    color_name = fields.Char(string='Color Name')
    code_color = fields.Char(string='Color Code')
    color = fields.Char(string='Color')
    hexadecimal = fields.Char(string='Hex')
    recipes = fields.Char(string='Recipes')

    state = fields.Selection([
        ('approved', 'Approved'),
        ('denied', 'Denied'),
        ('pending', 'Pendiente'),
    ], string='State', default='pending')

    # -----------------------------------------
    # 🔌 CONEXION SQL SERVER
    # -----------------------------------------
    def _get_sql_connection(self):
        try:
            conn = pyodbc.connect(
                "DRIVER={ODBC Driver 17 for SQL Server};"
                "SERVER=172.16.64.8;"
                "DATABASE=pruebas;"
                "UID=sistemas;"
                "PWD=idtE#21@IRdc95;",
                timeout=5
            )
            return conn
        except Exception as e:
            _logger.error(f"Error conectando a SQL Server: {e}")
            raise api.exceptions.UserError(f"No se pudo conectar a SQL Server: {e}")

    # -----------------------------------------
    # 🚀 ACCIÓN PARA ENVIAR REGISTRO A SQL
    # -----------------------------------------
    def action_send_to_sql(self):
        self.ensure_one()
        conn = self._get_sql_connection()
        
        try:
            cursor = conn.cursor()

            query = """
                INSERT INTO tabla_orgatex
                (product, color_name, code_color, color, hexadecimal, recipes, state)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """

            values = (
                self.product or '',
                self.color_name or '',
                self.code_color or '',
                self.color or '',
                self.hexadecimal or '',
                self.recipes or '',
                self.state or 'pending',
            )

            cursor.execute(query, values)
            conn.commit()
            cursor.close()
            conn.close()

            self.state = "approved"
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Éxito',
                    'message': 'Datos enviados correctamente a Orgatex',
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            _logger.error(f"Error al insertar datos en SQL Server: {e}")
            self.state = "denied"
            raise api.exceptions.UserError(f"Error al enviar datos: {e}")
