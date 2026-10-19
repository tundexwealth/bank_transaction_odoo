# Bank Transaction Monitoring

An Odoo 18 add-on that records bank transactions, sends high-risk activity for
review, and posts eligible transactions to Odoo Accounting. It is designed as a
small, installable assessment project and can also serve as a starting point
for a larger monitoring workflow.

## What it does

- Sends transactions whose value is **₦10,000,000 or more** to review. The
  transaction is converted to NGN using the rate for the transaction date
  before the threshold is checked.
- Sends customer activity to review when more than five non-error transactions
  fall in the inclusive rolling ten-minute window.
- Posts eligible incoming and outgoing transactions as accounting journal
  entries and links the entry to the transaction.
- Processes a bounded batch of up to 500 pending transactions every minute.
- Records a per-transaction error and continues the batch if an individual
  transaction cannot be posted.
- Uses database row locking, unique references, and a unique journal-entry link
  to help prevent duplicate processing during retries or concurrent runs.

> **Important:** This add-on does not connect to a bank or initiate payments.
> It stores transactions entered or imported into Odoo and, for eligible rows,
> posts accounting entries. Review the entry before using this code in a live
> accounting environment.

## Requirements

- Odoo 18.0
- The Odoo **Accounting** (`account`) application
- A configured Odoo company and chart of accounts
- NGN enabled in Odoo, with exchange rates configured for the relevant dates
- A bank journal with a default account for posting normal transactions
- Receivable and payable accounts configured for customers used in normal
  transactions

## Installation

### Add the module to the add-ons path

Place this directory in an Odoo add-ons directory. For example:

```text
<odoo-source>/addons/bank_transactions_monitoring/
```

If it is in a separate custom-addons directory, add that directory to
`addons_path` in `odoo.conf`:

```ini
addons_path = /path/to/odoo/addons,/path/to/custom-addons
```

On Windows, use Windows paths in the configuration file. Restart the Odoo
server after changing the add-ons path.

### Install from the Odoo interface

1. Sign in as an administrator and open **Apps**.
2. Choose **Update Apps List**. If that option is not visible, activate
   developer mode first.
3. Clear the default **Apps** search filter if necessary.
4. Search for **Bank Transaction Monitoring** and click **Install**.
5. Assign the relevant internal users to **Bank Transaction Monitoring / Transaction User**
   or **Bank Transaction Monitoring / Transaction Manager** in their user access
   rights.

The Transaction User role can read transaction records. The Transaction
Manager role can read, create, edit, and delete them. Assign the manager role
only to users who need to maintain transaction data.

### Install or upgrade from the command line

Run these commands from the Odoo source directory, adjusting the config file
and database name for your environment. Stop the normal Odoo server before
running an installation or upgrade command against the same database.

```bash
# First installation
python odoo-bin -c odoo.conf -d <database_name> -i bank_transactions_monitoring --stop-after-init

# Upgrade after changing the add-on
python odoo-bin -c odoo.conf -d <database_name> -u bank_transactions_monitoring --stop-after-init
```

After the command completes, start the Odoo server again. Check the log for
`Module bank_transactions_monitoring loaded` or an installation error.

## Odoo configuration

### Enable NGN and exchange rates

1. Open **Accounting** or **Invoicing** and go to **Configuration → Settings**.
2. Enable multi-currency if Odoo asks for it, then save.
3. Open **Accounting/Invoicing → Configuration → Currencies**, activate NGN,
   and configure the exchange rate for each relevant transaction date.

Rates are date-sensitive. A transaction denominated in another currency is
converted to NGN using the transaction date's rate. For an NGN transaction,
the amount is compared directly in NGN.

### Configure the bank journal and customer accounts

1. Open **Accounting/Invoicing → Configuration → Journals** and create or open
   a **Bank** journal.
2. Set its **Default Account** to the company's bank or cash account, then save.
3. Ensure each customer has a receivable account and payable account. These
   fields may be under the contact's **Invoicing** tab, in **Accounting Entries**.
   For a child contact, accounting properties are managed on the parent company.
   If those fields are hidden, an administrator with Accounting access must
   configure them. Odoo may already provide the accounts through the chart of
   accounts or company defaults.

These accounts are needed only when a transaction is posted as normal. A
transaction flagged for review does not create a journal entry.

## Entering transactions

Open **Bank Monitoring → Transactions** and create a record. The transaction
form includes:

| Field | Purpose |
| --- | --- |
| Reference | Required unique transaction reference |
| Partner | Customer associated with the transaction |
| Direction | `Incoming` or `Outgoing` |
| Transaction Date | Date and time used for currency conversion and velocity checks |
| Amount and Currency | Original transaction amount and currency |
| Bank Journal | Optional when a bank journal with a default account can be found automatically |
| State | Starts as `Pending`; the scheduled action updates it |

References must be unique. To import CSV data, use Odoo's import feature and
map the relevant fields. A typical import includes `reference`, `partner_id/id`,
`direction`, `transaction_date`, `amount`, and `currency_id/id`. Use valid Odoo
external IDs for related records, or select the matching records through the
import interface. Supported direction values are `incoming` and `outgoing`.
Leave state and accounting-entry fields to Odoo.

## Processing and outcomes

The scheduled action **Process Bank Transactions** runs every minute and
processes up to 500 pending records per run, oldest transaction date first.
It can also be run manually in developer mode from **Settings → Technical →
Automation → Scheduled Actions**. Open **Process Bank Transactions** and use
**Run Manually**.

| Outcome | Meaning |
| --- | --- |
| **Review** | The NGN value is at least ₦10,000,000, or the customer's rolling ten-minute transaction count is greater than five. A review reason is recorded. |
| **Processed** | The transaction passed the review checks and Odoo posted a journal entry. The entry is linked on the transaction. |
| **Error** | Posting failed. Odoo records the error message and continues processing other transactions in the batch. |

Incoming transactions debit the bank account and credit the customer's
receivable account. Outgoing transactions debit the customer's payable account
and credit the bank account. Amounts are converted to the company's currency
for the journal entry.

Transactions in the `error` state are excluded from the velocity count. Pending,
processed, and review transactions are included. The ten-minute boundary is
inclusive. If multiple transactions have exactly the same timestamp, the batch
can evaluate them as one burst and flag more than just the row that was entered
last.

If a transaction enters `error`, correct the cause first (for example, add the
missing bank journal default account or customer account). Then return the
record to `Pending` and run the scheduled action again. Processed rows are not
reposted on a retry; each transaction can link to only one accounting entry.

## Testing

### Run the automated Odoo test

Use a disposable test database, not a production database. From the Odoo source
directory:

```bash
python odoo-bin -c odoo.conf -d bank_monitoring_test -i bank_transactions_monitoring --test-enable --test-tags /bank_transactions_monitoring --stop-after-init
```

On Windows with the virtual environment in this project, run the equivalent
PowerShell command:

```powershell
.\.venv\Scripts\python.exe .\odoo-bin -c .\odoo.conf -d bank_monitoring_test -i bank_transactions_monitoring --test-enable --test-tags /bank_transactions_monitoring --stop-after-init
```

The included test checks an exact-threshold transaction, normal posting,
six transactions within the velocity window, and duplicate-safe retry behavior.

### Check behavior in the Odoo interface

1. Create a test customer and make sure its accounting accounts are configured.
2. Create one transaction below ₦10,000,000 with a unique reference; it should
   process and link to a posted accounting entry.
3. Create a transaction for exactly ₦10,000,000 NGN; it should enter **Review**.
4. Create six low-value transactions for the same customer with dates inside
   ten minutes. The sixth should enter **Review** when the timestamps are
   strictly increasing and the earlier five are processed or otherwise count
   toward the window.
5. Run the scheduled action again and confirm a processed transaction still
   links to only one journal entry.
6. Try a duplicate reference; Odoo should reject it. Correct an error cause,
   reset that record to Pending, and verify that other rows continue processing.

## Troubleshooting

- **The add-on does not appear in Apps:** Confirm the folder is in `addons_path`,
  restart Odoo, update the Apps list, and remove the default Apps filter.
- **The Bank Monitoring menu is missing:** Assign your internal user to the
  module's Transaction User or Transaction Manager group, then refresh Odoo.
- **A normal transaction enters Error:** Read its error message. Configure a
  bank journal with a default account and the partner's receivable/payable
  account, and verify that the transaction date and currency rate are valid.
- **A transaction enters Review unexpectedly:** Check the NGN rate for the
  transaction date and inspect the review reason and the customer's other
  transactions in the preceding ten minutes.
- **The scheduled action has not run:** Confirm **Process Bank Transactions**
  is active and the Odoo server's scheduled-action worker is running. It runs
  periodically; use **Run Manually** to check immediately.

## License

LGPL-3. See the `license` field in `__manifest__.py`.
