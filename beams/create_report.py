import frappe

def execute():
    report_name = "Custom Outstanding Report"
    if not frappe.db.exists("Report", report_name):
        doc = frappe.get_doc({
            "doctype": "Report",
            "report_name": report_name,
            "ref_doctype": "GL Entry",
            "report_type": "Script Report",
            "is_standard": "Yes",
            "module": "Beams"
        })
        doc.insert()
        frappe.db.commit()
        print(f"Created report: {report_name}")
    else:
        print(f"Report {report_name} already exists.")
