from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBankTransactionMonitoring(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.ngn = cls.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "NGN")], limit=1
        )
        if not cls.ngn:
            cls.ngn = cls.env["res.currency"].create(
                {"name": "NGN", "symbol": "₦"}
            )
        elif not cls.ngn.active:
            cls.ngn.active = True
        cls.env["res.currency.rate"].create(
            {
                "name": fields.Date.today(),
                "rate": 1.0,
                "currency_id": cls.ngn.id,
                "company_id": cls.company.id,
            }
        )

        Account = cls.env["account.account"].with_company(cls.company)
        cls.bank_account = Account.create(
            {
                "name": "Monitoring Test Bank",
                "code": "BMON1",
                "account_type": "asset_cash",
                "company_ids": [Command.set(cls.company.ids)],
            }
        )
        cls.receivable_account = Account.create(
            {
                "name": "Monitoring Test Receivable",
                "code": "BMON2",
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_ids": [Command.set(cls.company.ids)],
            }
        )
        cls.payable_account = Account.create(
            {
                "name": "Monitoring Test Payable",
                "code": "BMON3",
                "account_type": "liability_payable",
                "reconcile": True,
                "company_ids": [Command.set(cls.company.ids)],
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Monitoring Test Bank Journal",
                "code": "BMON1",
                "type": "bank",
                "company_id": cls.company.id,
                "default_account_id": cls.bank_account.id,
            }
        )

    def _make_partner(self, name):
        partner = self.env["res.partner"].create({"name": name})
        partner.with_company(self.company).write(
            {
                "property_account_receivable_id": self.receivable_account.id,
                "property_account_payable_id": self.payable_account.id,
            }
        )
        return partner

    def _make_transaction(self, reference, partner, amount, transaction_date):
        return self.env["bank.transaction"].create(
            {
                "reference": reference,
                "partner_id": partner.id,
                "amount": amount,
                "currency_id": self.ngn.id,
                "transaction_date": transaction_date,
                "journal_id": self.journal.id,
                "company_id": self.company.id,
                "direction": "incoming",
            }
        )

    def test_threshold_velocity_and_idempotent_processing(self):
        customer = self._make_partner("Monitoring velocity customer")
        normal_customer = self._make_partner("Monitoring normal customer")
        now = fields.Datetime.now().replace(second=0, microsecond=0)

        high_value = self._make_transaction(
            "BMON-HIGH", customer, 10_000_000, now - timedelta(hours=1)
        )
        normal = self._make_transaction(
            "BMON-NORMAL", normal_customer, 5_000, now
        )
        velocity_transactions = self.env["bank.transaction"]
        for index in range(6):
            velocity_transactions |= self._make_transaction(
                "BMON-VELOCITY-%s" % index,
                customer,
                1_000,
                now + timedelta(minutes=index),
            )

        self.env["bank.transaction"].cron_process_pending_transactions()

        self.assertEqual(high_value.state, "review")
        self.assertIn("₦10,000,000", high_value.review_reason)
        self.assertEqual(normal.state, "processed")
        self.assertTrue(normal.move_id)
        self.assertTrue(normal.move_id.posted_before)
        self.assertEqual(velocity_transactions[:5].mapped("state"), ["processed"] * 5)
        self.assertEqual(velocity_transactions[5].state, "review")
        self.assertIn("more than five", velocity_transactions[5].review_reason)

        first_move_id = normal.move_id.id
        self.env["bank.transaction"].cron_process_pending_transactions()
        normal.invalidate_recordset()
        self.assertEqual(normal.state, "processed")
        self.assertEqual(normal.move_id.id, first_move_id)
        self.assertEqual(
            self.env["account.move"].search_count([("ref", "=", "BMON-NORMAL")]),
            1,
        )
