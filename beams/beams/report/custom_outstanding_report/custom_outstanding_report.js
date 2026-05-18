frappe.query_reports["Custom Outstanding Report"] = {
	"filters": [
		// ── Core filters (always visible) ─────────────────────────────────────
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company") || "Madhyamam Broadcasting Limited",
			"reqd": 1
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"reqd": 1,
			"default": "2000-01-01"   // overwritten in onload with actual first GL entry date
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "outstanding_type",
			"label": __("Outstanding Type"),
			"fieldtype": "Select",
			"options": "Receivable\nPayable",
			"default": "Receivable",
			"reqd": 1,
			"on_change": function () {
				let out_type = frappe.query_report.get_filter_value("outstanding_type");
				let ptf = frappe.query_report.get_filter("party_type");
				if (ptf) {
					if (out_type === "Receivable") {
						ptf.df.options = "Customer\nEmployee";
						frappe.query_report.set_filter_value("party_type", "Customer");
					} else {
						ptf.df.options = "Supplier\nEmployee";
						frappe.query_report.set_filter_value("party_type", "Supplier");
					}
					ptf.refresh();
				}
				_clear_mode_filters();
				_toggle_mode_filters();
				setTimeout(() => frappe.query_report.refresh(), 400);
			}
		},
		{
			"fieldname": "party_type",
			"label": __("Party Type"),
			"fieldtype": "Select",
			"options": "Customer\nEmployee",
			"default": "Customer",
			"reqd": 1,
			"on_change": function () {
				_clear_mode_filters();
				_toggle_mode_filters();
				setTimeout(() => frappe.query_report.refresh(), 400);
			}
		},

		// ── Receivable + Customer filters ──────────────────────────────────────
		{
			"fieldname": "agency",
			"label": __("Agency"),
			"fieldtype": "Link",
			"options": "Customer",
			"hidden": 0,
			"on_change": () => setTimeout(() => frappe.query_report.refresh(), 300)
		},
		{
			"fieldname": "client",
			"label": __("Client"),
			"fieldtype": "Link",
			"options": "Customer",
			"hidden": 0,
			"on_change": () => setTimeout(() => frappe.query_report.refresh(), 300)
		},
		{
			"fieldname": "executive",
			"label": __("Executive"),
			"fieldtype": "Link",
			"options": "Employee",
			"hidden": 0,
			"on_change": () => setTimeout(() => frappe.query_report.refresh(), 300)
		},
		{
			"fieldname": "item_filter",
			"label": __("Item"),
			"fieldtype": "Link",
			"options": "Item",
			"hidden": 0,
			"on_change": () => setTimeout(() => frappe.query_report.refresh(), 300)
		},
		{
			"fieldname": "group_filter",
			"label": __("Group"),
			"fieldtype": "Link",
			"options": "Account",
			"hidden": 0,
			"on_change": () => setTimeout(() => frappe.query_report.refresh(), 300)
		},

		// ── Payable + Supplier filters ─────────────────────────────────────────
		{
			"fieldname": "supplier_filter",
			"label": __("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"hidden": 1,
			"on_change": () => setTimeout(() => frappe.query_report.refresh(), 300)
		},
		{
			"fieldname": "s_item_filter",
			"label": __("Item"),
			"fieldtype": "Link",
			"options": "Item",
			"hidden": 1,
			"on_change": () => setTimeout(() => frappe.query_report.refresh(), 300)
		},
		{
			"fieldname": "s_group_filter",
			"label": __("Group"),
			"fieldtype": "Link",
			"options": "Account",
			"hidden": 1,
			"on_change": () => setTimeout(() => frappe.query_report.refresh(), 300)
		},

		// ── Employee filters (shared for Receivable+Employee & Payable+Employee) ─
		{
			"fieldname": "emp_filter",
			"label": __("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"hidden": 1,
			"on_change": () => setTimeout(() => frappe.query_report.refresh(), 300)
		},
		{
			"fieldname": "emp_group_filter",
			"label": __("Group"),
			"fieldtype": "Link",
			"options": "Account",
			"hidden": 1,
			"on_change": () => setTimeout(() => frappe.query_report.refresh(), 300)
		}
	],

	"onload": function (report) {
		_toggle_mode_filters();

		let company = frappe.query_report.get_filter_value("company") || "Madhyamam Broadcasting Limited";
		if (company) {
			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "GL Entry",
					filters: { "company": company },
					fields: ["posting_date"],
					order_by: "posting_date asc",
					limit_page_length: 1
				},
				callback: function (r) {
					let date_to_set = (r.message && r.message.length > 0)
						? r.message[0].posting_date
						: frappe.datetime.add_months(frappe.datetime.get_today(), -24);
					frappe.query_report.set_filter_value("from_date", date_to_set);
					frappe.query_report.refresh();
				}
			});
		}
	},

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.is_header) {
			value = $(`<span>${value || ""}</span>`).css({ "font-weight": "bold", "color": "#2d6a9f" }).prop("outerHTML");
		}
		if (data && data.is_total) {
			value = $(`<span>${value || ""}</span>`).css({ "font-weight": "bold", "color": "#1a202c" }).prop("outerHTML");
		}
		return value;
	}
};

// ── Filter groups per mode ──────────────────────────────────────────────────
const _FILTER_GROUPS = {
	"Receivable_Customer": ["agency", "client", "executive", "item_filter", "group_filter"],
	"Payable_Supplier":    ["supplier_filter", "s_item_filter", "s_group_filter"],
	"Employee":            ["emp_filter", "emp_group_filter"]
};

function _get_active_group_key() {
	let out = frappe.query_report.get_filter_value("outstanding_type") || "Receivable";
	let pt  = frappe.query_report.get_filter_value("party_type") || "Customer";
	if (pt === "Employee") return "Employee";
	return `${out}_${pt}`;
}

/** Clear all mode-specific filter values (not dates/company). */
function _clear_mode_filters() {
	let all = ["agency","client","executive","item_filter","group_filter",
	           "supplier_filter","s_item_filter","s_group_filter",
	           "emp_filter","emp_group_filter"];
	all.forEach(fn => {
		try { frappe.query_report.set_filter_value(fn, ""); } catch(e) {}
	});
}

/** Show only the filter group relevant to the current mode, hide all others. */
function _toggle_mode_filters() {
	let active_key = _get_active_group_key();
	let active_filters = _FILTER_GROUPS[active_key] || [];

	// Build set of all registered filter fieldnames
	let all_mode_filters = Object.values(_FILTER_GROUPS).flat();

	all_mode_filters.forEach(fn => {
		let f = frappe.query_report.get_filter(fn);
		if (!f) return;
		let should_show = active_filters.includes(fn);
		f.df.hidden = should_show ? 0 : 1;
		f.refresh();
	});
}
