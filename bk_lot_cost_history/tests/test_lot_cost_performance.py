import logging
import time

from odoo.tests import tagged

from .common import LotCostHistoryCommon

_logger = logging.getLogger(__name__)

SERIALS = 1000


@tagged('post_install', '-at_install', '-standard', 'bk_lot_performance')
class TestLotCostPerformance(LotCostHistoryCommon):
    """Run on demand: --test-tags bk_lot_performance"""

    def _measure(self, prefix, no_log=False):
        lots = [('%s-%04d' % (prefix, index), 1) for index in range(SERIALS)]
        env = self.env
        self.env = env(context=dict(env.context, bk_lot_cost_no_log=no_log))
        self.env.invalidate_all()
        queries, start = self.env.cr.sql_log_count, time.time()
        self._transfer(self.serial_product.with_env(self.env), lots, price=100)
        result = self.env.cr.sql_log_count - queries, time.time() - start
        self.env = env
        return result

    def test_receipt_of_many_serials(self):
        queries_without, time_without = self._measure('OFF', no_log=True)
        queries_with, time_with = self._measure('ON')
        self.assertEqual(self.History.search_count([('product_id', '=', self.serial_product.id)]), SERIALS)
        extra = (queries_with - queries_without) / SERIALS
        _logger.info('Lot cost history: receipt of %s serials: %s queries / %.1fs without the log, '
                     '%s queries / %.1fs with it (%.1f queries per serial)',
                     SERIALS, queries_without, time_without, queries_with, time_with, extra)
        self.assertLessEqual(extra, 6)
