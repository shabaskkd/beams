import frappe
frappe.init(site="erp.mediaonetv.com", sites_path="/home/prod/frappe-bench/sites")
frappe.connect()

if not frappe.db.exists("Report", "M1 Trial Balnce"):
    report = frappe.new_doc("Report")
    report.report_name = "M1 Trial Balnce"
    report.ref_doctype = "GL Entry"
    report.is_standard = "Yes"
    report.module = "Beams"
    report.report_type = "Script Report"
    report.insert()
    frappe.db.commit()
    print("Report 'M1 Trial Balnce' created successfully.")
else:
    print("Report 'M1 Trial Balnce' already exists.")
