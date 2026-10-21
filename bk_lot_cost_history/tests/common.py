from odoo.tests import TransactionCase


class LotCostHistoryCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.History = cls.env['bk.lot.cost.history'].sudo()
        cls.categ = cls.env['product.category'].create({
            'name': 'AVCO Lots',
            'property_cost_method': 'average',
            'property_valuation': 'manual_periodic',
        })
        cls.serial_product = cls._create_product('Serial Phone', 'serial')
        cls.lot_product = cls._create_product('Lot Cable', 'lot')
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.supplier = cls.env.ref('stock.stock_location_suppliers')
        cls.customer = cls.env.ref('stock.stock_location_customers')

    @classmethod
    def _create_product(cls, name, tracking, lot_valuated=True):
        return cls.env['product.product'].create({
            'name': name,
            'type': 'consu',
            'is_storable': True,
            'tracking': tracking,
            'lot_valuated': lot_valuated,
            'categ_id': cls.categ.id,
        })

    def _lot(self, product, name):
        return self.env['stock.lot'].search([('product_id', '=', product.id), ('name', '=', name)])

    def _transfer(self, product, lots, price=0.0, out=False, uom=None, returned_move=None):
        """Validate a receipt (or a delivery) of the given [(lot name, quantity)]."""
        if out:
            src, dst, picking_type = self.stock, self.customer, self.warehouse.out_type_id
        elif returned_move:
            src, dst, picking_type = self.customer, self.stock, self.warehouse.in_type_id
        else:
            src, dst, picking_type = self.supplier, self.stock, self.warehouse.in_type_id
        uom = uom or product.uom_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': src.id,
            'location_dest_id': dst.id,
            'move_ids': [(0, 0, {
                'name': product.name,
                'product_id': product.id,
                'product_uom': uom.id,
                'product_uom_qty': sum(quantity for dummy, quantity in lots),
                'price_unit': price,
                'location_id': src.id,
                'location_dest_id': dst.id,
                'origin_returned_move_id': returned_move and returned_move.id,
            })],
        })
        picking.action_confirm()
        move = picking.move_ids
        move.move_line_ids.unlink()
        line_vals = []
        for lot_name, quantity in lots:
            lot = self._lot(product, lot_name)
            if not lot and out:
                lot = self.env['stock.lot'].create({'name': lot_name, 'product_id': product.id})
            vals = {
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': product.id,
                'product_uom_id': uom.id,
                'quantity': quantity,
                'location_id': src.id,
                'location_dest_id': dst.id,
            }
            vals.update({'lot_id': lot.id} if lot else {'lot_name': lot_name})
            line_vals.append(vals)
        self.env['stock.move.line'].create(line_vals)
        move.picked = True
        picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
        self.assertEqual(picking.state, 'done')
        return picking

    def _lines(self, lot, company=None):
        domain = [('lot_id', '=', lot.id)]
        if company:
            domain.append(('company_id', '=', company.id))
        return self.History.search(domain, order='id')

    def assertLines(self, lot, expected, company=None):
        """expected: [(source, old cost, new cost, reference, quantity)]"""
        lines = self._lines(lot, company)
        self.assertEqual(
            [(line.source, round(line.old_cost, 2), round(line.new_cost, 2), line.reference or False,
              round(line.quantity, 2)) for line in lines],
            expected)
        # The log is a chain: each line starts from the cost the previous one ended with,
        # and the last one is the current cost of the lot.
        for previous, line in zip(lines, lines[1:]):
            self.assertAlmostEqual(line.old_cost, previous.new_cost, places=2)
        if lines:
            lot = lot.with_company(lines[-1].company_id)
            self.assertAlmostEqual(lines[-1].new_cost, lot.standard_price, places=2)
