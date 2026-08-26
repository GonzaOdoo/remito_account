# -*- coding: utf-8 -*-
{
    'name': "Ajustes Remito y Reportes de Asistencias",

    'summary': """
        Modulo para ajustes de remito.
        """,

    'description': """
    """,

    'author': "GonzaOdoo",
    'website': "http://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['sale','l10n_ar_stock','account','stock'],

    # always loaded
    "data": ["security/ir.model.access.csv",
             "views/report_remito.xml",
             "views/account_move.xml",
             "views/stock_picking_type.xml",
            ],
}
