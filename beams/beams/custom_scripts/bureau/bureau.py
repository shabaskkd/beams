import frappe

@frappe.whitelist()
def get_department_cost_heads(department):
    if not department:
        return {}

    doc = frappe.get_doc("Department", department)

    return {
        "bata_cost_head": doc.get("bata_cost_head"),
        "fuel_cost_head": doc.get("fuel_cost_head"),
        "travel_cost_head": doc.get("travel_cost_head"),
        "repair_cost_head": doc.get("repair_cost_head"),
        "company": doc.get("company")
    }
