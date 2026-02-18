{
    "name": "Customers Only (Sales)",
    "version": "1.0",
    "depends": ["account"],  # porque la acción es account.res_partner_action_customer
    "data": [
        "views/customers_action.xml",
    ],
    "installable": True,
}
