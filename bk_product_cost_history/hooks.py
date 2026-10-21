import logging

from psycopg2.extras import execute_values

from odoo import SUPERUSER_ID, api
from odoo.tools import column_exists

_logger = logging.getLogger(__name__)

ORIGIN = 'bk_product_cost_history: post_init_hook'

# The cost recorded on the posted sales invoice lines, kept only where it changed for
# the variant and company. The first known cost of a variant has no previous cost.
HISTORY_QUERY = """
    INSERT INTO bk_product_cost_history
        (create_uid, create_date, write_uid, write_date, date, product_id, product_tmpl_id, company_id,
         old_cost, new_cost, source, reference, user_id, technical_origin)
    SELECT %(uid)s, NOW() AT TIME ZONE 'UTC', %(uid)s, NOW() AT TIME ZONE 'UTC', x.line_date, x.product_id,
           pp.product_tmpl_id, x.company_id, COALESCE(x.previous_cost, x.cost), x.cost, 'invoice_history',
           x.invoice, x.line_user, %(origin)s
    FROM (
        SELECT aml.product_id, am.company_id, aml.product_cost AS cost, aml.create_date AS line_date,
               am.name AS invoice, aml.create_uid AS line_user,
               LAG(aml.product_cost) OVER (PARTITION BY aml.product_id, am.company_id
                                           ORDER BY aml.create_date, aml.id) AS previous_cost
        FROM account_move_line aml
        JOIN account_move am ON am.id = aml.move_id
        WHERE am.type = 'out_invoice' AND am.state = 'posted' AND aml.product_id IS NOT NULL
          AND NOT aml.exclude_from_invoice_tab AND aml.product_cost > 0
    ) x
    JOIN product_product pp ON pp.id = x.product_id
    WHERE x.previous_cost IS NULL OR ROUND(x.previous_cost::numeric, %(digits)s) <> ROUND(x.cost::numeric, %(digits)s)
"""


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    digits = env['decimal.precision'].precision_get('Product Price')

    # The invoice line cost comes from a customization (a product_cost field): without it,
    # there is no history to take and only the opening cost is recorded.
    if column_exists(cr, 'account_move_line', 'product_cost'):
        cr.execute(HISTORY_QUERY, {'uid': SUPERUSER_ID, 'origin': ORIGIN, 'digits': digits})
        _logger.info('Product cost history: %s lines from the sales invoices', cr.rowcount)
    else:
        _logger.info('Product cost history: no product cost on the invoice lines, history skipped')

    # Last historical cost per (variant, company).
    cr.execute("""
        SELECT DISTINCT ON (product_id, company_id) product_id, company_id, new_cost
        FROM bk_product_cost_history
        ORDER BY product_id, company_id, date DESC, id DESC
    """)
    last_costs = {(product_id, company_id): cost for product_id, company_id, cost in cr.fetchall()}

    # Opening cost: the cost of every variant in every company on the install date, unless
    # it equals the last historical cost (nothing changed).
    products = env['product.product'].with_context(active_test=False).search([])
    rows = []
    for company in env['res.company'].search([]):
        costs = products.with_context(force_company=company.id).read(['standard_price', 'product_tmpl_id'])
        for product in costs:
            cost = product['standard_price'] or 0.0
            last_cost = last_costs.get((product['id'], company.id))
            if last_cost is not None and round(last_cost, digits) == round(cost, digits):
                continue
            rows.append((SUPERUSER_ID, SUPERUSER_ID, product['id'], product['product_tmpl_id'][0], company.id,
                         cost if last_cost is None else last_cost, cost, 'opening', SUPERUSER_ID, ORIGIN))
    execute_values(cr, """
        INSERT INTO bk_product_cost_history
            (create_uid, write_uid, product_id, product_tmpl_id, company_id, old_cost, new_cost, source,
             user_id, technical_origin, create_date, write_date, date)
        VALUES %s
    """, rows, template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW() AT TIME ZONE 'UTC', "
                        "NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')", page_size=1000)
    _logger.info('Product cost history: %s opening lines', len(rows))
