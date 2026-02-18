import pyodbc
from odoo import models, fields
from odoo.exceptions import UserError


class IntegrationOrgatex(models.Model):
    _name = "integration.orgatex"
    _description = "Dyelot Header"

    # =============================
    # CABECERA DYELLOT
    # =============================
    dyelot = fields.Char()
    customer = fields.Char()
    article = fields.Char()
    colourNo= fields.Char()
    redye = fields.Integer()
    machine = fields.Char()
    program_creation_type = fields.Integer()
    recipe_no = fields.Integer()
    recipe_state = fields.Integer()
    import_state = fields.Integer()
    liquor_ratio = fields.Float()
    weight = fields.Float()
    procedure_no = fields.Integer()
    parameter7 = fields.Integer()

    # =============================
    # DETALLE (N REGISTROS)
    # =============================
    procedure_ids = fields.One2many(
        "integration.orgatex.procedure",
        "orgatex_id",
        string="Procedures"
    )

    recipe_ids = fields.One2many(
        "integration.orgatex.recipe",
        "orgatex_id",
        string="Recipes"
    )

    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('approved', 'Approved'),
        ('denied', 'Denied'),
    ], default='pending')

    # =============================
    # CONEXION SQL SERVER
    # =============================
    def _get_sql_connection(self):
        return pyodbc.connect(
            "DSN=ORGATEX_DSN;"
            "DATABASE=ORGATEX-INTEG;"
            "UID=orgatex;"
            "PWD=orgatex;"
            "TDS_Version=7.3;"
        )

    # =============================
    # INSERT COMPLETO (1 + N + N)
    # =============================
    def action_insert_all(self):
        self.ensure_one()
        conn = self._get_sql_connection()
        cur = conn.cursor()

        try:
            # -------- CABECERA
            cur.execute("""
                INSERT INTO Dyelots
                (Dyelot, Customer, Article, colourNo, Redye, Machine, ProgramCreationType, RecipeNo,
                 RecipeState, ImportState, LiquorRatio, Weight, ProcedureNo, Parameter7)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.dyelot,
                self.customer,
                self.article,
                self.colourNo,
                self.redye,
                self.machine,
                self.program_creation_type,
                self.recipe_no,
                self.recipe_state,
                self.import_state,
                self.liquor_ratio,
                self.weight,
                self.procedure_no,
                self.parameter7
            ))

            # -------- PROCEDURES (N)
            for p in self.procedure_ids:
                cur.execute("""
                    INSERT INTO Dyelot_Procedure
                    (Dyelot, Redye, TreatmentCnt, TreatmentNo)
                    VALUES (?, ?, ?, ?)
                """, (
                    self.dyelot,
                    p.redye,
                    p.treatment_cnt,
                    p.treatment_no
                ))

            # -------- RECIPES (N)
            for r in self.recipe_ids:
                cur.execute("""
                    INSERT INTO Dyelot_Recipe
                    (
                        Dyelot, CorrectionNumber, Redye, CallOff, Counter,
                        ProductName, ProductShortName, ProductCode,
                        Amount, AmountPerMachine, Unit,
                        KindOfStation, State, SpecificWeight, NoOfStation
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.dyelot,
                    r.correction_number,
                    r.redye,
                    r.call_off,
                    r.counter,
                    r.product_name,
                    r.product_short_name,
                    r.product_code,
                    r.amount,
                    r.amount_per_machine,
                    r.unit,
                    r.kind_of_station,
                    r.state,
                    r.specific_weight,
                    r.no_of_station
                ))

            conn.commit()
            self.state = "approved"

        except Exception as e:
            conn.rollback()
            self.state = "denied"
            raise UserError(e)

        finally:
            cur.close()
            conn.close()
