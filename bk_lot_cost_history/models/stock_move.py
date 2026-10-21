from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def product_price_update_before_done(self, forced_qty=None):
        """Give the lot cost log the source, the reference and the quantity of every lot
        of the receipt (Odoo writes the cost of each lot once)."""
        lots_data = {}
        for move in self:
            if not move.product_id.lot_valuated or not move._is_in():
                continue
            if forced_qty:
                # Odoo 18 passes (lot, quantity) for a correction of a done quantity.
                source, quantities = 'quantity_correction', [forced_qty]
            else:
                source = 'customer_return' if move.origin_returned_move_id else 'receipt'
                quantities = [(line.lot_id, line.quantity_product_uom) for line in move._get_in_move_lines()]
            reference = move.picking_id.name or move.reference
            for lot, quantity in quantities:
                if not lot:
                    continue
                dummy, references, total = lots_data.get(lot.id, (source, set(), 0.0))
                lots_data[lot.id] = (source, references | {reference}, total + quantity)
        if not lots_data:
            return super().product_price_update_before_done(forced_qty=forced_qty)
        moves = self.with_context(bk_lot_cost_moves=tuple(
            (lot_id, source, ', '.join(sorted(references)), quantity)
            for lot_id, (source, references, quantity) in lots_data.items()))
        if forced_qty:
            # The corrected lot is written by Odoo itself: it must carry the context.
            forced_qty = (forced_qty[0].with_env(moves.env), forced_qty[1])
        return super(StockMove, moves).product_price_update_before_done(forced_qty=forced_qty)
