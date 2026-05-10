# Copyright (c) 2026, shabas and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_first_day, get_last_day, nowdate

from beams.beams.doctype.bureau_trip_sheet.bureau_trip_sheet import _get_supplier_payable_account
from collections import defaultdict
from frappe.utils import getdate

class MonthlyConsolidatedTripSheet(Document):
	def validate(self):
		self._validate_employee_bureau()
		self._prevent_edit_of_processed_rows()
		supplier_doc = frappe.get_doc("Supplier", self.supplier) if self.supplier else None
		is_special = supplier_doc.is_special_condition if supplier_doc else 0
		if not self.is_actual:
			if not is_special:
				self._set_batta_totals_from_details()
				self._set_total_distance_and_fuel_from_details()
			self._set_total_hours()
			self._set_extra_charges()
			self._set_final_rent()
		self._validate_and_prepare_fuel_card_deduction()

	def on_update(self):
		self._apply_fuel_card_deduction()

	def on_trash(self):
		self._restore_fuel_card_on_delete()

	def _month_name_to_number(self, month_name):
		months = [
			"January", "February", "March", "April", "May", "June",
			"July", "August", "September", "October", "November", "December",
		]
		if month_name in months:
			return months.index(month_name) + 1
		return None

	def _prevent_edit_of_processed_rows(self):
		'''Prevent editing of certain fields if the row was already processed (i.e. a Journal Entry was created for it).'''
		if not self.get_doc_before_save():
			return

		old_doc = self.get_doc_before_save()

		old_rows_map = {
			row.bureau_trip_sheet: row
			for row in old_doc.get("monthly_consolidated_trip_sheet_details")
		}

		for new_row in self.get("monthly_consolidated_trip_sheet_details"):

			old_row = old_rows_map.get(new_row.bureau_trip_sheet)

			if not old_row:
				continue

			if old_row.is_processed:
				fields = [
					"total_batta",
					"total_ot_batta",
					"amount_received_driver",
					"fuel_consumption_l",
					"distance_travelledkm"
				]

				for field in fields:
					if flt(new_row.get(field)) != flt(old_row.get(field)):
						frappe.throw(
							_("Row {0} is already processed and cannot be modified").format(new_row.idx)
						)

	def _set_batta_totals_from_details(self):
		"""Set total_batta, total_ot_batta, total_amount_received_driver; per-row and parent after-advance amounts."""
		total_batta = 0
		total_ot_batta = 0
		total_amount_received_driver = 0
		total_batta_after = 0
		total_ot_after = 0
		for row in self.get("monthly_consolidated_trip_sheet_details") or []:
			batta = flt(row.get("total_batta"))
			ot = flt(row.get("total_ot_batta"))
			advance = flt(row.get("amount_received_driver"))
			total_batta += batta
			total_ot_batta += ot
			total_amount_received_driver += advance
			# Advance applies to batta first, remainder to OT
			remaining_after_batta = max(0, advance - batta)
			batta_after = max(0, batta - advance)
			ot_after = max(0, ot - remaining_after_batta)
			row.total_batta_amount_after_advances = round(batta_after, 2)
			row.total_ot_amount_after_advances = round(ot_after, 2)
			total_batta_after += batta_after
			total_ot_after += ot_after
		self.total_batta = total_batta
		self.total_ot_batta = total_ot_batta
		self.total_amount_received_driver = total_amount_received_driver
		self.total_batta_amount_after_advances = round(total_batta_after, 2)
		self.total_ot_amount_after_advances = round(total_ot_after, 2)

	def _set_total_distance_and_fuel_from_details(self):
		"""Set total_distance_travelled, total_fuel_consumed and total_fuel_expense from child table rows."""
		total_distance = 0
		total_fuel = 0
		for row in self.get("monthly_consolidated_trip_sheet_details") or []:
			total_distance += flt(row.get("distance_travelledkm"))
			total_fuel += flt(row.get("fuel_consumption_l"))
		self.total_distance_travelled = total_distance
		self.total_fuel_consumed = total_fuel
		fuel_rate = flt(self.get("fuel_rate__litre"))
		self.total_fuel_expense = total_fuel * fuel_rate

	def _validate_and_prepare_fuel_card_deduction(self):
		"""Validate total_fuel_card_expense against bureau's fuel card limit; store old value for on_update."""
		expense = flt(self.get("total_fuel_card_expense"))
		supplier_doc = frappe.get_doc("Supplier", self.supplier) if self.supplier else None
		is_special = supplier_doc.is_special_condition if supplier_doc else 0
		if is_special:
			return
		if not self.bureau or expense <= 0:
			self._old_total_fuel_card_expense = 0
			return
		fuel_card_name = frappe.db.get_value("Bureau", self.bureau, "fuel_card")
		if not fuel_card_name:
			return
		old_expense = flt(
			frappe.db.get_value(self.doctype, self.name, "total_fuel_card_expense")
			if self.name else 0
		)
		self._old_total_fuel_card_expense = old_expense
		fuel_card = frappe.get_doc("Fuel Card", fuel_card_name)
		current_limit = flt(fuel_card.fuel_card_limit)
		# After we add back old deduction, available = current_limit + old_expense
		available = current_limit + old_expense
		if expense > available:
			frappe.throw(
				_("Total Fuel Card Expense ({0}) cannot exceed the bureau's Fuel Card available amount ({1}).").format(
					expense, available
				),
				title=_("Fuel Card Limit Exceeded"),
			)

	def _apply_fuel_card_deduction(self):
		"""Reduce the bureau's Fuel Card limit by total_fuel_card_expense (after adding back previous deduction)."""
		new_expense = flt(self.get("total_fuel_card_expense"))
		old_expense = getattr(self, "_old_total_fuel_card_expense", None)
		supplier_doc = frappe.get_doc("Supplier", self.supplier) if self.supplier else None
		is_special = supplier_doc.is_special_condition if supplier_doc else 0
		if is_special:
			return
		if old_expense is None and self.name:
			old_expense = flt(frappe.db.get_value(self.doctype, self.name, "total_fuel_card_expense"))
		if old_expense is None:
			old_expense = 0
		if not self.bureau:
			return
		fuel_card_name = frappe.db.get_value("Bureau", self.bureau, "fuel_card")
		if not fuel_card_name:
			return
		# No change
		if new_expense == old_expense:
			return
		fuel_card = frappe.get_doc("Fuel Card", fuel_card_name)
		current = flt(fuel_card.fuel_card_limit)
		# Add back what we had deducted before, then deduct new amount
		fuel_card.fuel_card_limit = current + old_expense - new_expense
		fuel_card.flags.ignore_permissions = True
		fuel_card.save(ignore_version=True)

	def _restore_fuel_card_on_delete(self):
		"""Restore total_fuel_card_expense to the bureau's Fuel Card when this doc is deleted."""
		expense = flt(self.get("total_fuel_card_expense"))
		if not self.bureau or expense <= 0:
			return
		fuel_card_name = frappe.db.get_value("Bureau", self.bureau, "fuel_card")
		if not fuel_card_name:
			return
		fuel_card = frappe.get_doc("Fuel Card", fuel_card_name)
		fuel_card.fuel_card_limit = flt(fuel_card.fuel_card_limit) + expense
		fuel_card.flags.ignore_permissions = True
		fuel_card.save(ignore_version=True)

	def _set_total_hours(self):

		day_map = defaultdict(list)

		for row in self.get("monthly_consolidated_trip_sheet_details") or []:

			if not row.starting_date_and_time:
				continue
			day = getdate(row.starting_date_and_time)

			hours = flt(row.get("total_hours"))
			if not hours:
				continue

			day_map[day].append(hours)
		total = 0

		for day, hours_list in day_map.items():

			if hours_list:
				max_hours = max(hours_list)
				total += max_hours

		self.total_hours = round(total, 2)

	def _set_extra_charges(self):
		# Get supplier settings
		supplier = self.supplier

		if not supplier:
			return

		supplier_doc = frappe.get_doc("Supplier", supplier)

		minimum_km = flt(supplier_doc.get("minimum_km"))
		extra_km_rate = flt(supplier_doc.get("extra_km_charge"))

		minimum_hours = flt(supplier_doc.get("minimum_working_hours"))
		extra_hour_rate = flt(supplier_doc.get("extra_time_charge"))

		# Extra KM Calculation
		total_distance = flt(self.total_distance_travelled)

		if total_distance > minimum_km:
			extra_km = total_distance - minimum_km
			self.total_extra_km_charge = round(extra_km * extra_km_rate, 2)
		else:
			self.total_extra_km_charge = 0

		# Extra Hours Calculation
		total_hours = flt(self.total_hours)

		if total_hours > minimum_hours:
			extra_hours = total_hours - minimum_hours
			self.total_extra_hours_charge = round(extra_hours * extra_hour_rate, 2)
		else:
			self.total_extra_hours_charge = 0

	def _set_final_rent(self):
		self.final_rent = round(
			flt(self.total_montly_rent)
			+ flt(self.total_ot_amount_after_advances)
			+ flt(self.total_extra_hours_charge)
			+ flt(self.total_extra_km_charge),
			2
		)
	def _validate_employee_bureau(self):
		employee = frappe.db.get_value(
			"Employee",
			{"user_id": frappe.session.user},
			["name", "bureau"],
			as_dict=True
		)

		employee_bureau = employee.get("bureau") if employee else None

		#  Case 1: Employee HAS bureau
		if employee_bureau:
			if not self.bureau:
				self.bureau = employee_bureau
			if self.bureau != employee_bureau:
				frappe.throw(_("You are not allowed to select another Bureau"))
		# Case 2: Employee has NO bureau → derive from supplier
		else:
			supplier_bureau = None
			if self.supplier:
				supplier_bureau = frappe.db.get_value("Supplier", self.supplier, "bureau")

			if supplier_bureau:
				self.bureau = supplier_bureau
		if self.supplier and self.bureau:
			supplier_bureau = frappe.db.get_value("Supplier", self.supplier, "bureau")

			if supplier_bureau and supplier_bureau != self.bureau:
				frappe.msgprint(_("Warning: Supplier belongs to a different Bureau"))

@frappe.whitelist()
def fetch_trip_sheets(supplier, bureau, month, year):
	if not all([supplier, bureau, month, year]):
		return []

	from frappe.utils import get_first_day, get_last_day, getdate, flt

	months = [
		"January", "February", "March", "April", "May", "June",
		"July", "August", "September", "October", "November", "December",
	]

	month_number = months.index(month) + 1 if month in months else None
	if not month_number:
		return []

	first_day = get_first_day(f"{year}-{month_number:02d}-01")
	last_day = get_last_day(first_day)

	docname = frappe.form_dict.get("docname")

	existing_trip_sheets = []
	if docname:
		doc = frappe.get_doc("Monthly Consolidated Trip Sheet", docname)
		existing_trip_sheets = [
			d.bureau_trip_sheet for d in doc.get("monthly_consolidated_trip_sheet_details")
		]

	processed_trip_sheets = frappe.db.get_all(
		"Monthly Consolidated Trip Sheet Details",
		filters={"is_processed": 1},
		pluck="bureau_trip_sheet"
	)

	exclude_trip_sheets = list(set((existing_trip_sheets or []) + (processed_trip_sheets or [])))

	trip_sheets = frappe.db.get_all(
		"Bureau Trip Sheet",
		filters={
			"supplier": supplier,
			"bureau": bureau,
			"docstatus": 1,
			"name": ["not in", exclude_trip_sheets or [""]]
		},
		fields=[
			"name", "departure_location", "destination_location",
			"initial_odometer_reading", "final_odometer_reading",
			"starting_date_and_time", "ending_date_and_time",
			"distance_travelledkm", "total_daily_batta", "total_ot_batta",
			"average_mileage_kmpl", "fuel_consumption_l","total_hours",
		],
	)

	rows = []
	for ts in trip_sheets:

		start_date = ts.get("starting_date_and_time") and getdate(ts["starting_date_and_time"])
		if not start_date or not (first_day <= start_date <= last_day):
			continue

		amount_received = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(amount), 0)
			FROM `tabBureau Trip Sheet Journal Entry`
			WHERE parent = %s
			""",
			(ts.get("name"),),
		)

		amount_received_driver = flt(amount_received[0][0]) if amount_received else 0

		rows.append({
			"departure_location": ts.get("departure_location") or "",
			"destination_location": ts.get("destination_location") or "",
			"initial_odometer_reading": ts.get("initial_odometer_reading"),
			"final_odometer_reading": ts.get("final_odometer_reading"),
			"starting_date_and_time": ts.get("starting_date_and_time"),
			"ending_date_and_time": ts.get("ending_date_and_time"),
			"distance_travelledkm": ts.get("distance_travelledkm"),
			"bureau_trip_sheet": ts.get("name"),
			"total_batta": ts.get("total_daily_batta"),
			"total_ot_batta": ts.get("total_ot_batta"),
			"amount_received_driver": amount_received_driver,
			"average_mileage_kmpl": ts.get("average_mileage_kmpl"),
			"fuel_consumption_l": ts.get("fuel_consumption_l"),
			"total_hours": ts.get("total_hours"),
		})

	return rows

@frappe.whitelist()
def create_journal_entry(monthly_consolidated_trip_sheet_name):
	"""
	Create a Journal Entry for Monthly Consolidated Trip Sheet settlement.
	Uses accounts from Beams Accounts Settings (Bureau Trip Sheet Settings).

	Debit (expenses): Batta and OT after advances (advance already netted in those amounts), plus Fuel Expense.
	Credit (already given): Total Fuel Card Expense (fuel log) only — do not post advance again.
	Balancing: Supplier payable (Batta after + OT after + Fuel Expense - Fuel Log).
	"""
	doc = frappe.get_doc("Monthly Consolidated Trip Sheet", monthly_consolidated_trip_sheet_name)
	supplier_doc = frappe.get_doc("Supplier", doc.supplier)
	is_special = supplier_doc.is_special_condition
	if is_special:
		frappe.throw("Journal Entry not allowed for Special Supplier")
	if doc.docstatus != 1:
		frappe.throw(_("Document must be submitted before creating Journal Entry"))
	if not doc.supplier:
		frappe.throw(_("Supplier is not set on Monthly Consolidated Trip Sheet."))
	# Ensure batta/OT after-advance and fuel totals match child rows before posting
	if not doc.is_actual:
		if not is_special:
			doc._set_batta_totals_from_details()
			doc._set_total_distance_and_fuel_from_details()
		doc._set_total_hours()
		doc._set_extra_charges()
		doc._set_final_rent()
	unprocessed_rows = [
	row for row in doc.get("monthly_consolidated_trip_sheet_details") or []
	if not row.is_processed
	]

	if not unprocessed_rows:
		frappe.throw(_("All trip details are already processed."))

	company = None
	cost_center = None
	if doc.bureau:
		bureau_doc = frappe.db.get_value(
			"Bureau", doc.bureau, ["company", "cost_center"], as_dict=True
		)
		if bureau_doc:
			company = bureau_doc.get("company")
			cost_center = bureau_doc.get("cost_center")
	if not company:
		company = frappe.defaults.get_default("company")
	if not company:
		frappe.throw(_("Company could not be determined. Set Bureau or default Company."))

	settings = frappe.get_single("Beams Accounts Settings")
	batta_account = settings.get("batta_expense_item")
	fuel_expense_account = settings.get("fuel_expense_item")
	ot_account = settings.get("batta_ot_expense_item")
	fuel_card_account = settings.get("fuel_card_account")

	supplier_payable_account = _get_supplier_payable_account(doc.supplier, company)
	if not supplier_payable_account:
		frappe.throw(
			_("No default payable account for Supplier {0} and Company {1}. Set it in Supplier or Company.").format(
				doc.supplier, company
			)
		)
	if doc.is_actual:
		total_batta_je = flt(doc.total_batta_amount_after_advances)
		total_ot_je = flt(doc.total_ot_amount_after_advances)
		total_fuel_expense = flt(doc.total_fuel_expense) if not is_special else 0
	else:

		total_batta_je = 0
		total_ot_je = 0
		total_fuel = 0

		for row in unprocessed_rows:
			total_batta_je += flt(row.total_batta_amount_after_advances)
			total_ot_je += flt(row.total_ot_amount_after_advances)
			if not is_special:
				total_fuel += flt(row.fuel_consumption_l)

		fuel_rate = flt(doc.fuel_rate__litre)
		total_fuel_expense = round(total_fuel * fuel_rate, 2) if not is_special else 0

	total_fuel_log = round(flt(doc.total_fuel_card_expense), 2)

	total_batta_je = round(total_batta_je, 2)
	total_ot_je = round(total_ot_je, 2)

	supplier_amount = round(total_batta_je + total_ot_je + total_fuel_expense - total_fuel_log, 2)

	accounts = []
	# Debits — expense accounts
	if batta_account and total_batta_je:
		accounts.append({
			"account": batta_account,
			"debit_in_account_currency": total_batta_je,
			"credit_in_account_currency": 0,
		})
	if ot_account and total_ot_je:
		accounts.append({
			"account": ot_account,
			"debit_in_account_currency": total_ot_je,
			"credit_in_account_currency": 0,
		})
	if fuel_expense_account and total_fuel_expense:
		accounts.append({
			"account": fuel_expense_account,
			"debit_in_account_currency": total_fuel_expense,
			"credit_in_account_currency": 0,
		})
	# Credits — fuel card / fuel log only (advance is already reflected in batta_after / ot_after)
	if fuel_card_account and total_fuel_log:
		accounts.append({
			"account": fuel_card_account,
			"debit_in_account_currency": 0,
			"credit_in_account_currency": total_fuel_log,
		})
	# Supplier balancing: credit when company owes supplier, debit when recovering
	if supplier_payable_account and supplier_amount != 0:
		accounts.append({
			"account": supplier_payable_account,
			"party_type": "Supplier",
			"party": doc.supplier,
			"debit_in_account_currency": abs(supplier_amount) if supplier_amount < 0 else 0,
			"credit_in_account_currency": supplier_amount if supplier_amount > 0 else 0,
		})

	if not accounts:
		frappe.throw(_("No amounts to post. Set Batta, OT, Fuel Expense or Fuel Card, and ensure accounts are set in Beams Accounts Settings > Bureau Trip Sheet Settings."))

	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.posting_date = nowdate()
	je.company = company
	je.cost_center = cost_center or None
	je.user_remark = _("Settlement for Monthly Consolidated Trip Sheet {0} – {1}").format(doc.name, doc.supplier)

	for row in accounts:
		je.append("accounts", row)

	# requires party_type and party for Receivable/Payable accounts
	for d in je.get("accounts"):
		account_type = frappe.get_cached_value("Account", d.account, "account_type")
		if account_type in ("Receivable", "Payable") and not (d.party_type and d.party):
			d.party_type = "Supplier"
			d.party = doc.supplier

	je.flags.ignore_permissions = True
	je.insert()

	for row in unprocessed_rows:
		frappe.db.set_value(
			row.doctype,
			row.name,
			{
				"is_processed": 1,
				"processed_in_jv": je.name
			}
		)

	return je.name
@frappe.whitelist()
def get_employee_bureau():
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, ["name", "bureau"], as_dict=True)

    if not employee:
        return {}

    return {
        "employee": employee.name,
        "bureau": employee.bureau
    }
@frappe.whitelist()
def create_purchase_invoice(docname):
    doc = frappe.get_doc("Monthly Consolidated Trip Sheet", docname)

    supplier_doc = frappe.get_doc("Supplier", doc.supplier)
    is_special = supplier_doc.is_special_condition
    if doc.docstatus != 1:
       frappe.throw("Submit the document before creating Purchase Invoice")
    # Prevent duplicate
    if doc.get("purchase_invoice"):
        return doc.purchase_invoice

    # Ensure latest calculation
    doc._set_total_hours()
    doc._set_extra_charges()
    doc._set_final_rent()

    # Get Item from Settings
    settings = frappe.get_single("Beams Accounts Settings")
    item_code = settings.get("rent_expense_item")

    if not item_code:
        frappe.throw("Rent Expense Item not set in Beams Accounts Settings")

    #  Decide Amount
    if is_special:
        amount = flt(doc.final_rent)
    else:
        amount = flt(doc.total_montly_rent)

    if amount <= 0:
        frappe.throw("Amount is zero")

    #  Company (Fixed as per your requirement)
    company = "Madhyamam Broadcasting Limited"

    #  Create PI
    pi = frappe.new_doc("Purchase Invoice")
    pi.supplier = doc.supplier
    pi.company = company
    pi.posting_date = nowdate()

    pi.append("items", {
        "item_code": item_code,
        "qty": 1,
        "rate": amount
    })

    pi.insert(ignore_permissions=True)
    pi.submit()

    # Link back
    doc.db_set("purchase_invoice", pi.name)

    return pi.name
