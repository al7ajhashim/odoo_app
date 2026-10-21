from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.bk_lot_cost_history.hooks import post_init_hook

from .common import LotCostHistoryCommon


@tagged('post_install', '-at_install')
class TestLotCostHistory(LotCostHistoryCommon):

    def test_01_receipt_first_line_from_zero(self):
        """The cost Odoo copies from the product on a new lot is not logged."""
        self.serial_product.standard_price = 1000
        receipt = self._transfer(self.serial_product, [('SN-1', 1)], price=900)
        self.assertLines(self._lot(self.serial_product, 'SN-1'), [('receipt', 0.0, 900.0, receipt.name, 1.0)])

    def test_02_receipt_at_the_product_cost(self):
        """The first receipt is logged even when its price equals the copied product cost."""
        self.serial_product.standard_price = 900
        receipt = self._transfer(self.serial_product, [('SN-2', 1)], price=900)
        self.assertLines(self._lot(self.serial_product, 'SN-2'), [('receipt', 0.0, 900.0, receipt.name, 1.0)])

    def test_03_average_cost_of_a_lot(self):
        first = self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        second = self._transfer(self.lot_product, [('LOT-A', 10)], price=70)
        self.assertLines(self._lot(self.lot_product, 'LOT-A'), [
            ('receipt', 0.0, 50.0, first.name, 10.0),
            ('receipt', 50.0, 60.0, second.name, 10.0),
        ])

    def test_04_two_lots_in_one_receipt(self):
        first = self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        second = self._transfer(self.lot_product, [('LOT-A', 10), ('LOT-B', 10)], price=70)
        self.assertLines(self._lot(self.lot_product, 'LOT-A'), [
            ('receipt', 0.0, 50.0, first.name, 10.0),
            ('receipt', 50.0, 60.0, second.name, 10.0),
        ])
        self.assertLines(self._lot(self.lot_product, 'LOT-B'), [('receipt', 0.0, 70.0, second.name, 10.0)])

    def test_05_delivery_keeps_the_lot_cost(self):
        self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        self._transfer(self.lot_product, [('LOT-A', 10)], price=70)
        self._transfer(self.lot_product, [('LOT-A', 5)], out=True)
        self.assertEqual(len(self._lines(self._lot(self.lot_product, 'LOT-A'))), 2)

    def test_06_customer_return(self):
        first = self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        delivery = self._transfer(self.lot_product, [('LOT-A', 5)], out=True)
        second = self._transfer(self.lot_product, [('LOT-A', 5)], price=70)
        back = self._transfer(self.lot_product, [('LOT-A', 1)], returned_move=delivery.move_ids)
        # The return comes back at its delivery cost: (10 x 60 + 1 x 50) / 11
        self.assertLines(self._lot(self.lot_product, 'LOT-A'), [
            ('receipt', 0.0, 50.0, first.name, 10.0),
            ('receipt', 50.0, 60.0, second.name, 5.0),
            ('customer_return', 60.0, 59.09, back.name, 1.0),
        ])

    def test_07_quantity_correction(self):
        first = self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        second = self._transfer(self.lot_product, [('LOT-A', 10)], price=100)
        second.move_ids.move_line_ids.quantity = 20
        # (20 x 75 + 10 x 100) / 30
        self.assertLines(self._lot(self.lot_product, 'LOT-A'), [
            ('receipt', 0.0, 50.0, first.name, 10.0),
            ('receipt', 50.0, 75.0, second.name, 10.0),
            ('quantity_correction', 75.0, 83.33, second.name, 10.0),
        ])

    def test_08_manual_and_import(self):
        first = self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        lot = self._lot(self.lot_product, 'LOT-A')
        lot.standard_price = 45
        lot.with_context(import_file=True).standard_price = 44
        lot.standard_price = 44
        self.assertLines(lot, [
            ('receipt', 0.0, 50.0, first.name, 10.0),
            ('manual', 50.0, 45.0, False, 0.0),
            ('import', 45.0, 44.0, False, 0.0),
        ])

    def test_09_product_cost_written_on_its_lots(self):
        first = self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        second = self._transfer(self.lot_product, [('LOT-B', 10)], price=70)
        empty_lot = self.env['stock.lot'].create({'name': 'LOT-C', 'product_id': self.lot_product.id})
        self.lot_product.standard_price = 66
        self.assertLines(self._lot(self.lot_product, 'LOT-A'), [
            ('receipt', 0.0, 50.0, first.name, 10.0),
            ('product_cost', 50.0, 66.0, False, 0.0),
        ])
        self.assertLines(self._lot(self.lot_product, 'LOT-B'), [
            ('receipt', 0.0, 70.0, second.name, 10.0),
            ('product_cost', 70.0, 66.0, False, 0.0),
        ])
        self.assertLines(empty_lot, [('product_cost', 0.0, 66.0, False, 0.0)])

    def test_10_negative_stock_compensation(self):
        delivery = self._transfer(self.lot_product, [('LOT-N', 5)], out=True)
        receipt = self._transfer(self.lot_product, [('LOT-N', 10)], price=80)
        # The receipt first values the lot with the delivered units at zero: (-5 x 0 + 10 x 80) / 5,
        # then the compensation values them at 80.
        self.assertLines(self._lot(self.lot_product, 'LOT-N'), [
            ('receipt', 0.0, 160.0, receipt.name, 10.0),
            ('negative_stock', 160.0, 80.0, '%s ← %s' % (delivery.name, receipt.name), 0.0),
        ])

    def test_11_product_without_lot_valuation(self):
        product = self._create_product('Plain Serial', 'serial', lot_valuated=False)
        self._transfer(product, [('PS-1', 1)], price=500)
        lot = self._lot(product, 'PS-1')
        lot.standard_price = 450
        self.assertFalse(self._lines(lot))

    def test_12_companies_and_access(self):
        first = self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        lot = self._lot(self.lot_product, 'LOT-A')
        company_2 = self.env['res.company'].create({'name': 'BK Lot Cost Test Company'})
        lot.with_company(company_2).standard_price = 30
        self.assertLines(lot, [('receipt', 0.0, 50.0, first.name, 10.0)], company=self.env.company)
        self.assertLines(lot, [('manual', 0.0, 30.0, False, 0.0)], company=company_2)

        viewer = self.env['res.users'].create({
            'name': 'Cost Viewer', 'login': 'bk_cost_viewer',
            'company_id': company_2.id, 'company_ids': [(6, 0, company_2.ids)],
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('bk_product_cost_history.group_view_product_cost_history').id])],
        })
        lines = self.env['bk.lot.cost.history'].with_user(viewer).search([('lot_id', '=', lot.id)])
        self.assertEqual(lines.company_id, company_2)
        with self.assertRaises(AccessError):
            lines.write({'new_cost': 1})
        with self.assertRaises(AccessError):
            lines.unlink()
        with self.assertRaises(AccessError):
            self.env['bk.lot.cost.history'].with_user(viewer).create({
                'lot_id': lot.id, 'company_id': company_2.id, 'source': 'manual'})

        user = self.env['res.users'].create({
            'name': 'Plain User', 'login': 'bk_plain_user',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        with self.assertRaises(AccessError):
            self.env['bk.lot.cost.history'].with_user(user).search([])

    def test_13_opening_cost_on_install(self):
        self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        lot_a = self._lot(self.lot_product, 'LOT-A')
        lot_empty = self.env['stock.lot'].create({'name': 'LOT-E', 'product_id': self.lot_product.id})
        no_cost_product = self._create_product('No Cost', 'lot')
        lot_no_cost = self.env['stock.lot'].create({'name': 'LOT-0', 'product_id': no_cost_product.id})
        plain_product = self._create_product('Plain Lot', 'lot', lot_valuated=False)
        lot_plain = self.env['stock.lot'].create({'name': 'LOT-P', 'product_id': plain_product.id})
        lot_plain.standard_price = 20
        self.History.search([]).unlink()

        post_init_hook(self.env)
        self.History.invalidate_model()
        self.assertLines(lot_a, [('opening', 50.0, 50.0, False, 0.0)])
        self.assertLines(lot_empty, [('opening', 50.0, 50.0, False, 0.0)])
        self.assertFalse(self._lines(lot_no_cost))
        self.assertFalse(self._lines(lot_plain))
        line = self._lines(lot_a)
        self.assertEqual((line.product_id, line.product_tmpl_id, line.company_id),
                         (self.lot_product, self.lot_product.product_tmpl_id, self.env.company))

    def test_14_unit_of_measure(self):
        dozen = self.env.ref('uom.product_uom_dozen')
        # The price of a move is per unit of the product: 2 dozens are 24 units at 10.
        receipt = self._transfer(self.lot_product, [('LOT-D', 2)], price=10, uom=dozen)
        self.assertLines(self._lot(self.lot_product, 'LOT-D'), [('receipt', 0.0, 10.0, receipt.name, 24.0)])

    def test_15_new_lot_keeps_logging(self):
        """The context that skips the creation does not stay on the new lot."""
        lot = self.env['stock.lot'].create({'name': 'LOT-M', 'product_id': self.lot_product.id})
        lot.standard_price = 55
        self.assertLines(lot, [('manual', 0.0, 55.0, False, 0.0)])

    def test_16_product_history_still_logged(self):
        receipt = self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        product_lines = self.env['bk.product.cost.history'].sudo().search(
            [('product_id', '=', self.lot_product.id), ('source', '=', 'receipt')])
        self.assertEqual(product_lines.mapped('reference'), [receipt.name])

    def test_17_technical_origin(self):
        self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        line = self._lines(self._lot(self.lot_product, 'LOT-A'))
        self.assertEqual(line.technical_origin, 'stock_account: stock.move.product_price_update_before_done')

    def _revalue(self, added_value, reason, lot=None):
        wizard = self.env['stock.valuation.layer.revaluation'].with_context(
            default_product_id=self.lot_product.id, default_lot_id=lot and lot.id).create({
                'product_id': self.lot_product.id,
                'lot_id': lot and lot.id,
                'added_value': added_value,
                'reason': reason,
            })
        wizard.action_validate_revaluation()

    def test_18_revaluation(self):
        first = self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        second = self._transfer(self.lot_product, [('LOT-B', 10)], price=70)
        lot_a, lot_b = self._lot(self.lot_product, 'LOT-A'), self._lot(self.lot_product, 'LOT-B')
        # One lot: 100 on its 10 units. Then the product: 200 on its 20 units, shared by its lots.
        self._revalue(100, 'Market price', lot=lot_a)
        self._revalue(200, 'Year end')
        self.assertLines(lot_a, [
            ('receipt', 0.0, 50.0, first.name, 10.0),
            ('revaluation', 50.0, 60.0, 'Market price', 0.0),
            ('revaluation', 60.0, 70.0, 'Year end', 0.0),
        ])
        self.assertLines(lot_b, [
            ('receipt', 0.0, 70.0, second.name, 10.0),
            ('revaluation', 70.0, 80.0, 'Year end', 0.0),
        ])

    def test_19_lot_valuation_enabled(self):
        product = self._create_product('Later Lots', 'lot', lot_valuated=False)
        self._transfer(product, [('LOT-V', 10)], price=50)
        lot = self._lot(product, 'LOT-V')
        self.assertFalse(self._lines(lot))
        product.product_tmpl_id.lot_valuated = True
        self.assertLines(lot, [('valuation_change', 0.0, 50.0, False, 0.0)])

    def test_20_costing_method_change_refused(self):
        """Odoo refuses to change the costing method of lots in stock: nothing is logged."""
        self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        lot = self._lot(self.lot_product, 'LOT-A')
        with self.assertRaises(UserError):
            self.categ.property_cost_method = 'fifo'
        self.assertEqual(self._lines(lot).mapped('source'), ['receipt'])

    def test_21_unknown_change(self):
        """A cost written by code that no known caller labelled (e.g. landed costs) is "other"."""
        first = self._transfer(self.lot_product, [('LOT-A', 10)], price=50)
        lot = self._lot(self.lot_product, 'LOT-A')
        lot.with_context(disable_auto_svl=True).standard_price = 58
        self.assertLines(lot, [
            ('receipt', 0.0, 50.0, first.name, 10.0),
            ('other', 50.0, 58.0, False, 0.0),
        ])
