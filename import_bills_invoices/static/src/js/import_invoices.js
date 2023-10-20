/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { useService } from "@web/core/utils/hooks";

class importInvoicesAccountListController extends ListController {
    setup() {
        super.setup();
//        this.orm = useService("orm");
        this.action = useService("action");
    }
    async onImportInvoiceClick() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Import Preparation',
            res_model: 'prepare.import',
            views: [[false, 'form']],
            view_mode: 'form',
            target: 'new',
            context: {
                'default_upload_type': 'invoice',
            }
        });

    }
};

const invoicesImportFromListView = {
    ...listView,
    Controller: importInvoicesAccountListController,
    buttonTemplate: 'importInvoicesAccountListView.buttons',
};

registry.category('views').add('invoices_from_list', invoicesImportFromListView);