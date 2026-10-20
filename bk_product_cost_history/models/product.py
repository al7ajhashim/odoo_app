from odoo import api, fields, models

from .product_cost_history import VIEW_GROUPS, technical_origin


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    bk_cost_history_ids = fields.One2many('bk.product.cost.history', 'product_tmpl_id', string='Cost History',
                                          groups=VIEW_GROUPS)

    @api.model_create_multi
    def create(self, vals_list):
        # The cost given on a new template is written on its variants afterwards.
        return super(ProductTemplate, self.with_context(bk_cost_source='creation')).create(vals_list)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    bk_cost_history_ids = fields.One2many('bk.product.cost.history', 'product_id', string='Cost History',
                                          groups=VIEW_GROUPS)

    def _bk_cost_company_id(self):
        # Same company as the one used by Odoo to read and write the company dependent cost.
        return self.env.context.get('force_company') or self.env.company.id

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        if not self.env.context.get('bk_cost_no_log'):
            History = self.env['bk.product.cost.history']
            origin = technical_origin()
            History._log([{
                'product_id': product.id,
                'company_id': products._bk_cost_company_id(),
                'old_cost': product.standard_price,
                'new_cost': product.standard_price,
                'source': 'creation',
                'technical_origin': origin,
            } for product in products if History._cost_changed(0.0, product.standard_price)])
        return products

    def write(self, vals):
        """Safety net: every change of the cost is logged, whatever changed it. The known
        callers only put the source and the reference in the context."""
        if 'standard_price' not in vals or self.env.context.get('bk_cost_no_log'):
            return super().write(vals)
        # On import, stock_account changes the cost through _change_standard_price, which logs it.
        if self.env.context.get('import_file') and not self.env.context.get('import_standard_price'):
            return super().write(vals)
        old_costs = {product.id: product.standard_price for product in self}
        res = super().write(vals)
        History = self.env['bk.product.cost.history']
        source = self.env.context.get('bk_cost_source') or 'other'
        origin = technical_origin()
        History._log([{
            'product_id': product.id,
            'company_id': self._bk_cost_company_id(),
            # A new product starts from its first cost, not from zero.
            'old_cost': product.standard_price if source == 'creation' else old_costs[product.id],
            'new_cost': product.standard_price,
            'source': source,
            'reference': self.env.context.get('bk_cost_reference') or False,
            'technical_origin': origin,
        } for product in self if History._cost_changed(old_costs[product.id], product.standard_price)])
        return res

    def _change_standard_price(self, new_price, counterpart_account_id=False):
        source = 'import' if self.env.context.get('import_file') else 'manual'
        return super(ProductProduct, self.with_context(bk_cost_source=source))._change_standard_price(
            new_price, counterpart_account_id=counterpart_account_id)

    def _run_fifo_vacuum(self, company=None):
        """Log the cost change of the negative stock compensation with the compensated
        deliveries and the receipt that compensated them."""
        if self.env.context.get('bk_cost_no_log'):
            return super()._run_fifo_vacuum(company=company)
        company_id = (company or self.env.company).id
        product = self.with_context(force_company=company_id)
        old_cost = product.standard_price
        Layer = self.env['stock.valuation.layer'].sudo()
        last_layer_id = Layer.search([], order='id desc', limit=1).id or 0
        res = super(ProductProduct, self.with_context(bk_cost_no_log=True))._run_fifo_vacuum(company=company)
        History = self.env['bk.product.cost.history']
        if History._cost_changed(old_cost, product.standard_price):
            vacuum_layers = Layer.search([('id', '>', last_layer_id), ('product_id', '=', self.id),
                                          ('stock_valuation_layer_id', '!=', False)])
            deliveries = vacuum_layers.mapped('stock_valuation_layer_id.stock_move_id.picking_id.name')
            receipt_moves = self.env['stock.move'].browse(self.env.context.get('bk_cost_done_move_ids', ()))
            receipts = receipt_moves.filtered(lambda m: m.product_id == self).mapped('picking_id.name')
            reference = ', '.join(sorted(set(deliveries)))
            if receipts:
                reference = '%s ← %s' % (reference, ', '.join(sorted(set(receipts))))
            History._log([{
                'product_id': self.id,
                'company_id': company_id,
                'old_cost': old_cost,
                'new_cost': product.standard_price,
                'source': 'negative_stock',
                'reference': reference or False,
                'technical_origin': technical_origin(),
            }])
        return res
