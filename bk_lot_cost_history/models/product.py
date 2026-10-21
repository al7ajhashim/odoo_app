from odoo import fields, models

from odoo.addons.bk_product_cost_history.models.product_cost_history import VIEW_GROUPS


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    bk_lot_cost_history_count = fields.Integer(compute='_compute_bk_lot_cost_history_count',
                                               groups=VIEW_GROUPS)

    def _compute_bk_lot_cost_history_count(self):
        counts = dict(self.env['bk.lot.cost.history']._read_group(
            [('product_tmpl_id', 'in', self.ids)], ['product_tmpl_id'], ['__count']))
        for template in self:
            template.bk_lot_cost_history_count = counts.get(template, 0)

    def action_view_bk_lot_cost_history(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('bk_lot_cost_history.action_lot_cost_history')
        action['domain'] = [('product_tmpl_id', '=', self.id)]
        return action


class ProductProduct(models.Model):
    _inherit = 'product.product'

    bk_lot_cost_history_count = fields.Integer(compute='_compute_bk_lot_cost_history_count',
                                               groups=VIEW_GROUPS)

    def _compute_bk_lot_cost_history_count(self):
        counts = dict(self.env['bk.lot.cost.history']._read_group(
            [('product_id', 'in', self.ids)], ['product_id'], ['__count']))
        for product in self:
            product.bk_lot_cost_history_count = counts.get(product, 0)

    def action_view_bk_lot_cost_history(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('bk_lot_cost_history.action_lot_cost_history')
        action['domain'] = [('product_id', '=', self.id)]
        return action

    def _change_standard_price(self, new_price):
        # The cost of a lot valuated product is written on all its lots.
        return super(ProductProduct, self.with_context(bk_lot_cost_source='product_cost'))._change_standard_price(
            new_price)

    def _update_lots_standard_price(self):
        # A change of the costing method or of the lot valuation gives the lots the product cost.
        return super(ProductProduct, self.with_context(bk_lot_cost_source='valuation_change'))._update_lots_standard_price()

    def _run_fifo_vacuum(self, company=None):
        if not any(self.mapped('lot_valuated')):
            return super()._run_fifo_vacuum(company=company)
        # The lot log finds the compensated deliveries in the layers created after this one.
        last_layer_id = self.env['stock.valuation.layer'].sudo().search([], order='id desc', limit=1).id or 0
        return super(ProductProduct, self.with_context(
            bk_lot_cost_source='negative_stock', bk_lot_cost_vacuum_layer_id=last_layer_id,
        ))._run_fifo_vacuum(company=company)
