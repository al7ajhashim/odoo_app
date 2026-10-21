from odoo import models


class StockValuationLayerRevaluation(models.TransientModel):
    _inherit = 'stock.valuation.layer.revaluation'

    def action_validate_revaluation(self):
        # The reason of the revaluation is the reference of the lot cost change.
        return super(StockValuationLayerRevaluation, self.with_context(
            bk_lot_cost_source='revaluation', bk_lot_cost_reference=self.reason or False,
        )).action_validate_revaluation()
