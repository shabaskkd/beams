import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
    if not filters.get("company"):
        frappe.throw(_("Company is required"))
    if not filters.get("from_date"):
        frappe.throw(_("From Date is required"))
    if not filters.get("to_date"):
        frappe.throw(_("To Date is required"))

    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"fieldname": "account", "label": _("Account / Party"), "fieldtype": "Data", "width": 300},
        {"fieldname": "opening_debit", "label": _("Opening (Dr)"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "opening_credit", "label": _("Opening (Cr)"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "debit", "label": _("Debit"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "credit", "label": _("Credit"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "closing_debit", "label": _("Closing (Dr)"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "closing_credit", "label": _("Closing (Cr)"), "fieldtype": "Currency", "options": "currency", "width": 120},
    ]

def get_data(filters):
    accounts = get_accounts(filters.company)
    accounts_by_name = {d.name: d for d in accounts}
    company_currency = frappe.get_cached_value("Company", filters.company, "default_currency")

    # Fetch raw GL data
    gl_entries = get_gl_entries(filters)
    
    # Map party names efficiently (bulk fetch)
    unique_parties = {}
    for entry in gl_entries:
        if entry.party_type and entry.party:
            unique_parties.setdefault(entry.party_type, set()).add(entry.party)

    party_names = {}
    for ptype, parties in unique_parties.items():
        if ptype == "Customer":
            records = frappe.get_all("Customer", filters={"name": ("in", list(parties))}, fields=["name", "customer_name"])
            for r in records: party_names[(ptype, r.name)] = r.customer_name or r.name
        elif ptype == "Supplier":
            records = frappe.get_all("Supplier", filters={"name": ("in", list(parties))}, fields=["name", "supplier_name"])
            for r in records: party_names[(ptype, r.name)] = r.supplier_name or r.name
        elif ptype == "Employee":
            records = frappe.get_all("Employee", filters={"name": ("in", list(parties))}, fields=["name", "employee_name"])
            for r in records: party_names[(ptype, r.name)] = r.employee_name or r.name
        else:
            for p in parties: party_names[(ptype, p)] = p
    
    # Group GL entries by account
    entries_by_account = {}
    for entry in gl_entries:
        entries_by_account.setdefault(entry.account, []).append(entry)

    party_rows = []

    # Bottom-up traversal
    for acc in reversed(accounts):
        if not acc.is_group:
            entries = entries_by_account.get(acc.name, [])
            party_entries = [e for e in entries if e.party]
            
            has_party_rows = len(party_entries) > 0
            acc.has_party_rows = has_party_rows
            
            if has_party_rows:
                # 1. Virtual Party Parent Account
                for entry in party_entries:
                    # Net Party Opening
                    p_open_net = flt(entry.opening_debit) - flt(entry.opening_credit)
                    p_open_dr = p_open_net if p_open_net > 0 else 0.0
                    p_open_cr = abs(p_open_net) if p_open_net < 0 else 0.0
                    
                    # Transaction (Actual, No netting)
                    p_debit = flt(entry.debit)
                    p_credit = flt(entry.credit)
                    
                    # Calculate and Net Party Closing
                    p_close_dr = p_open_dr + p_debit
                    p_close_cr = p_open_cr + p_credit
                    p_close_net = p_close_dr - p_close_cr
                    p_close_dr = p_close_net if p_close_net > 0 else 0.0
                    p_close_cr = abs(p_close_net) if p_close_net < 0 else 0.0
                    
                    party_has_value = any(abs(v) > 0.001 for v in [p_open_dr, p_open_cr, p_debit, p_credit, p_close_dr, p_close_cr])
                    
                    if party_has_value:
                        party_title = party_names.get((entry.party_type, entry.party), entry.party)

                        party_rows.append({
                            "account": party_title,
                            "party": entry.party,
                            "party_type": entry.party_type,
                            "parent_account": acc.name,
                            "indent": acc.indent + 1,
                            "is_group_account": 0,
                            "is_party": 1,
                            "currency": company_currency,
                            "opening_debit": p_open_dr,
                            "opening_credit": p_open_cr,
                            "debit": p_debit,
                            "credit": p_credit,
                            "closing_debit": p_close_dr,
                            "closing_credit": p_close_cr,
                        })
                        
                        # Accumulate directly to Virtual Parent (Sum of netted party balances)
                        acc.opening_debit += p_open_dr
                        acc.opening_credit += p_open_cr
                        acc.debit += p_debit
                        acc.credit += p_credit
                        acc.closing_debit += p_close_dr
                        acc.closing_credit += p_close_cr

                # Handle any unexpected non-party entries on a party ledger safely
                non_party_entries = [e for e in entries if not e.party]
                if non_party_entries:
                    np_open_dr = sum(flt(e.opening_debit) for e in non_party_entries)
                    np_open_cr = sum(flt(e.opening_credit) for e in non_party_entries)
                    np_debit = sum(flt(e.debit) for e in non_party_entries)
                    np_credit = sum(flt(e.credit) for e in non_party_entries)
                    
                    np_open_net = np_open_dr - np_open_cr
                    np_open_dr = np_open_net if np_open_net > 0 else 0.0
                    np_open_cr = abs(np_open_net) if np_open_net < 0 else 0.0
                    
                    np_close_dr = np_open_dr + np_debit
                    np_close_cr = np_open_cr + np_credit
                    np_close_net = np_close_dr - np_close_cr
                    np_close_dr = np_close_net if np_close_net > 0 else 0.0
                    np_close_cr = abs(np_close_net) if np_close_net < 0 else 0.0
                    
                    acc.opening_debit += np_open_dr
                    acc.opening_credit += np_open_cr
                    acc.debit += np_debit
                    acc.credit += np_credit
                    acc.closing_debit += np_close_dr
                    acc.closing_credit += np_close_cr

            else:
                # 2. Normal Ledger Account
                for entry in entries:
                    acc.opening_debit += flt(entry.opening_debit)
                    acc.opening_credit += flt(entry.opening_credit)
                    acc.debit += flt(entry.debit)
                    acc.credit += flt(entry.credit)
                    
                # Net opening for leaf
                net_opening = acc.opening_debit - acc.opening_credit
                if net_opening > 0:
                    acc.opening_debit, acc.opening_credit = net_opening, 0.0
                else:
                    acc.opening_credit, acc.opening_debit = abs(net_opening), 0.0
                    
                # Calculate closing
                acc.closing_debit = acc.opening_debit + acc.debit
                acc.closing_credit = acc.opening_credit + acc.credit
                
                # Net closing for leaf
                net_closing = acc.closing_debit - acc.closing_credit
                if net_closing > 0:
                    acc.closing_debit, acc.closing_credit = net_closing, 0.0
                else:
                    acc.closing_credit, acc.closing_debit = abs(net_closing), 0.0

        # Now whether Leaf or Group, pass the finalized values up to parent
        if acc.parent_account and acc.parent_account in accounts_by_name:
            parent = accounts_by_name[acc.parent_account]
            parent.opening_debit += acc.opening_debit
            parent.opening_credit += acc.opening_credit
            parent.debit += acc.debit
            parent.credit += acc.credit
            parent.closing_debit += acc.closing_debit
            parent.closing_credit += acc.closing_credit

    # 3. Format final tree structure
    data = []
    
    party_rows_by_parent = {}
    for pr in party_rows:
        party_rows_by_parent.setdefault(pr["parent_account"], []).append(pr)
    
    for acc in accounts:
        row = {
            "account": acc.name,
            "parent_account": acc.parent_account,
            "indent": acc.indent,
            "is_group_account": 1 if (acc.is_group or getattr(acc, "has_party_rows", False)) else 0,
            "currency": company_currency,
            "opening_debit": acc.opening_debit,
            "opening_credit": acc.opening_credit,
            "debit": acc.debit,
            "credit": acc.credit,
            "closing_debit": acc.closing_debit,
            "closing_credit": acc.closing_credit,
        }
        
        has_value = any(abs(row[k]) > 0.001 for k in ["opening_debit", "opening_credit", "debit", "credit", "closing_debit", "closing_credit"])
        
        if has_value or acc.is_group:
            data.append(row)
            
            # Insert party rows directly beneath their ledger
            if getattr(acc, "has_party_rows", False):
                # Sort party rows alphabetically by account name for neatness
                sorted_party_rows = sorted(party_rows_by_parent.get(acc.name, []), key=lambda x: x["account"])
                data.extend(sorted_party_rows)

    data = filter_empty_groups(data)
    
    total_row = get_total_row(data)
    data.extend([{}, total_row])
    
    return data

def get_accounts(company):
    accounts = frappe.db.sql("""
        SELECT name, parent_account, is_group, lft, rgt
        FROM `tabAccount`
        WHERE company = %s
        ORDER BY lft ASC
    """, company, as_dict=1)
    
    parent_children_map = {}
    for acc in accounts:
        parent_children_map.setdefault(acc.parent_account or None, []).append(acc)
        for k in ["opening_debit", "opening_credit", "debit", "credit", "closing_debit", "closing_credit", "indent"]:
            acc[k] = 0.0
            
    def set_indent(parent, level):
        for child in parent_children_map.get(parent, []):
            child.indent = level
            set_indent(child.name, level + 1)
            
    set_indent(None, 0)
    return accounts

def get_gl_entries(filters):
    return frappe.db.sql("""
        SELECT 
            account,
            IFNULL(party_type, '') as party_type,
            IFNULL(party, '') as party,
            SUM(CASE WHEN posting_date < %(from_date)s THEN debit ELSE 0 END) as opening_debit,
            SUM(CASE WHEN posting_date < %(from_date)s THEN credit ELSE 0 END) as opening_credit,
            SUM(CASE WHEN posting_date >= %(from_date)s AND posting_date <= %(to_date)s THEN debit ELSE 0 END) as debit,
            SUM(CASE WHEN posting_date >= %(from_date)s AND posting_date <= %(to_date)s THEN credit ELSE 0 END) as credit
        FROM `tabGL Entry`
        WHERE company = %(company)s AND is_cancelled = 0
        GROUP BY account, IFNULL(party_type, ''), IFNULL(party, '')
    """, filters, as_dict=1)

def filter_empty_groups(data):
    accounts_to_keep = set()
    parent_map = {d.get("account"): d.get("parent_account") for d in data}
    
    def keep_parents(account):
        parent = parent_map.get(account)
        if parent and parent not in accounts_to_keep:
            accounts_to_keep.add(parent)
            keep_parents(parent)
            
    for d in data:
        # Ignore total row and empty row
        if not d.get("account") or d.get("account") == "'Total'":
            continue
            
        has_val = any(abs(d.get(k, 0)) > 0.001 for k in ["opening_debit", "opening_credit", "debit", "credit", "closing_debit", "closing_credit"])
        if has_val:
            accounts_to_keep.add(d["account"])
            keep_parents(d["account"])
            
    return [d for d in data if d.get("account") in accounts_to_keep]

def get_total_row(data):
    # Determine the currency dynamically from the first valid row, or use nothing if empty
    currency = ""
    for d in data:
        if d.get("currency"):
            currency = d["currency"]
            break

    total_row = {
        "account": "'" + _("Total") + "'",
        "is_group_account": 0,
        "currency": currency,
        "opening_debit": 0.0, "opening_credit": 0.0,
        "debit": 0.0, "credit": 0.0,
        "closing_debit": 0.0, "closing_credit": 0.0
    }
    
    for d in data:
        if d.get("account") and not d.get("parent_account") and d.get("account") != "'Total'":
            for k in ["opening_debit", "opening_credit", "debit", "credit", "closing_debit", "closing_credit"]:
                total_row[k] += d.get(k, 0.0)
                
    return total_row
