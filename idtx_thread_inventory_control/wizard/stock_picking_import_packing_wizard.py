# -*- coding: utf-8 -*-
from odoo import models, fields


class StockPickingImportPackingWizard(models.TransientModel):
    _name = 'stock.picking.import.packing.wizard'
    _description = 'Stock Picking Import Packing Wizard'
