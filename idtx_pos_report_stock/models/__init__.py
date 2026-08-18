# -*- coding: utf-8 -*-
from . import stock_lot                     # debe importarse ANTES de pos_stock_report
from . import stock_scrap_reason_tag        # extensión defensiva para asegurar el tag 'Muestra'
from . import pos_stock_report              # para que la columna exista cuando la vista la referencia
