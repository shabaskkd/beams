// Copyright (c) 2026, shabas and contributors
// For license information, please see license.txt

frappe.ui.form.on("Vehicle Hire Request", {
    posting_date(frm) {
        frm.call({ method: "validate_posting_date", doc: frm.doc });
    }
});
