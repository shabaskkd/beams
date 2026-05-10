frappe.ui.form.on('Department', {

    onload: function(frm) {
        if (!frm.doc.name) return;

        frappe.call({
            method: 'beams.beams.custom_scripts.department.department.get_hod_users',
            args: {
                department_name: frm.doc.name
            },
            callback: function(r) {
                if (r.message) {
                    frm.set_query('head_of_department', function() {
                        return {
                            filters: {
                                department: frm.doc.name,
                                user_id: ['in', r.message || []]
                            }
                        };
                    });
                }
            }
        });
    },

    refresh(frm) {
        trigger_all(frm);
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
    },

    company(frm) {
        trigger_all(frm);
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
            if (r.message) {
                frm.set_value(account_field, r.message);
            } else {
                frm.set_value(account_field, null);
            }
        }
    });
}
