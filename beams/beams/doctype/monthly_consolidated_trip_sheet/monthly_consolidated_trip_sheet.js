// Copyright (c) 2026, shabas and contributors
// For license information, please see license.txt


frappe.ui.form.on('Monthly Consolidated Trip Sheet', {
    onload(frm) {
        set_yeat(frm);
        set_supplier_filter(frm);
        if (frappe.user.has_role("Bureau User")) {
              frm.set_df_property("is_actual", "hidden", 1);
        }
        if (frm.doc.supplier) {
              frappe.db.get_value("Supplier", frm.doc.supplier, "is_special_condition", function(r) {
                  if (r) {
                      frm.doc._is_special = r.is_special_condition || 0;
                      apply_special_condition_ui(frm, r.is_special_condition);
                  }
              });
        }
        frappe.call({
              method: "beams.beams.doctype.monthly_consolidated_trip_sheet.monthly_consolidated_trip_sheet.get_employee_bureau",
              callback: function(r) {
                   if (r.message && r.message.bureau) {
                       if (!frm.doc.bureau) {
                            frm.set_value("bureau", r.message.bureau);
                       }
                       apply_supplier_filter_by_bureau(frm, r.message.bureau);
                   }
              }
        });
    },
    refresh(frm) {
        frm.clear_custom_buttons();
        toggle_actual_fields(frm, frm.doc.is_actual);
        if (frm.doc.docstatus === 1) {
             if (frm.doc._is_special === 1 || frm.doc._is_special === true) {
                 add_create_purchase_invoice_button(frm);
             } else {
                 add_create_journal_entry_button(frm);
                 add_create_purchase_invoice_button(frm);
             }
        }
        if (frappe.user.has_role("Bureau User")) {
             frm.set_df_property("is_actual", "hidden", 1);
        }
        if (frm.doc._is_special !== undefined) {
             apply_special_condition_ui(frm, frm.doc._is_special);
        }
        if (!frm.doc.is_actual && !frm.doc._is_special) {
             calculate_batta_totals(frm);
             calculate_fuel_expense(frm);
        }
    },
    is_actual(frm) {
	toggle_actual_fields(frm, frm.doc.is_actual);
	if (!frm.doc.is_actual && !frm.doc._is_special) {
		calculate_batta_totals(frm);
		calculate_fuel_expense(frm);
	}
    },
    fetch_trip_sheets_btn: function(frm) {
        run_fetch_trip_sheets(frm);
    },
    fuel_rate__litre: function(frm) {
      if (!frm.doc.is_actual && !frm.doc._is_special) {
        calculate_fuel_expense(frm);
      }
    },
    monthly_consolidated_trip_sheet_details_on_form_rendered: function(frm, cdt, cdn) {
      if (!frm.doc.is_actual && !frm.doc._is_special) {
        calculate_batta_totals(frm);
        calculate_fuel_expense(frm);
      }
    },
    bureau(frm) {
      set_supplier_filter(frm);
    },
    supplier(frm) {
     if (!frm.doc.supplier) return;
       frappe.db.get_value("Supplier", frm.doc.supplier, ["bureau", "is_special_condition"], function(r) {
        if (r) {
           frm.doc._is_special = r.is_special_condition;
           if (r.bureau && !frm.doc.bureau) {
                frm.set_value("bureau", r.bureau);
           }
           apply_special_condition_ui(frm, r.is_special_condition);
       }
     });
   }
});

// Set default year to current year on new document creation
function set_yeat(frm) {
    if (frm.is_new()) {
        frm.set_value("year", frappe.datetime.get_today().split("-")[0]);
    }
}

// Filter supplier field to show only transporters
function set_supplier_filter(frm) {
    frm.set_query("supplier", function() {
         let filters = {
             is_transporter: 1
         };
         if (frm.doc.bureau) {
             filters.bureau = frm.doc.bureau;
         }
         return { filters };
     });
}

// Fetch Bureau Trip Sheets (used by the Fetch Trip Sheets button below Month field)
function run_fetch_trip_sheets(frm) {
    if (!frm.doc.supplier || !frm.doc.bureau || !frm.doc.month || !frm.doc.year) {
        frappe.msgprint(__("Please set Supplier, Bureau, Month and Year first."));
        return;
    }

    frappe.call({
        method: "beams.beams.doctype.monthly_consolidated_trip_sheet.monthly_consolidated_trip_sheet.fetch_trip_sheets",
        args: {
            supplier: frm.doc.supplier,
            bureau: frm.doc.bureau,
            month: frm.doc.month,
            year: frm.doc.year
        },
        callback: function(r) {
            if (r.message && r.message.length) {

                let existing = (frm.doc.monthly_consolidated_trip_sheet_details || [])
                    .map(d => d.bureau_trip_sheet);

                let added_count = 0;

                (r.message || []).forEach(function(row) {
                    if (!existing.includes(row.bureau_trip_sheet)) {

                        let child = frm.add_child("monthly_consolidated_trip_sheet_details");

                        Object.assign(child, row);
                        child.is_processed = 0;

                        added_count++;
                    }
                });

                frm.refresh_field("monthly_consolidated_trip_sheet_details");

		if (!frm.doc.is_actual && !frm.doc._is_special) {
	                calculate_batta_totals(frm);
               		calculate_fuel_expense(frm);
		}
                frappe.show_alert({
                    message: __("Added {0} new trip sheet(s).", [added_count]),
                    indicator: "green"
                });

            } else {
                frappe.msgprint(__("No new trip sheets found."));
            }
        }
    });
}

// Create Journal Entry: debits batta/OT after advances + fuel expense; credit fuel log only (advance netted in batta/OT)
function add_create_journal_entry_button(frm) {
        if (frm.doc.docstatus !== 1) {
            return;
        }
        let has_unprocessed = (frm.doc.monthly_consolidated_trip_sheet_details || [])
            .some(row => !row.is_processed);
        if (!has_unprocessed) {
            return;
        }
        frm.add_custom_button(__("Create JV"), function() {
            frappe.call({
                method: "beams.beams.doctype.monthly_consolidated_trip_sheet.monthly_consolidated_trip_sheet.create_journal_entry",
                args: { monthly_consolidated_trip_sheet_name: frm.doc.name },
                callback: function(r) {
                    if (r.message) {
                        frappe.set_route("Form", "Journal Entry", r.message);
			frm.reload_doc();
                    }
                }
            });
        });
}

// Sum totals; per row: deduct amount_received_driver from batta first, then from OT
function calculate_batta_totals(frm) {
    var total_batta = 0;
    var total_ot_batta = 0;
    var total_amount_received_driver = 0;
    var total_batta_after = 0;
    var total_ot_after = 0;
    (frm.doc.monthly_consolidated_trip_sheet_details || []).forEach(function(row) {
        var batta = flt(row.total_batta);
        var ot = flt(row.total_ot_batta);
        var advance = flt(row.amount_received_driver);
        total_batta += batta;
        total_ot_batta += ot;
        total_amount_received_driver += advance;
        var remaining_after_batta = Math.max(0, advance - batta);
        var batta_after = Math.max(0, batta - advance);
        var ot_after = Math.max(0, ot - remaining_after_batta);
        frappe.model.set_value(
            row.doctype,
            row.name,
            "total_batta_amount_after_advances",
            batta_after
        );
        frappe.model.set_value(
            row.doctype,
            row.name,
            "total_ot_amount_after_advances",
            ot_after
        );
        total_batta_after += batta_after;
        total_ot_after += ot_after;
    });
    frm.set_value("total_batta", total_batta);
    frm.set_value("total_ot_batta", total_ot_batta);
    frm.set_value("total_amount_received_driver", total_amount_received_driver);
    frm.set_value("total_batta_amount_after_advances", total_batta_after);
    frm.set_value("total_ot_amount_after_advances", total_ot_after);
    frm.refresh_field("total_batta");
    frm.refresh_field("total_ot_batta");
    frm.refresh_field("total_amount_received_driver");
    frm.refresh_field("total_batta_amount_after_advances");
    frm.refresh_field("total_ot_amount_after_advances");
}

// Calculate fuel expense of monthly_consolidated_trip_sheet_details
function calculate_fuel_expense(frm) {

    let fuel_rate__litre = frm.doc.fuel_rate__litre || 0;
    let total_fuel = 0;
    let total_distance_travelledkm = 0;
    let avg_mileage = 0;

    (frm.doc.monthly_consolidated_trip_sheet_details || []).forEach(row => {
        total_fuel += row.fuel_consumption_l || 0;
        total_distance_travelledkm += row.distance_travelledkm || 0;
        avg_mileage = row.average_mileage_kmpl;
    });

    frm.set_value("total_fuel_consumed", total_fuel);
    frm.set_value("total_distance_travelled", total_distance_travelledkm);

    let total_expense = fuel_rate__litre * total_fuel;

    frm.set_value("total_fuel_expense", total_expense);
    frm.set_value("avg_mileage", avg_mileage)

    frm.refresh_field("total_distance_travelled");
    frm.refresh_field("total_fuel_consumed");
    frm.refresh_field("total_fuel_expense");
    frm.refresh_field("avg_mileage");
}
function toggle_actual_fields(frm, enable) {

    let fields = [
        "total_extra_hours_charge",
        "total_fuel_expense",
        "total_extra_km_charge",
        "total_batta_amount_after_advances",
        "total_ot_amount_after_advances",
        "final_rent",
        "total_amount_received_driver"
    ];

    fields.forEach(field => {
        frm.set_df_property(field, "read_only", enable ? 0 : 1);
    });

    frm.refresh_fields(fields);
}
function apply_supplier_filter_by_bureau(frm, bureau) {
    frm.set_query("supplier", function() {
        return {
            filters: {
                is_transporter: 1,
                bureau: bureau
            }
        };
    });
}
function apply_special_condition_ui(frm, is_special) {

    let show_fields = [
        "total_hours",
        "total_extra_hours_charge",
        "total_extra_km_charge",
        "final_rent"
    ];

    let hide_fields = [
        "avg_mileage",
        "fuel_rate__litre",
        "total_fuel_expense",
        "total_fuel_consumed",
        "total_fuel_card_expense",
        "total_batta",
        "total_batta_amount_after_advances"
    ];

    let normal_hide = [
        "total_hours",
        "total_extra_hours_charge",
        "total_extra_km_charge",
        "final_rent"
    ];

    if (is_special) {
        // Show special fields
        show_fields.forEach(f => frm.set_df_property(f, "hidden", 0));

        // Hide normal fuel/batta fields
        hide_fields.forEach(f => frm.set_df_property(f, "hidden", 1));

    } else {
        // Hide special fields
        normal_hide.forEach(f => frm.set_df_property(f, "hidden", 1));

        // Show normal fields
        hide_fields.forEach(f => frm.set_df_property(f, "hidden", 0));
    }

    frm.refresh_fields();
}
function add_create_purchase_invoice_button(frm) {

    if (frm.doc.purchase_invoice) {
	       frm.add_custom_button(
                   __("View Purchase Invoice"),
                   function() {
                        frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice);
                   },
                   __("View")
                );
                return;
     }

    frm.add_custom_button(__("Create Purchase Invoice"), function() {

        frappe.call({
            method: "beams.beams.doctype.monthly_consolidated_trip_sheet.monthly_consolidated_trip_sheet.create_purchase_invoice",
            args: {
                docname: frm.doc.name
            },
            callback: function(r) {
                if (r.message) {
                    frappe.set_route("Form", "Purchase Invoice", r.message);
                    frm.reload_doc();
                }
            }
        });

    }, __("Create"));
}
