# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

import time
import json
import io
import datetime
import tempfile
import binascii
import xlrd
import itertools
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from datetime import date, datetime
from odoo.exceptions import Warning, ValidationError
from odoo import models, fields, api, _, exceptions
import logging
from operator import itemgetter

_logger = logging.getLogger(__name__)

try:
    import csv
except ImportError:
    _logger.debug('Cannot `import csv`.')
try:
    import base64
except ImportError:
    _logger.debug('Cannot `import base64`.')


class ImportPreparation(models.TransientModel):
    _name = "prepare.import"

    file_to_upload = fields.Binary('File')
    upload_type = fields.Selection([('bill', 'Vendor Bill'), ('invoice', 'Customer Invoice')], string="Upload For", default='bill')
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)

    def _get_account_id(self, account_code):
        if account_code:
            account_ids = self.env['account.account'].search([('code', 'in', account_code.split('.'))])
            if account_ids:
                account_id = account_ids[0]
                return account_id
            else:
                raise ValidationError(_('"%s" Wrong Account Code') % (account_code))

    def _get_analytic_distribution(self, analytic_distribution):
        not_found = []
        count = 0
        analytic_data = {}
        if analytic_distribution:
            for analytic in analytic_distribution:
                count += 1
                analytic_id = self.env['account.analytic.account'].search([('name', '=', analytic)])
                if not analytic_id:
                    not_found.append(str(analytic))
                else:
                    analytic_data.update({analytic_id.id: 100})
            if not_found:
                msg = _("[%s] Wrong analytic name or not found in the system" % ','.join(not_found))
                raise ValidationError(msg)

            return analytic_data

    def _get_taxes(self, taxes):
        tax_ids = []
        if taxes:
            for tax in taxes:
                tax_id = self.env['account.tax'].search([('name', '=', tax)])
                if tax_id:
                    tax_ids.append(tax_id.id)

            return tax_ids
        else:
            return False

    def _get_label(self, name):
        if name:
            return name
        else:
            return '/'

    def _get_partner(self, partner_name):
        partner_ids = self.env['res.partner'].search([('name', '=', partner_name)])
        if partner_ids:
            partner_id = partner_ids[0]
        else:
            partner_id = None
        return partner_id

    def _check_date_format(self, date):
        DATETIME_FORMAT = "%Y-%m-%d"
        if date:
            date = date.split(' ')
            try:
                p_date = datetime.strptime(date[0], DATETIME_FORMAT).date()
                return p_date
            except Exception:
                raise ValidationError(_('Wrong Date Format. Date Should be in format YYYY-MM-DD.0'))
        else:
            raise ValidationError(_('Please add Date field in sheet.'))

    def _check_currency(self, currency):
        currency_ids = self.env['res.currency'].search([('name', '=', currency)])
        if currency_ids:
            currency_id = currency_ids[0]
        else:
            currency_id = None
        return currency_id

    def _get_product_id(self, product):
        product_id = self.env['product.product'].search([('name', '=', product)])
        if not product_id:
            product_id = None
        return product_id

    def _prepare_bill_lines(self, values):
        line_data = {}

        if values.get('name'):
            line_data.update({'name': self._get_label(values.get('name'))})

        if values.get('account_code'):
            account_code = values.get('account_code')
            account_id = self._get_account_id(str(account_code))
            if account_id is not None:
                line_data.update({'account_id': account_id.id})
            else:
                raise ValidationError(_('"%s" Wrong Account Code') % (account_code))

        if values.get('product'):
            product = self._get_product_id(values.get('product'))
            if product is not None:
                line_data.update({'product_id': product.id})
            else:
                line_data.update({'product_id': False})

        if values.get('analytic_distribution'):
            analytics = values.get('analytic_distribution')
            analytics_dist = self._get_analytic_distribution(analytics.split(','))
            if analytics_dist != {}:
                line_data.update({'analytic_distribution': analytics_dist})
            else:
                line_data.update({'analytic_distribution': False})

        if values.get('taxes'):
            taxes = values.get('taxes')
            taxes = self._get_taxes(taxes.split(','))
            if taxes:
                line_data.update({'tax_ids': [(6, 0, taxes)]})
            else:
                line_data.update({'tax_ids': False})

        if values.get('quantity') != '':
            line_data.update({'quantity': float(values.get('quantity'))})
        else:
            line_data.update({'quantity': float('1.0')})

        if values.get('discount') != '':
            line_data.update({'discount': float(values.get('discount'))})
        else:
            line_data.update({'discount': float('0.0')})

        if values.get('price') != '':
            line_data.update({'price_unit': float(values.get('price'))})

        return line_data

    def import_vendor_bill(self):
        try:
            fp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            fp.write(binascii.a2b_base64(self.file_to_upload))
            fp.seek(0)
            workbook = xlrd.open_workbook(fp.name)
            sheet = workbook.sheet_by_index(0)
        except Exception:
            raise exceptions.ValidationError(_('Invalid File!!'))

        data = []
        default_journal = self.env['account.journal'].sudo().search([('type', '=', 'purchase'), ('company_id', '=', self.company_id.id)])
        move_type = 'in_invoice'
        if self.upload_type == 'invoice':
            default_journal = self.env['account.journal'].sudo().search(
                [('type', '=', 'sale'), ('company_id', '=', self.company_id.id)])
            move_type = 'out_invoice'

        for row_no in range(sheet.nrows):
            if row_no <= 0:
                fields = map(lambda row: row.value.encode('utf-8'), sheet.row(row_no))
            else:
                line = list(
                    map(lambda row: isinstance(row.value, bytes) and row.value.encode('utf-8') or str(row.value),
                        sheet.row(row_no)))

                if line[0] != '' or line[1] != '' or line[2] != '' or line[8] != '':
                    if line[0].split('/'):
                        if len(line[0].split('/')) > 1:
                            raise ValidationError(_('Wrong Date Format. Date Should be in format YYYY-MM-DD.1'))
                        if len(line[0]) > 8 or len(line[0]) < 5:
                            raise ValidationError(_('Wrong Date Format. Date Should be in format YYYY-MM-DD.2'))
                    if line[1].split('/'):
                        if len(line[1].split('/')) > 1:
                            raise ValidationError(_('Wrong Date Format. Date Should be in format YYYY-MM-DD.3'))
                        if len(line[1]) > 8 or len(line[1]) < 5:
                            raise ValidationError(_('Wrong Date Format. Date Should be in format YYYY-MM-DD.4'))

                    date = str(xlrd.xldate.xldate_as_datetime(int(float(line[0])), workbook.datemode))
                    bill_date = str(xlrd.xldate.xldate_as_datetime(int(float(line[1])), workbook.datemode))
                    self._check_date_format(date)
                    self._check_date_format(bill_date)
                    values = {
                        'date': date,
                        'bill_date': bill_date,
                        'ref': line[2],
                        'partner': line[3],
                        'journal': line[4],
                        'name': line[5],
                        'product': line[6],
                        'analytic_distribution': line[7],
                        'account_code': line[8],
                        'discount': line[9],
                        'quantity': line[10],
                        'price': line[11],
                        'taxes': line[12],
                        'currency': line[13],
                        }
                    data.append(values)
                else:
                    raise ValidationError(_('Date, Bill Date, Ref and Account are required'))
        data1 = {}
        sorted_data = sorted(data, key=lambda x: x['ref'])

        for key, value in itertools.groupby(sorted_data, key=lambda x: x['ref']):
            sorted_list = []
            for i in value:
                sorted_list.append(i)
                data1.update({key: sorted_list})

        for key in data1.keys():
            lines = []
            values = data1.get(key)
            for val in values:
                move_obj = self.env['account.move']
                partner = self._get_partner(val.get('partner'))
                currency_id = self._check_currency(val.get('currency'))
                journal_search = self.env['account.journal'].sudo()
                if val.get('journal'):
                    journal_search = journal_search.search(
                        [('name', '=', val.get('journal')), ('company_id', '=', self.company_id.id)])

                if not journal_search:
                    journal_search = default_journal and default_journal[0] or False
                if journal_search:
                    move1 = move_obj.search([('date', '=', val.get('date')),
                                             ('ref', '=', val.get('ref')),
                                             ('move_type', '=', move_type),
                                             ('journal_id', '=', journal_search.id)])
                    if move1:
                        move = move1
                    else:
                        move_dict = {
                            'move_type': move_type,
                            'date': val.get('date') or False,
                            'invoice_date': val.get('bill_date') or False,
                            'ref': val.get('ref') or False,
                            'journal_id': journal_search.id,
                        }
                        if partner != None:
                            move_dict.update({'partner_id': partner.id})
                        if currency_id != None:
                            move_dict.update({'currency_id': currency_id.id})
                        move = move_obj.create(move_dict)

                else:
                    raise ValidationError(_('Please Define Journal which are already in system.'))
                # del val['date'], val['bill_date'], val['ref'], val['partner'], val['journal'], val['currency']
                line_data = self._prepare_bill_lines(val)
                lines.append((0, 0, line_data))
            move.write({'invoice_line_ids': lines})
