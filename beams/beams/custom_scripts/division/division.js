frappe.ui.form.on('Division', {

    department(frm) {
        if (!frm.doc.department) return;

        frappe.call({
            method: "beams.beams.custom_scripts.division.division.get_department_cost_heads",
            args: {
                department: frm.doc.department
            },
            callback: function(r) {
                if (!r.message) return;

                let data = r.message;

                frm.set_value('company', data.company);

                frm.set_value('bata_cost_head', data.bata_cost_head);
                frm.set_value('fuel_cost_head', data.fuel_cost_head);
                frm.set_value('travel_cost_head', data.travel_cost_head);
                frm.set_value('repair_cost_head', data.repair_cost_head);

                trigger_all(frm);
            }
        });
    },

    refresh(frm) {
        if (frm.doc.department) {
            frm.trigger('department');
        }
    },

    bata_cost_head(frm) {
        fetch_account(frm, 'bata_cost_head', 'bata_account');
    },

    fuel_cost_head(frm) {
        fetch_account(frm, 'fuel_cost_head', 'fuel_account');
    },

    travel_cost_head(frm) {
        fetch_account(frm, 'travel_cost_head', 'travel_account');
    },

    repair_cost_head(frm) {
        fetch_account(frm, 'repair_cost_head', 'repair_account');
    }

});


function trigger_all(frm) {
    if (frm.doc.bata_cost_head)
        frm.trigger('bata_cost_head');

    if (frm.doc.fuel_cost_head)
        frm.trigger('fuel_cost_head');

    if (frm.doc.travel_cost_head)
        frm.trigger('travel_cost_head');

    if (frm.doc.repair_cost_head)
        frm.trigger('repair_cost_head');
}


function fetch_account(frm, cost_head_field, account_field) {

    if (!frm.doc[cost_head_field] || !frm.doc.company) return;

    frappe.call({
        method: "beams.beams.custom_scripts.department.department.get_default_account",
        args: {
            cost_head: frm.doc[cost_head_field],
            company: frm.doc.company
        },
        callback: function(r) {
            frm.set_value(account_field, r.message || null);
        }
    });
}
