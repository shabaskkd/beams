import frappe
frappe.init(site="erp.mediaonetv.com", sites_path="/home/prod/frappe-bench/sites")
frappe.connect()

from beams.beams.report.custom_trial_balance.custom_trial_balance import execute

company = frappe.db.get_all("Company")[0].name
filters = frappe._dict({
    "company": company,
    "from_date": "2024-04-01",
    "to_date": "2025-03-31"
})

try:
    cols, data = execute(filters)
    groups = [d for d in data if d.get("is_group_account")]
    print(f"Total rows: {len(data)}")
    print(f"Total groups: {len(groups)}")
    if groups:
        print("First group:", groups[0])
except Exception as e:
    import traceback
    print("Error:", traceback.format_exc())

