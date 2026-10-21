from odoo import models

from .product_cost_history import technical_origin


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        # The negative stock compensation run at the end knows its receipt this way.
        return super(StockMove, self.with_context(bk_cost_done_move_ids=tuple(self.ids)))._action_done(
            cancel_backorder=cancel_backorder)

    def _product_price_update_after_done(self):
        # With the lot valuation, a delivery recomputes the product cost from its layers.
        reference = ', '.join(sorted(set(self.mapped('picking_id.name')))) or False
        return super(StockMove, self.with_context(bk_cost_source='lot_delivery', bk_cost_reference=reference)
                     )._product_price_update_after_done()

    def product_price_update_before_done(self, forced_qty=None):
        """One history line per product and company of the receipt, from the cost before
        the receipt to the cost after it (Odoo writes the cost once per move line)."""
        if self.env.context.get('bk_cost_no_log'):
            return super().product_price_update_before_done(forced_qty=forced_qty)
        moves_by_key = {}
        for move in self:
            key = (move.company_id.id, move.product_id.id)
            moves_by_key[key] = moves_by_key.get(key, self.browse()) | move
        Product = self.env['product.product']
        old_costs = {key: Product.browse(key[1]).with_company(key[0]).standard_price
                     for key in moves_by_key}
        res = super(StockMove, self.with_context(bk_cost_no_log=True)).product_price_update_before_done(
            forced_qty=forced_qty)
        History = self.env['bk.product.cost.history']
        origin = technical_origin()
        values_list = []
        for (company_id, product_id), moves in moves_by_key.items():
            product = Product.browse(product_id).with_company(company_id)
            if not History._cost_changed(old_costs[company_id, product_id], product.standard_price):
                continue
            if forced_qty:
                # Odoo 18 passes (lot, quantity) for a correction of a done quantity.
                source, quantity = 'quantity_correction', forced_qty[1]
            else:
                source = 'customer_return' if any(moves.mapped('origin_returned_move_id')) else 'receipt'
                quantity = sum(line.quantity_product_uom for move in moves for line in move._get_in_move_lines())
            values_list.append({
                'product_id': product_id,
                'company_id': company_id,
                'old_cost': old_costs[company_id, product_id],
                'new_cost': product.standard_price,
                'source': source,
                'reference': ', '.join(sorted(set(moves.mapped('picking_id.name')))) or moves[0].reference,
                'quantity': quantity,
                'technical_origin': origin,
            })
        History._log(values_list)
        return res
