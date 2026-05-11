import { Base } from "@point_of_sale/app/models/related_models";
import { registry } from "@web/core/registry";

export class AccountPaymentTerm extends Base {
    static pythonModel = "account.payment.term";
}

registry.category("pos_available_models").add(AccountPaymentTerm.pythonModel, AccountPaymentTerm);
