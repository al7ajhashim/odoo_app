odoo.define('base_import_restrict.import_patch', function (require) {
    "use strict";

    var core = require('web.core');
    var AbstractAction = require('web.AbstractAction');
    var session = require('web.session');
    var Dialog = require('web.Dialog');
    var QWeb = core.qweb;
    var _t = core._t;

    var DataImport = require('base_import.import').DataImport;;

    DataImport.include({
        willStart: function () {
            var self = this;

            var checkGroup = this._rpc({
                model: 'res.users',
                method: 'has_group',
                args: ['base_import_restrict.group_allow_import'],
            }).then(function (has_group) {
                if (!has_group) {
                    self.access_denied = true;
                }
            });

            var def = this._rpc({
                model: this.res_model,
                method: 'get_import_templates',
                context: this.parent_context,
            }).then(function (result) {
                self.importTemplates = result;
            });

            return Promise.all([this._super.apply(this, arguments), checkGroup, def]);
        },

        start: function () {
            var self = this;

            if (this.access_denied) {
                var this_model = this.res_model;
                var model_name_clean = this_model.replace(/\./g, ' ');

                var message = $('<div class="alert alert-danger mt-32" style="font-size:16px; text-align:center;">')
                    .html(_t('<strong>You do not have permission to import files for model:</strong>') +
                        '<br/><strong>' + model_name_clean + '</strong>'
                    );

                var backButton = $('<button type="button" class="btn mt-3" style="background-color: black; color: white;">')
                    .text(_t('Back'))
                    .on('click', function () {
                        window.history.back();
                    });

                this.$el.html($('<div style="text-align:center;">').append(message).append(backButton));
                return Promise.resolve();
            }

            return this._super.apply(this, arguments);
        }
    });
});
