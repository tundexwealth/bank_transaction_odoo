{
    "name": "Bank Transaction Monitoring",
    "version": "18.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Monitor bank transactions for review and unusual activity",
    "description": "Periodically processes transactions, flags large amounts, and detects high transaction velocity.",
    "depends": ["base", "account"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/bank_transaction_views.xml",
        "data/ir_cron.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
