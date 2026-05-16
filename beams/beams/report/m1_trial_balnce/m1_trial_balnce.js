// Copyright (c) 2026, Shabas Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

frappe.query_reports["M1 Trial Balnce"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        }
    ],
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (column.fieldname == "account") {
            let filters = frappe.query_report.get_values() || {};
            let company = encodeURIComponent(filters.company || "");
            let from_date = encodeURIComponent(filters.from_date || "");
            let to_date = encodeURIComponent(filters.to_date || "");

            if (data.is_party && data.party) {
                let ptype = encodeURIComponent(data.party_type || "");
                let party = encodeURIComponent(data.party || "");
                let link = `/app/query-report/General%20Ledger?company=${company}&party_type=${ptype}&party=${party}&from_date=${from_date}&to_date=${to_date}`;
                value = `<span style="margin-left: 20px;"><a href="${link}">${value}</a></span>`;
            } else if (!data.is_party && data.account && data.account !== "'Total'") {
                let acc = encodeURIComponent(data.account || "");
                let link = `/app/query-report/General%20Ledger?company=${company}&account=${acc}&from_date=${from_date}&to_date=${to_date}`;
                value = `<a href="${link}">${value}</a>`;
            }
        }
        return value;
    },
    tree: true,
    name_field: "account",
    parent_field: "parent_account",
    initial_depth: 3
};
