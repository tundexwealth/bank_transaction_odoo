from bisect import bisect_left, bisect_right
from datetime import timedelta

from odoo import api, fields, models


class BankTransaction(models.Model):
    _name = "bank.transaction"
    _description = "Bank Transaction"
    _order = "transaction_date asc, id asc"

    reference = fields.Char(required=True, index=True, copy=False)
    partner_id = fields.Many2one(
        "res.partner", required=True, index=True, ondelete="restrict"
    )
    amount = fields.Monetary(required=True, currency_field="currency_id")
    direction = fields.Selection(
        [("incoming", "Incoming"), ("outgoing", "Outgoing")],
        required=True,
        default="incoming",
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    transaction_date = fields.Datetime(required=True, index=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("processed", "Processed"),
            ("review", "Review"),
            ("error", "Error"),
        ],
        required=True,
        default="pending",
        index=True,
    )
    processed_at = fields.Datetime(readonly=True)
    journal_id = fields.Many2one(
        "account.journal",
        string="Bank Journal",
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    move_id = fields.Many2one(
        "account.move",
        string="Accounting Entry",
        readonly=True,
        copy=False,
        check_company=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    review_reason = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)

    _sql_constraints = [
        (
            "reference_unique",
            "unique(reference)",
            "Transaction reference must be unique.",
        ),
        (
            "positive_amount",
            "check(amount > 0)",
            "Transaction amount must be greater than zero.",
        ),
        (
            "move_unique",
            "unique(move_id)",
            "An accounting entry can only belong to one bank transaction.",
        ),
    ]

    @api.model
    def cron_process_pending_transactions(self, limit=500):
        """Process one bounded batch of pending transactions."""
        self.env.cr.execute(
            """
                SELECT id
                  FROM bank_transaction
                 WHERE state = 'pending'
                 ORDER BY transaction_date, id
                 LIMIT %s
                 FOR UPDATE SKIP LOCKED
            """,
            [limit],
        )
        transaction_ids = [row[0] for row in self.env.cr.fetchall()]
        transactions = self.browse(transaction_ids)

        # Read customer history in one query, then use binary search for each
        # rolling window rather than issuing a count query per transaction.
        dates_by_partner = {}
        if transactions:
            partner_ids = transactions.mapped("partner_id").ids
            earliest = min(transactions.mapped("transaction_date")) - timedelta(minutes=10)
            latest = max(transactions.mapped("transaction_date"))
            history = self.search(
                [
                    ("partner_id", "in", partner_ids),
                    ("transaction_date", ">=", fields.Datetime.to_string(earliest)),
                    ("transaction_date", "<=", fields.Datetime.to_string(latest)),
                    ("state", "!=", "error"),
                ],
                order="transaction_date asc, id asc",
            )
            for item in history:
                dates_by_partner.setdefault(item.partner_id.id, []).append(
                    item.transaction_date
                )

        ngn = self.env["res.currency"].search([("name", "=", "NGN")], limit=1)
        for transaction in transactions:
            try:
                with self.env.cr.savepoint():
                    reason = False
                    if not ngn:
                        reason = "NGN currency is not configured; manual review required."
                    else:
                        amount_ngn = transaction.currency_id._convert(
                            transaction.amount,
                            ngn,
                            transaction.company_id,
                            transaction.transaction_date.date(),
                        )
                    if not reason and ngn and amount_ngn >= 10_000_000:
                        reason = "Amount is at least ₦10,000,000."
                    elif not reason:
                        start = transaction.transaction_date - timedelta(minutes=10)
                        dates = dates_by_partner.get(transaction.partner_id.id, [])
                        recent_count = bisect_right(
                            dates, transaction.transaction_date
                        ) - bisect_left(dates, start)
                        if recent_count > 5:
                            reason = "Customer made more than five transactions within 10 minutes."

                    if reason:
                        transaction.write({"state": "review", "review_reason": reason})
                    else:
                        move = transaction._create_accounting_move()
                        transaction.write(
                            {
                                "state": "processed",
                                "processed_at": fields.Datetime.now(),
                                "error_message": False,
                                "move_id": move.id,
                            }
                        )
            except Exception as error:
                # The savepoint rolls back only this row's work; other rows continue.
                transaction.invalidate_recordset()
                transaction.write(
                    {
                        "state": "error",
                        "error_message": str(error)[:2000],
                    }
                )

    def _create_accounting_move(self):
        """Post the transaction against bank and customer control accounts."""
        self.ensure_one()
        if self.move_id:
            return self.move_id
        journal = self.journal_id
        if not journal:
            journal = self.env["account.journal"].search(
                [
                    ("type", "=", "bank"),
                    ("company_id", "=", self.company_id.id),
                    ("default_account_id", "!=", False),
                ],
                limit=1,
            )
        if not journal or not journal.default_account_id:
            raise ValueError("Configure a bank journal with a default account.")

        company_currency = self.company_id.currency_id
        company_amount = self.currency_id._convert(
            self.amount,
            company_currency,
            self.company_id,
            self.transaction_date.date(),
        )
        if self.direction == "incoming":
            bank_debit, bank_credit = company_amount, 0.0
            customer_debit, customer_credit = 0.0, company_amount
            customer_account = self.partner_id.property_account_receivable_id
        else:
            bank_debit, bank_credit = 0.0, company_amount
            customer_debit, customer_credit = company_amount, 0.0
            customer_account = self.partner_id.property_account_payable_id
        bank_account = journal.default_account_id
        if not customer_account:
            raise ValueError("Configure the customer's receivable/payable account.")

        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "date": self.transaction_date.date(),
                "ref": self.reference,
                "company_id": self.company_id.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": self.reference,
                            "partner_id": self.partner_id.id,
                            "account_id": bank_account.id,
                            "debit": bank_debit,
                            "credit": bank_credit,
                            "currency_id": self.currency_id.id,
                            "amount_currency": (
                                self.amount
                                if self.direction == "incoming"
                                else -self.amount
                            ),
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": self.reference,
                            "partner_id": self.partner_id.id,
                            "account_id": customer_account.id,
                            "debit": customer_debit,
                            "credit": customer_credit,
                            "currency_id": self.currency_id.id,
                            "amount_currency": (
                                -self.amount
                                if self.direction == "incoming"
                                else self.amount
                            ),
                        },
                    ),
                ],
            }
        )
        move.action_post()
        return move
