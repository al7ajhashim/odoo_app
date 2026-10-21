{
    'name': 'Product Cost History',
    'version': '15.0.1.0.0',
    'summary': 'Log every change of the product cost, per variant and company, with its source.',
    'category': 'Inventory',
    'author': 'Al-Haj Hashim',
    'depends': ['stock_account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/product_cost_history_views.xml',
    ],
    'license': 'LGPL-3',
    'images': ['static/description/logo.png'],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
