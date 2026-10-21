import inspect
import os
from functools import lru_cache

from odoo import api, fields, models
from odoo.tools import float_compare

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORM_FILES = (
    os.path.join('odoo', 'models.py'),
    os.path.join('odoo', 'fields.py'),
    os.path.join('odoo', 'api.py'),
)

VIEW_GROUPS = 'base.group_system,account.group_account_user,' \
              'bk_product_cost_history.group_view_product_cost_history'


@lru_cache(maxsize=None)
def _module_of(directory):
    """Name of the Odoo module that contains the directory (the folder with a manifest)."""
    while directory and directory != os.path.dirname(directory):
        if os.path.isfile(os.path.join(directory, '__manifest__.py')):
            return os.path.basename(directory)
        directory = os.path.dirname(directory)
    return 'odoo'


def technical_origin():
    """'module: model.method' of the code that changed the cost: the first caller
    outside this module and the ORM (frames are walked, the stack is not inspected)."""
    frame = inspect.currentframe().f_back
    while frame:
        path = frame.f_code.co_filename
        if not path.startswith(MODULE_DIR) and not path.endswith(ORM_FILES):
            caller = frame.f_locals.get('self')
            model = getattr(caller, '_name', None)
            method = '%s.%s' % (model, frame.f_code.co_name) if model else frame.f_code.co_name
            return '%s: %s' % (_module_of(os.path.dirname(path)), method)
        frame = frame.f_back
    return False


class ProductCostHistory(models.Model):
    _name = 'bk.product.cost.history'
    _description = 'Product Cost History'
    _order = 'date desc, id desc'
    _rec_name = 'product_id'

    date = fields.Datetime(string='Date', required=True, readonly=True, default=fields.Datetime.now)
    product_id = fields.Many2one('product.product', string='Product Variant', required=True, readonly=True,
                                 index=True, ondelete='cascade')
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id', store=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True)
    old_cost = fields.Float(string='Old Cost', digits='Product Price', readonly=True)
    new_cost = fields.Float(string='New Cost', digits='Product Price', readonly=True)
    source = fields.Selection([
        ('invoice_history', 'Historical from Sales Invoices'),
        ('opening', 'Opening Cost'),
        ('creation', 'Product Creation'),
        ('receipt', 'Receipt'),
        ('customer_return', 'Customer Return'),
        ('quantity_correction', 'Quantity Correction'),
        ('negative_stock', 'Negative Stock Compensation'),
        ('lot_delivery', 'Delivery (Lot Valuation)'),
        ('manual', 'Manual Update'),
        ('import', 'Import'),
        ('other', 'Other'),
    ], string='Source', required=True, readonly=True)
    reference = fields.Char(string='Reference', readonly=True)
    quantity = fields.Float(string='Quantity', digits='Product Unit of Measure', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True)
    technical_origin = fields.Char(string='Technical Origin', readonly=True, groups='base.group_system')

    @api.model
    def _cost_changed(self, old_cost, new_cost):
        digits = self.env['decimal.precision'].precision_get('Product Price')
        return float_compare(old_cost, new_cost, precision_digits=digits) != 0

    @api.model
    def _log(self, values_list):
        """Create the history lines (the model is read-only for everybody)."""
        for values in values_list:
            values.setdefault('user_id', self.env.uid)
        return self.sudo().create(values_list)
