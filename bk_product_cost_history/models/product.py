from odoo import api, fields, models

from .product_cost_history import VIEW_GROUPS, technical_origin


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    bk_cost_history_ids = fields.One2many('bk.product.cost.history', 'product_tmpl_id', string='Cost History',
                                          groups=VIEW_GROUPS)

    @api.model_create_multi
    def create(self, vals_list):
        # The cost given on a new template is written on its variants afterwards. The new
        # records are returned without that context, so later changes keep their own source.
        templates = super(ProductTemplate, self.with_context(bk_cost_source='creation')).create(vals_list)
        return templates.with_env(self.env)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    bk_cost_history_ids = fields.One2many('bk.product.cost.history', 'product_id', string='Cost History',
                                          groups=VIEW_GROUPS)

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        if not self.env.context.get('bk_cost_no_log'):
            History = self.env['bk.product.cost.history']
            origin = technical_origin()
            History._log([{
                'product_id': product.id,
                'company_id': self.env.company.id,
                'old_cost': product.standard_price,
                'new_cost': product.standard_price,
                'source': 'creation',
                'technical_origin': origin,
            } for product in products if History._cost_changed(0.0, product.standard_price)])
        return products

    def _bk_cost_source(self):
        """Source of a cost write that no known caller labelled: Odoo revalues the stock
        (disable_auto_svl not set) only for a cost changed by a user or an import."""
        context = self.env.context
        if context.get('bk_cost_source'):
            return context['bk_cost_source']
        if not context.get('disable_auto_svl'):
            return 'import' if context.get('import_file') else 'manual'
        return 'other'

    def write(self, vals):
        """Safety net: every change of the cost is logged, whatever changed it. The known
        callers only put the source and the reference in the context."""
        if 'standard_price' not in vals or self.env.context.get('bk_cost_no_log'):
            return super().write(vals)
        # The company dependent cost is read and written in the current company (with_company).
        old_costs = {product.id: product.standard_price for product in self}
        res = super().write(vals)
        History = self.env['bk.product.cost.history']
        source = self._bk_cost_source()
        origin = technical_origin()
        History._log([{
            'product_id': product.id,
            'company_id': self.env.company.id,
            # A new product starts from its first cost, not from zero.
            'old_cost': product.standard_price if source == 'creation' else old_costs[product.id],
            'new_cost': product.standard_price,
            'source': source,
            'reference': self.env.context.get('bk_cost_reference') or False,
            'technical_origin': origin,
        } for product in self if History._cost_changed(old_costs[product.id], product.standard_price)])
        return res

    def _run_fifo_vacuum(self, company=None):
        """Log the cost change of the negative stock compensation with the compensated
        deliveries and the receipt that compensated them (Odoo 18 runs it on several products)."""
        if self.env.context.get('bk_cost_no_log'):
            return super()._run_fifo_vacuum(company=company)
        company = company or self.env.company
        products = self.with_company(company)
        old_costs = {product.id: product.standard_price for product in products}
        Layer = self.env['stock.valuation.layer'].sudo()
        last_layer_id = Layer.search([], order='id desc', limit=1).id or 0
        res = super(ProductProduct, self.with_context(bk_cost_no_log=True))._run_fifo_vacuum(company=company)
        History = self.env['bk.product.cost.history']
        changed = products.filtered(lambda p: History._cost_changed(old_costs[p.id], p.standard_price))
        if not changed:
            return res
        vacuum_layers = Layer.search([('id', '>', last_layer_id), ('product_id', 'in', changed.ids),
                                      ('stock_valuation_layer_id', '!=', False)])
        receipt_moves = self.env['stock.move'].browse(self.env.context.get('bk_cost_done_move_ids', ()))
        origin = technical_origin()
        values_list = []
        for product in changed:
            deliveries = vacuum_layers.filtered(lambda l: l.product_id == product).mapped(
                'stock_valuation_layer_id.stock_move_id.picking_id.name')
            receipts = receipt_moves.filtered(lambda m: m.product_id == product).mapped('picking_id.name')
            reference = ', '.join(sorted(set(deliveries)))
            if receipts:
                reference = '%s ← %s' % (reference, ', '.join(sorted(set(receipts))))
            values_list.append({
                'product_id': product.id,
                'company_id': company.id,
                'old_cost': old_costs[product.id],
                'new_cost': product.standard_price,
                'source': 'negative_stock',
                'reference': reference or False,
                'technical_origin': origin,
            })
        History._log(values_list)
        return res
