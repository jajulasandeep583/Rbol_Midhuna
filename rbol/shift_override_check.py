# E2E verification for midhuna_hr CustomShiftAssignment override (run via bench execute)
import frappe
from frappe.utils import get_datetime

EMP_NAME = "MT Shift Test"
SHIFT_A = "MT-TEST-DAY"   # 09:00-17:00
SHIFT_B = "MT-TEST-EVE"   # 08:00-16:00 (overlaps so same checkins fit both)
D1 = "2026-08-03"
D2 = "2026-08-05"


def _cleanup():
	for att in frappe.get_all("Attendance", filters={"employee_name": EMP_NAME}, pluck="name"):
		doc = frappe.get_doc("Attendance", att)
		frappe.db.set_value("Employee Checkin", {"attendance": att}, "attendance", None)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Attendance", att, force=True)
	emp = frappe.db.get_value("Employee", {"first_name": EMP_NAME}, "name")
	if emp:
		for ci in frappe.get_all("Employee Checkin", filters={"employee": emp}, pluck="name"):
			frappe.delete_doc("Employee Checkin", ci, force=True)
		for sa in frappe.get_all("Shift Assignment", filters={"employee": emp}, pluck="name"):
			doc = frappe.get_doc("Shift Assignment", sa)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("Shift Assignment", sa, force=True)
		frappe.delete_doc("Employee", emp, force=True)
	for st in (SHIFT_A, SHIFT_B):
		if frappe.db.exists("Shift Type", st):
			frappe.delete_doc("Shift Type", st, force=True)
	frappe.db.commit()


def run():
	out = []
	_cleanup()

	# resolved class check
	from frappe.model.document import get_controller
	cls = get_controller("Shift Assignment")
	out.append(("override active", cls.__module__ + "." + cls.__name__))

	company = frappe.db.get_value("Company", {}, "name")

	for st, start, end in ((SHIFT_A, "09:00:00", "17:00:00"), (SHIFT_B, "08:00:00", "16:00:00")):
		frappe.get_doc({
			"doctype": "Shift Type", "__newname": st,
			"start_time": start, "end_time": end,
			"enable_auto_attendance": 0,
		}).insert(ignore_permissions=True)

	emp = frappe.get_doc({
		"doctype": "Employee", "first_name": EMP_NAME, "gender": "Male",
		"employee_number": "MT-TEST-001",
		"date_of_birth": "1995-01-01", "date_of_joining": "2026-01-01",
		"company": company, "status": "Active",
	}).insert(ignore_permissions=True)

	sa1 = frappe.get_doc({
		"doctype": "Shift Assignment", "employee": emp.name, "shift_type": SHIFT_A,
		"start_date": D1, "end_date": D2, "status": "Active", "company": company,
	}).insert(ignore_permissions=True)
	sa1.submit()

	checkins = []
	for ts, lt in ((f"{D1} 09:05:00", "IN"), (f"{D1} 15:55:00", "OUT")):
		ci = frappe.get_doc({
			"doctype": "Employee Checkin", "employee": emp.name,
			"time": get_datetime(ts), "log_type": lt,
		}).insert(ignore_permissions=True)
		checkins.append(ci.name)
	out.append(("checkin shift after insert (expect %s)" % SHIFT_A,
		frappe.db.get_value("Employee Checkin", checkins[0], "shift")))

	# TEST 1: cancel with checkins but NO attendance -> must succeed now
	try:
		sa1.reload(); sa1.cancel()
		out.append(("TEST1 cancel SA with checkins, no attendance", "PASS (cancelled)"))
	except Exception as e:
		out.append(("TEST1 cancel SA with checkins, no attendance", "FAIL: %s" % e))

	# checkins untouched?
	still = frappe.get_all("Employee Checkin", filters={"name": ("in", checkins)}, pluck="name")
	out.append(("TEST2 checkins preserved", "PASS" if len(still) == 2 else "FAIL %s" % still))

	# after cancel, auto-resync should have cleared shift (no active assignment)
	sh = frappe.db.get_value("Employee Checkin", checkins[0], ["shift", "offshift"], as_dict=True)
	out.append(("TEST2b auto-resync on cancel cleared shift",
		"PASS" if not sh.shift and sh.offshift else "FAIL %s" % sh))

	# TEST 3: new assignment same dates, different shift
	sa2 = frappe.get_doc({
		"doctype": "Shift Assignment", "employee": emp.name, "shift_type": SHIFT_B,
		"start_date": D1, "end_date": D2, "status": "Active", "company": company,
	}).insert(ignore_permissions=True)
	sa2.submit()
	out.append(("TEST3 new SA same dates after cancel", "PASS (%s)" % sa2.name))

	# TEST 4: checkins AUTO re-mapped to new shift on submit (no manual Fetch Shift)
	shifts = [frappe.db.get_value("Employee Checkin", c, "shift") for c in checkins]
	out.append(("TEST4 checkins auto re-mapped to %s on submit" % SHIFT_B,
		"PASS" if all(s == SHIFT_B for s in shifts) else "FAIL %s" % shifts))

	# TEST 5: once Attendance exists + linked, cancel must be BLOCKED
	att = frappe.get_doc({
		"doctype": "Attendance", "employee": emp.name, "attendance_date": D1,
		"status": "Present", "shift": SHIFT_B, "company": company,
	}).insert(ignore_permissions=True)
	att.submit()
	frappe.db.set_value("Employee Checkin", checkins[0], "attendance", att.name)
	try:
		sa2.reload(); sa2.cancel()
		out.append(("TEST5 cancel blocked when attendance linked", "FAIL: cancel went through"))
	except frappe.ValidationError as e:
		out.append(("TEST5 cancel blocked when attendance linked", "PASS (%s)" % str(e)[:80]))

	frappe.db.commit()
	_cleanup()
	out.append(("cleanup", "done"))
	for k, v in out:
		print(f"{k}: {v}")
