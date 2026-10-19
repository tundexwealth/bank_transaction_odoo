Bank Transaction Monitoring (Odoo 18)
=====================================

This add-on stores bank transactions, reviews high-value and high-velocity
activity, and posts normal transactions to Odoo Accounting.

Assumptions
-----------

- The ₦10,000,000 threshold is evaluated using the transaction-date exchange
  rate converted to NGN. NGN must be active and exchange rates must be configured.
- The sixth transaction in an inclusive rolling 10-minute window triggers
  review. Transactions in `error` state are excluded from the velocity count;
  pending, processed, and review transactions count.
- A normal incoming transaction debits the selected bank journal account and
  credits the customer's receivable account. A normal outgoing transaction
  debits the customer's payable account and credits the bank journal account.
- This is an accounting demonstration, not a connection to a bank payment
  network. It posts a journal entry; it does not initiate or settle a transfer.

Setup
-----

1. Put this directory in an Odoo 18 custom add-ons path and include that path in the server's ``addons_path`` configuration.
2. Install the Odoo ``account`` app and configure an accounting company.
3. Ensure NGN is active and configure relevant currency rates.
4. Create a bank journal with a default bank account. Configure customer receivable and payable accounts on the partner or its properties.
5. Restart Odoo, update the Apps list, and install **Bank Transaction Monitoring**.
6. Assign users to **Bank Monitoring / Transaction User** or **Bank Monitoring / Transaction Manager**. Managers can create/import and edit transaction records.

Entering transactions
---------------------

Use the **Bank Monitoring → Transactions** menu to create records manually or import a CSV. Include ``reference``, ``partner_id/id``, ``amount``, ``currency_id/id``, ``transaction_date``, and ``direction``. Use ``incoming`` or ``outgoing`` for direction. Leave ``state`` empty to use the default ``pending``. References must be unique. For CSV imports, use Odoo's external IDs for partners and currencies, or import the records through the UI and map the corresponding fields.

The scheduled action processes at most 500 pending records per run, every minute. It can also be run manually from **Settings → Technical → Automation → Scheduled Actions** by selecting **Process Bank Transactions** and clicking **Run Manually**.

Processing and review
---------------------

- Transactions converting to at least ₦10,000,000 are moved to `review`.
- Transactions after the fifth customer transaction in a rolling 10-minute
  window are moved to `review`.
- Other transactions create and post an accounting journal entry and become
  `processed`; the entry is linked in `move_id`.
- Failures are stored in `error_message` and the cron continues with other
  transactions. Correct the cause before resetting a failed record to pending.
- Database row locks with `SKIP LOCKED`, bounded batches, unique references,
  and one move per transaction prevent duplicate processing in normal cron
  retries and concurrent workers.

Assessment checks
-----------------

Try a below-threshold transaction, one whose converted NGN amount is exactly
₦10,000,000, a sixth transaction within ten minutes, transactions spread over
more than ten minutes, a duplicate reference, and a backlog over 500 records.
Run the scheduled action again and verify processed rows are not posted twice.
