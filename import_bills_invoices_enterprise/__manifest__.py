# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Import Bills and Invoices Enterprise',
    'version': '16.0.0.1',
    'sequence': 7,
    'category': 'Accounting',
    'summary': 'Import vendor bills and customer invoices [Enterprise]',
    'author': 'Al-haj Hashim',
    'website': 'https://www.linkedin.com/in/alhaj-hashim',
    'depends': ['account', 'import_bills_invoices'],
    'data': [
            'wizard/import_preparation_view.xml'
        ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

