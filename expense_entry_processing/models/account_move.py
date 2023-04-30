# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        if self.mapped('expense_sheet_id'):
            self.mapped('line_ids').filtered(lambda line: not line.debit and not line.credit).unlink()
        return super(AccountMove, self).action_post()
