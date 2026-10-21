import inspect
import os

from odoo import api, fields, models

from odoo.addons.bk_product_cost_history.models import product_cost_history as product_history

MODULE_DIRS = (
    product_history.MODULE_DIR + os.sep,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep,
)


def technical_origin():
    """'module: model.method' of the code that changed the cost: the first caller outside
    this module, the product cost history module and the ORM (frames are walked)."""
    frame = inspect.currentframe().f_back
    while frame:
        path = frame.f_code.co_filename
        if not path.startswith(MODULE_DIRS) and not path.endswith(product_history.ORM_FILES):
            caller = frame.f_locals.get('self')
            model = getattr(caller, '_name', None)
            method = '%s.%s' % (model, frame.f_code.co_name) if model else frame.f_code.co_name
            return '%s: %s' % (product_history._module_of(os.path.dirname(path)), method)
        frame = frame.f_back
    return False


class LotCostHistory(models.Model):
    _name = 'bk.lot.cost.history'
    _description = 'Lot Cost History'
    _order = 'date desc, id desc'
    _rec_name = 'lot_id'

    date = fields.Datetime(string='Date', required=True, readonly=True, default=fields.Datetime.now)
    lot_id = fields.Many2one('stock.lot', string='Lot/Serial Number', required=True, readonly=True,
                             index=True, ondelete='cascade')
    product_id = fields.Many2one(related='lot_id.product_id', store=True, index=True)
    product_tmpl_id = fields.Many2one(related='lot_id.product_id.product_tmpl_id', store=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True)
    old_cost = fields.Float(string='Old Cost', digits='Product Price', readonly=True)
    new_cost = fields.Float(string='New Cost', digits='Product Price', readonly=True)
    source = fields.Selection([
        ('opening', 'Opening Cost'),
        ('receipt', 'Receipt'),
        ('customer_return', 'Customer Return'),
        ('quantity_correction', 'Quantity Correction'),
        ('negative_stock', 'Negative Stock Compensation'),
        ('manual', 'Manual Update'),
        ('import', 'Import'),
        ('product_cost', 'Product Cost Update'),
        ('revaluation', 'Revaluation'),
        ('valuation_change', 'Valuation Settings Change'),
        ('other', 'Other'),
    ], string='Source', required=True, readonly=True)
    reference = fields.Char(string='Reference', readonly=True)
    quantity = fields.Float(string='Quantity', digits='Product Unit of Measure', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True)
    technical_origin = fields.Char(string='Technical Origin', readonly=True, groups='base.group_system')

    @api.model
    def _log(self, values_list):
        """Create the history lines (the model is read-only for everybody)."""
        for values in values_list:
            values.setdefault('user_id', self.env.uid)
        return self.sudo().create(values_list)
