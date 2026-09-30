# Public holiday working.
#
# Public holidays stay paid holidays for everyone (nobody is marked absent). HR assigns
# shifts to the people who must work; when such an employee's Attendance is submitted as
# Present / Half Day on a public holiday of their holiday list, a "Public Holiday Work"
# row records who worked, and the extra day's pay is created as an Additional Salary
# (CTC / 26, half for a Half Day). Cancelling the Attendance undoes both.
#
# Wired in hooks.py doc_events -> Attendance on_submit / on_cancel. Never raises: a
# failure is logged so that attendance marking (incl. the auto-attendance job) goes on.

import frappe
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from frappe.utils import flt, strip_html

DOCTYPE = "Public Holiday Work"
PH_COMPONENTS = ("Public Holiday Pay", "Factory Public Holiday Pay")
DAYS_PER_MONTH = 26


def on_attendance_submit(doc, method=None):
	try:
		record_holiday_work(doc)
	except Exception:
		frappe.log_error(title=f"Public Holiday Work failed for {doc.name}")


def on_attendance_cancel(doc, method=None):
	try:
		undo_holiday_work(doc)
	except Exception:
		frappe.log_error(title=f"Public Holiday Work cancel failed for {doc.name}")


def record_holiday_work(att):
	if att.status not in ("Present", "Half Day"):
		return

	holiday_list = get_holiday_list_for_employee(att.employee, raise_exception=False, as_on=att.attendance_date)
	if not holiday_list:
		return
	holiday = frappe.db.get_value(
		"Holiday",
		{"parent": holiday_list, "holiday_date": att.attendance_date, "weekly_off": 0},
		"description",
	)
	if holiday is None:
		return
	if frappe.db.exists(
		DOCTYPE, {"employee": att.employee, "holiday_date": att.attendance_date, "status": ["!=", "Cancelled"]}
	):
		return

	notes = []
	rows = frappe.db.sql(
		"""select name, shift_type from `tabShift Assignment`
		where docstatus = 1 and status = 'Active' and employee = %(employee)s
			and start_date <= %(date)s and (end_date is null or end_date >= %(date)s)
		order by start_date desc, creation desc limit 1""",
		{"employee": att.employee, "date": att.attendance_date},
		as_dict=True,
	)
	shift_assignment = rows[0] if rows else None
	shift = att.shift or (shift_assignment.shift_type if shift_assignment else None)
	if not shift_assignment:
		notes.append("No shift assignment found for the holiday")

	ctc, component = get_rate_basis(att, notes)
	day_rate = flt(ctc / DAYS_PER_MONTH, 2)
	pay = flt(day_rate * (0.5 if att.status == "Half Day" else 1), 2)

	status, additional_salary = "Recorded", None
	existing = frappe.db.get_value(
		"Additional Salary",
		{
			"employee": att.employee,
			"payroll_date": att.attendance_date,
			"docstatus": 1,
			"salary_component": ["in", PH_COMPONENTS],
		},
		"name",
	)
	if existing:
		status, additional_salary = "Pay Exists (Manual)", existing
		notes.append("Holiday pay already entered manually - not created again")
	elif not pay:
		notes.append("No CTC / salary structure - holiday pay not created")
	else:
		frappe.db.savepoint("public_holiday_pay")
		try:
			additional_salary = create_holiday_pay(att, component, pay)
			status = "Pay Created"
		except Exception as e:
			frappe.db.rollback(save_point="public_holiday_pay")
			notes.append(f"Holiday pay NOT created: {str(e)[:300]}")

	frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"employee": att.employee,
			"holiday_date": att.attendance_date,
			"holiday_name": strip_html(holiday or "").strip(),
			"holiday_list": holiday_list,
			"shift_type": shift,
			"shift_assignment": shift_assignment.name if shift_assignment else None,
			"attendance": att.name,
			"attendance_status": att.status,
			"in_time": att.in_time,
			"out_time": att.out_time,
			"working_hours": flt(att.working_hours, 2),
			"ctc": ctc,
			"day_rate": day_rate,
			"holiday_pay": pay,
			"salary_component": component,
			"additional_salary": additional_salary,
			"status": status,
			"remarks": "\n".join(notes),
		}
	).insert(ignore_permissions=True)


def get_rate_basis(att, notes):
	"""Monthly CTC and the holiday-pay component (Factory structure -> Factory component)."""
	ctc = flt(frappe.db.get_value("Employee", att.employee, "ctc"))
	ssa = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": att.employee, "docstatus": 1, "from_date": ["<=", att.attendance_date]},
		["salary_structure", "base"],
		as_dict=True,
		order_by="from_date desc",
	)
	if not ctc and ssa:
		ctc = flt(ssa.base)
		notes.append("Employee CTC blank - used salary structure base")
	structure = (ssa.salary_structure if ssa else "") or ""
	component = "Factory Public Holiday Pay" if "FACTORY" in structure.upper() else "Public Holiday Pay"
	return ctc, component


def create_holiday_pay(att, component, amount):
	doc = frappe.get_doc(
		{
			"doctype": "Additional Salary",
			"employee": att.employee,
			"company": att.company,
			"salary_component": component,
			"amount": amount,
			"payroll_date": att.attendance_date,
			"overwrite_salary_structure_amount": 0,
		}
	)
	if doc.meta.has_field("custom_ph_hours"):
		doc.custom_ph_hours = flt(att.working_hours, 2)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def undo_holiday_work(att):
	for row in frappe.get_all(
		DOCTYPE,
		filters={"attendance": att.name, "status": ["!=", "Cancelled"]},
		fields=["name", "status", "additional_salary", "remarks"],
	):
		note = f"Attendance {att.name} cancelled"
		if row.status == "Pay Created" and row.additional_salary:
			in_slip = frappe.db.sql(
				"""select sd.parent from `tabSalary Detail` sd
				join `tabSalary Slip` ss on ss.name = sd.parent
				where sd.additional_salary = %s and ss.docstatus = 1 limit 1""",
				row.additional_salary,
			)
			if in_slip:
				note += f"; holiday pay {row.additional_salary} already in submitted slip {in_slip[0][0]} - reverse it manually"
			elif frappe.db.get_value("Additional Salary", row.additional_salary, "docstatus") == 1:
				frappe.get_doc("Additional Salary", row.additional_salary).cancel()
				note += f"; holiday pay {row.additional_salary} cancelled"
		frappe.db.set_value(
			DOCTYPE, row.name, {"status": "Cancelled", "remarks": ((row.remarks or "") + "\n" + note).strip()}
		)
