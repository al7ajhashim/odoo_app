import logging

from psycopg2.extras import execute_values

from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)

ORIGIN = 'bk_lot_cost_history: post_init_hook'


def post_init_hook(env):
    """Opening cost: the cost of every lot of a lot valuated product in every company on the
    install date, even without stock (a returned lot then starts from its known cost)."""
    lots = env['stock.lot'].with_context(active_test=False).search([('product_id.lot_valuated', '=', True)])
    templates = {product.id: product.product_tmpl_id.id for product in lots.product_id}
    rows = []
    for company in env['res.company'].search([]):
        for lot in lots.with_company(company).read(['standard_price', 'product_id']):
            cost = lot['standard_price'] or 0.0
            if not cost:
                continue
            product_id = lot['product_id'][0]
            rows.append((SUPERUSER_ID, SUPERUSER_ID, lot['id'], product_id, templates[product_id], company.id,
                         cost, cost, 'opening', SUPERUSER_ID, ORIGIN))
    execute_values(env.cr, """
        INSERT INTO bk_lot_cost_history
            (create_uid, write_uid, lot_id, product_id, product_tmpl_id, company_id, old_cost, new_cost, source,
             user_id, technical_origin, create_date, write_date, date)
        VALUES %s
    """, rows, template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW() AT TIME ZONE 'UTC', "
                        "NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')", page_size=1000)
    _logger.info('Lot cost history: %s opening lines', len(rows))
