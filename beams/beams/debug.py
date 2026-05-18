import frappe

def execute():
    filters = frappe._dict({
        "company": "Madhyamam Broadcasting Limited",
        "from_date": "2021-01-01",
        "to_date": "2026-05-18",
        "outstanding_type": "Payable",
        "party_type": "Supplier"
    })

    print("=== Testing get_payable_supplier_data ===")
    from beams.beams.report.custom_outstanding_report.custom_outstanding_report import (
        get_payable_supplier_data, get_columns, get_data
    )

    try:
        rows = get_payable_supplier_data(filters)
        print(f"Total rows returned: {len(rows)}")
        for r in rows[:5]:
            print(r)
    except Exception as e:
        print(f"ERROR in get_payable_supplier_data: {e}")
        import traceback
        traceback.print_exc()

    print("\n=== Testing full get_data ===")
    try:
        result = get_data(filters)
        print(f"Total rows (incl header/total): {len(result)}")
        for r in result[:5]:
            print(r)
    except Exception as e:
        print(f"ERROR in get_data: {e}")
        import traceback
        traceback.print_exc()

    print("\n=== Testing get_columns ===")
    try:
        cols = get_columns(filters)
        print(f"Columns: {[c['fieldname'] for c in cols]}")
    except Exception as e:
        print(f"ERROR in get_columns: {e}")
