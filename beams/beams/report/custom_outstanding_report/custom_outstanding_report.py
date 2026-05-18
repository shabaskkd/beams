import frappe
from collections import OrderedDict
from frappe.utils import getdate, add_days


# ─────────────────────────────────────────────────────────────────────────────
# Aging bucket boundaries (in days from invoice date to to_date)
# ─────────────────────────────────────────────────────────────────────────────
AGING_BUCKETS = [
    ("lt_30",   "< 30",    0,   30),
    ("b_30_60", "30 - 60", 30,  60),
    ("b_60_90", "60 - 90", 60,  90),
    ("b_90_180","90 - 180",90,  180),
    ("gt_180",  "> 180",   180, None),
]
AGING_FIELDNAMES = [b[0] for b in AGING_BUCKETS]


def _aging_bucket(due_days):
    """Return which bucket fieldname a given due_days falls into."""
    for fieldname, _label, lo, hi in AGING_BUCKETS:
        if hi is None:
            if due_days >= lo:
                return fieldname
        elif lo <= due_days < hi:
            return fieldname
    return "lt_30"


def execute(filters=None):
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data


def get_columns(filters):
    out_type = (filters or {}).get("outstanding_type") or "Receivable"
    party_type = (filters or {}).get("party_type") or "Customer"

    if out_type == "Receivable" and party_type == "Customer":
        aging_cols = [
            {"fieldname": b[0], "label": b[1], "fieldtype": "Currency", "width": 110}
            for b in AGING_BUCKETS
        ]
        return [
            {"fieldname": "date",           "label": "Date",           "fieldtype": "Date",     "width": 100},
            {"fieldname": "invoice_no",     "label": "Invoice No",     "fieldtype": "Data",     "width": 160},
            {"fieldname": "agency",         "label": "Agency",         "fieldtype": "Data",     "width": 180},
            {"fieldname": "client",         "label": "Client",         "fieldtype": "Data",     "width": 180},
            {"fieldname": "executive",      "label": "Executive",      "fieldtype": "Data",     "width": 150},
            {"fieldname": "item",           "label": "Item",           "fieldtype": "Data",     "width": 220},
            {"fieldname": "group",          "label": "Group",          "fieldtype": "Data",     "width": 160},
            {"fieldname": "lt_30",          "label": "< 30",           "fieldtype": "Currency", "width": 100},
            {"fieldname": "b_30_60",        "label": "30 - 60",        "fieldtype": "Currency", "width": 100},
            {"fieldname": "b_60_90",        "label": "60 - 90",        "fieldtype": "Currency", "width": 100},
            {"fieldname": "b_90_180",       "label": "90 - 180",       "fieldtype": "Currency", "width": 100},
            {"fieldname": "gt_180",         "label": "> 180",          "fieldtype": "Currency", "width": 100},
            {"fieldname": "pending_amount", "label": "Pending Amount", "fieldtype": "Currency", "width": 150},
            {"fieldname": "due_on",         "label": "Due On",         "fieldtype": "Date",     "width": 110},
            {"fieldname": "due_days",       "label": "Due Days",       "fieldtype": "Int",      "width": 90},
        ]

    elif out_type == "Receivable" and party_type == "Employee":
        return [
            {"fieldname": "date",           "label": "Date",           "fieldtype": "Date",     "width": 100},
            {"fieldname": "invoice_no",     "label": "Reference No",   "fieldtype": "Data",     "width": 160},
            {"fieldname": "employee",       "label": "Employee Name",  "fieldtype": "Data",     "width": 220},
            {"fieldname": "group",          "label": "Group",          "fieldtype": "Data",     "width": 160},
            {"fieldname": "pending_amount", "label": "Pending Amount", "fieldtype": "Currency", "width": 150},
            {"fieldname": "due_days",       "label": "Due Days",       "fieldtype": "Int",      "width": 90},
        ]

    elif out_type == "Payable" and party_type == "Supplier":
        return [
            {"fieldname": "date",           "label": "Date",           "fieldtype": "Date",     "width": 100},
            {"fieldname": "invoice_no",     "label": "Invoice No",     "fieldtype": "Data",     "width": 160},
            {"fieldname": "supplier",       "label": "Supplier",       "fieldtype": "Data",     "width": 220},
            {"fieldname": "item",           "label": "Item",           "fieldtype": "Data",     "width": 220},
            {"fieldname": "group",          "label": "Group",          "fieldtype": "Data",     "width": 160},
            {"fieldname": "pending_amount", "label": "Pending Amount", "fieldtype": "Currency", "width": 150},
            {"fieldname": "due_days",       "label": "Due Days",       "fieldtype": "Int",      "width": 90},
        ]

    elif out_type == "Payable" and party_type == "Employee":
        return [
            {"fieldname": "date",           "label": "Date",           "fieldtype": "Date",     "width": 100},
            {"fieldname": "invoice_no",     "label": "Reference No",   "fieldtype": "Data",     "width": 160},
            {"fieldname": "employee",       "label": "Employee Name",  "fieldtype": "Data",     "width": 220},
            {"fieldname": "group",          "label": "Group",          "fieldtype": "Data",     "width": 160},
            {"fieldname": "pending_amount", "label": "Pending Amount", "fieldtype": "Currency", "width": 150},
            {"fieldname": "due_days",       "label": "Due Days",       "fieldtype": "Int",      "width": 90},
        ]
    return []


def get_data(filters):
    out_type = (filters or {}).get("outstanding_type") or "Receivable"
    party_type = (filters or {}).get("party_type") or "Customer"

    # Guard: company is mandatory for all queries
    if not (filters or {}).get("company"):
        return []

    if out_type == "Receivable" and party_type == "Customer":
        raw_data = get_receivable_customer_data(filters)
    elif out_type == "Receivable" and party_type == "Employee":
        raw_data = get_employee_data(filters, account_type="Receivable")
    elif out_type == "Payable" and party_type == "Supplier":
        raw_data = get_payable_supplier_data(filters)
    elif out_type == "Payable" and party_type == "Employee":
        raw_data = get_employee_data(filters, account_type="Payable")
    else:
        raw_data = []

    return build_hierarchical_data(raw_data, out_type, party_type)


def get_receivable_customer_data(filters):
    """
    Query Sales Invoice directly.
    - outstanding_amount maintained by ERPNext → always correct, never negative.
    - Supports specific filters: agency, client, executive, item_filter, group_filter.
    - Grouping (hierarchical display) is always by agency (customer) regardless of filter.
    """
    conditions = ["si.docstatus = 1", "si.outstanding_amount > 0.005", "si.company = %(company)s"]

    if filters.get("from_date"):
        conditions.append("si.posting_date >= %(from_date)s")
    if filters.get("to_date"):
        conditions.append("si.posting_date <= %(to_date)s")

    # ── Specific Receivable+Customer filters ──────────────────────────────
    # Agency: the invoice's main customer (si.customer)
    if filters.get("agency"):
        conditions.append("si.customer = %(agency)s")

    # Client: the actual_customer field on the Sales Invoice
    if filters.get("client"):
        conditions.append("si.actual_customer = %(client)s")

    # Executive: employee linked as executive on the invoice
    if filters.get("executive"):
        # executive field stores employee ID; executive_name stores display name
        conditions.append(
            "(si.executive = %(executive)s OR si.executive_name = "
            "(SELECT employee_name FROM `tabEmployee` WHERE name = %(executive)s LIMIT 1))"
        )

    # Item: at least one item line matches — use EXISTS to keep per-invoice pending_amount
    if filters.get("item_filter"):
        conditions.append(
            "EXISTS (SELECT 1 FROM `tabSales Invoice Item` sii2 "
            "WHERE sii2.parent = si.name "
            "AND (sii2.item_code = %(item_filter)s OR sii2.item_name = %(item_filter)s))"
        )

    # Group: the debtor ledger account used in the invoice
    if filters.get("group_filter"):
        conditions.append("si.debit_to = %(group_filter)s")

    # Backward compat: old generic party filter
    if filters.get("party") and not filters.get("agency"):
        conditions.append("si.customer = %(party)s")

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            si.posting_date                                                         AS date,
            si.name                                                                 AS invoice_no,
            si.customer                                                             AS party,
            COALESCE(NULLIF(si.actual_customer, ''), si.customer_name, si.customer) AS client,
            COALESCE(si.executive_name, '')                                         AS executive,
            si.debit_to                                                             AS `group`,
            si.outstanding_amount                                                   AS pending_amount,
            DATEDIFF(%(to_date)s, si.posting_date)                                 AS due_days,
            COALESCE(NULLIF(cust.credit_days, ''), '0')                            AS credit_days_raw,
            (
                SELECT GROUP_CONCAT(
                    COALESCE(NULLIF(sii.item_name,''), sii.item_code)
                    ORDER BY sii.idx SEPARATOR ', '
                )
                FROM `tabSales Invoice Item` sii
                WHERE sii.parent = si.name
            )                                                                       AS item
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
        WHERE {where_clause}
        ORDER BY si.customer, si.posting_date ASC
    """
    rows = frappe.db.sql(query, filters, as_dict=True)

    # Compute Due On and aging buckets in Python
    for row in rows:
        # ── Due On ──────────────────────────────────────────────────────────
        try:
            credit_days = int(row.get("credit_days_raw") or 0)
        except (ValueError, TypeError):
            credit_days = 0
        row["due_on"] = add_days(row["date"], credit_days) if credit_days else None

        # ── Aging buckets ────────────────────────────────────────────────────
        due_days = int(row.get("due_days") or 0)
        bucket = _aging_bucket(due_days)
        for fn in AGING_FIELDNAMES:
            row[fn] = row["pending_amount"] if fn == bucket else 0

    return rows


def get_payable_supplier_data(filters):
    """
    Fetch payable outstanding for suppliers from TWO sources (UNIONed):
      1. Purchase Invoices  - uses outstanding_amount maintained by ERPNext (always > 0).
      2. Journal Entries    - uses GL Entry net credit balance on payable accounts (positive only).
    Supports supplier_filter, s_item_filter, s_group_filter.
    """
    # ── Conditions for Purchase Invoice branch ─────────────────────────────
    pi_cond = ["pi.docstatus = 1", "pi.outstanding_amount > 0.005", "pi.company = %(company)s"]
    if filters.get("from_date"):
        pi_cond.append("pi.posting_date >= %(from_date)s")
    if filters.get("to_date"):
        pi_cond.append("pi.posting_date <= %(to_date)s")
    if filters.get("supplier_filter"):
        pi_cond.append("pi.supplier = %(supplier_filter)s")
    if filters.get("s_group_filter"):
        pi_cond.append("pi.credit_to = %(s_group_filter)s")
    if filters.get("s_item_filter"):
        pi_cond.append(
            "EXISTS (SELECT 1 FROM `tabPurchase Invoice Item` pii2 "
            "WHERE pii2.parent = pi.name "
            "AND (pii2.item_code = %(s_item_filter)s OR pii2.item_name = %(s_item_filter)s))"
        )
    pi_where = " AND ".join(pi_cond)

    # ── Conditions for GL Entry (Journal Entry) branch ─────────────────────
    gle_cond = [
        "gle.company = %(company)s",
        "gle.is_cancelled = 0",
        "gle.party_type = 'Supplier'",
        "gle.voucher_type NOT IN ('Purchase Invoice', 'Payment Entry')",
    ]
    if filters.get("from_date"):
        gle_cond.append("gle.posting_date >= %(from_date)s")
    if filters.get("to_date"):
        gle_cond.append("gle.posting_date <= %(to_date)s")
    if filters.get("supplier_filter"):
        gle_cond.append("gle.party = %(supplier_filter)s")
    if filters.get("s_group_filter"):
        gle_cond.append("gle.account = %(s_group_filter)s")
    gle_where = " AND ".join(gle_cond)

    query = f"""
        SELECT
            pi.posting_date                                                          AS date,
            pi.name                                                                  AS invoice_no,
            pi.supplier                                                              AS party,
            pi.credit_to                                                             AS `group`,
            pi.outstanding_amount                                                    AS pending_amount,
            DATEDIFF(%(to_date)s, pi.posting_date)                                  AS due_days,
            (
                SELECT GROUP_CONCAT(
                    COALESCE(NULLIF(pii.item_name,''), pii.item_code)
                    ORDER BY pii.idx SEPARATOR ', '
                )
                FROM `tabPurchase Invoice Item` pii
                WHERE pii.parent = pi.name
            )                                                                        AS item
        FROM `tabPurchase Invoice` pi
        WHERE {pi_where}

        UNION ALL

        SELECT
            gle.posting_date                                                         AS date,
            gle.voucher_no                                                           AS invoice_no,
            gle.party                                                                AS party,
            gle.account                                                              AS `group`,
            SUM(gle.credit) - SUM(gle.debit)                                        AS pending_amount,
            DATEDIFF(%(to_date)s, gle.posting_date)                                 AS due_days,
            NULL                                                                     AS item
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE {gle_where}
            AND acc.account_type = 'Payable'
        GROUP BY gle.voucher_no, gle.party, gle.account
        HAVING pending_amount > 0.005

        ORDER BY party, date ASC
    """
    return frappe.db.sql(query, filters, as_dict=True)




def get_employee_data(filters, account_type="Receivable"):
    """
    Employee outstanding from GL Entries on employee-linked accounts.
    Only positive balances (HAVING > 0) - advances don't appear as negatives.
    Supports emp_filter (employee ID) and emp_group_filter (account).
    """
    amount_calc = (
        "SUM(gle.debit) - SUM(gle.credit)"
        if account_type == "Receivable"
        else "SUM(gle.credit) - SUM(gle.debit)"
    )

    conditions = [
        "gle.company = %(company)s",
        "gle.is_cancelled = 0",
        "gle.party_type = 'Employee'",
    ]
    if filters.get("from_date"):
        conditions.append("gle.posting_date >= %(from_date)s")
    if filters.get("to_date"):
        conditions.append("gle.posting_date <= %(to_date)s")
    if filters.get("emp_filter"):
        conditions.append("gle.party = %(emp_filter)s")
    if filters.get("emp_group_filter"):
        conditions.append("gle.account = %(emp_group_filter)s")

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            gle.posting_date                              AS date,
            gle.voucher_no                                AS invoice_no,
            gle.party,
            gle.account                                   AS `group`,
            {amount_calc}                                 AS pending_amount,
            DATEDIFF(%(to_date)s, gle.posting_date)       AS due_days
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE {where_clause}
            AND acc.account_type = '{account_type}'
        GROUP BY gle.voucher_no, gle.party, gle.account
        HAVING pending_amount > 0.005
        ORDER BY gle.party, gle.posting_date ASC
    """
    rows = frappe.db.sql(query, filters, as_dict=True)

    # Enrich with readable employee name (cached)
    emp_name_cache = {}
    for row in rows:
        emp_id = row["party"]
        if emp_id not in emp_name_cache:
            emp_name_cache[emp_id] = (
                frappe.db.get_value("Employee", emp_id, "employee_name") or emp_id
            )
        row["employee"] = emp_name_cache[emp_id]

    return rows


def build_hierarchical_data(raw_data, out_type, party_type):
    """Insert bold header and total rows around each party's invoice detail rows."""
    is_receivable_customer = out_type == "Receivable" and party_type == "Customer"

    if is_receivable_customer:
        party_fieldname = "agency"
    elif out_type == "Payable" and party_type == "Supplier":
        party_fieldname = "supplier"
    else:
        party_fieldname = "employee"

    # Group rows by party, preserving insertion order
    grouped = OrderedDict()
    for row in raw_data:
        party = row.get("party") or ""
        grouped.setdefault(party, []).append(row)

    final_data = []
    for party, rows in grouped.items():
        if not rows:
            continue

        total_outstanding = sum(r.get("pending_amount") or 0 for r in rows)

        # Aggregate aging buckets for header/total (only for Receivable+Customer)
        bucket_totals = {}
        if is_receivable_customer:
            for fn in AGING_FIELDNAMES:
                bucket_totals[fn] = sum(r.get(fn) or 0 for r in rows)

        # ── Header row ──────────────────────────────────────────────────────
        header = {
            party_fieldname: party,
            "group": rows[0].get("group", ""),
            "pending_amount": total_outstanding,
            "is_header": 1,
            "bold": 1,
        }
        header.update(bucket_totals)
        final_data.append(header)

        # ── Detail rows ─────────────────────────────────────────────────────
        for r in rows:
            r["bold"] = 0
            if party_fieldname == "agency":
                r["agency"] = ""   # Party already shown in header row
            final_data.append(r)

        # ── Total row ───────────────────────────────────────────────────────
        total_row = {
            party_fieldname: f"Total  ➜  {party}",
            "pending_amount": total_outstanding,
            "is_total": 1,
            "bold": 1,
        }
        total_row.update(bucket_totals)
        final_data.append(total_row)

    return final_data
