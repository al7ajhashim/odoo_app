from odoo import api, fields, models

from odoo.addons.bk_product_cost_history.models.product_cost_history import VIEW_GROUPS

from .lot_cost_history import technical_origin


class StockLot(models.Model):
    _inherit = 'stock.lot'

    bk_cost_history_ids = fields.One2many('bk.lot.cost.history', 'lot_id', string='Cost History',
                                          groups=VIEW_GROUPS)

    @api.model_create_multi
    def create(self, vals_list):
        # Odoo gives a new lot the cost of its product until its receipt sets the real one:
        # that temporary cost is not logged. The new lots are returned without that context.
        lots = super(StockLot, self.with_context(bk_lot_cost_no_log=True)).create(vals_list)
        return lots.with_env(self.env)

    def _bk_cost_source(self):
        """Source of a cost write that no known caller labelled: Odoo revalues the stock
        (disable_auto_svl not set) only for a cost changed by a user or an import."""
        context = self.env.context
        if context.get('bk_lot_cost_source'):
            return context['bk_lot_cost_source']
        if not context.get('disable_auto_svl'):
            return 'import' if context.get('import_file') else 'manual'
        return 'other'

    def _bk_vacuum_reference(self):
        """Compensated deliveries of the lot and the receipt that compensated them."""
        context = self.env.context
        layers = self.env['stock.valuation.layer'].sudo().search([
            ('id', '>', context.get('bk_lot_cost_vacuum_layer_id', 0)),
            ('lot_id', '=', self.id),
            ('stock_valuation_layer_id', '!=', False),
        ])
        deliveries = layers.mapped('stock_valuation_layer_id.stock_move_id.picking_id.name')
        receipts = self.env['stock.move'].browse(context.get('bk_cost_done_move_ids', ())).filtered(
            lambda move: self in move.move_line_ids.lot_id).mapped('picking_id.name')
        reference = ', '.join(sorted(set(deliveries)))
        if receipts:
            reference = '%s ← %s' % (reference, ', '.join(sorted(set(receipts))))
        return reference or False

    def write(self, vals):
        """Every change of the cost of a lot valuated product is logged, whatever changed it.
        The known callers only put the source and the reference in the context."""
        if 'standard_price' not in vals or self.env.context.get('bk_lot_cost_no_log'):
            return super().write(vals)
        lots = self.filtered(lambda lot: lot.product_id.lot_valuated)
        # The company dependent cost is read and written in the current company (with_company).
        old_costs = {lot.id: lot.standard_price for lot in lots}
        res = super().write(vals)
        if lots:
            lots._bk_log_cost_change(old_costs)
        return res

    def _bk_log_cost_change(self, old_costs):
        History = self.env['bk.lot.cost.history']
        company = self.env.company
        logged_lots = {lot.id for lot, in History.sudo()._read_group(
            [('lot_id', 'in', self.ids), ('company_id', '=', company.id)], ['lot_id'])}
        # Receipts, returns and corrections give their own source, reference and quantity per lot.
        moves = {lot_id: (source, reference, quantity)
                 for lot_id, source, reference, quantity in self.env.context.get('bk_lot_cost_moves', ())}
        source = self._bk_cost_source()
        cost_changed = self.env['bk.product.cost.history']._cost_changed
        origin = technical_origin()
        values_list = []
        for lot in self:
            # The temporary cost given on creation is not a real cost: the first line starts from zero.
            old_cost = old_costs[lot.id] if lot.id in logged_lots else 0.0
            if not cost_changed(old_cost, lot.standard_price):
                continue
            lot_source, reference, quantity = moves.get(lot.id) or (
                source, self.env.context.get('bk_lot_cost_reference') or False, 0.0)
            if lot_source == 'negative_stock':
                reference = lot._bk_vacuum_reference()
            values_list.append({
                'lot_id': lot.id,
                'company_id': company.id,
                'old_cost': old_cost,
                'new_cost': lot.standard_price,
                'source': lot_source,
                'reference': reference,
                'quantity': quantity,
                'technical_origin': origin,
            })
        History._log(values_list)
