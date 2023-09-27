# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Import Bills and Invoices',
    'version': '16.0.0.1',
    'sequence': 7,
    'category': 'Accounting',
    'summary': 'Import vendor bills and customer invoices from exel file',
    'author': 'Al-haj Hashim',
    'website': 'https://www.linkedin.com/in/alhaj-hashim',
    'depends': ['account', 'analytic'],
    'data': [
            'security/ir.model.access.csv',
            'views/res_config_settings_view.xml',
            'wizard/import_preparation_view.xml'
        ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'images': ['static/description/log.png'],
}

