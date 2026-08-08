"""E2E verification for the rbol "Change Shift From Date" flow.

Run:  echo "from rbol.shift_change_check import run; run()" | bench --site <site> console
"""

import frappe
from frappe.utils import add_days, get_datetime, getdate

E = "MT Shift Change Test"
EMP_NO = "MT-SCT-001"
TODAY = "2026-08-08"
TOMORROW = "2026-08-09"
MONTH_END = "2026-08-31"

RESULTS = []


def ok(name, cond, detail=""):
	RESULTS.append(("PASS" if cond else "FAIL", name, detail))


def cleanup():
	emp = frappe.db.get_value("Employee", {"employee_number": EMP_NO}, "name")
	if emp:
		for att in frappe.get_all("Attendance", filters={"employee": emp}, pluck="name"):
			frappe.db.set_value("Employee Checkin", {"attendance": att}, "attendance", None)
			frappe.db.set_value("Attendance", att, "docstatus", 2)
			frappe.delete_doc("Attendance", att, force=True)
		for ci in frappe.get_all("Employee Checkin", filters={"employee": emp}, pluck="name"):
			frappe.delete_doc("Employee Checkin", ci, force=True)
		for sa in frappe.get_all("Shift Assignment", filters={"employee": emp}, pluck="name"):
			frappe.db.set_value("Shift Assignment", sa, "docstatus", 2)
			frappe.delete_doc("Shift Assignment", sa, force=True)
		frappe.delete_doc("Employee", emp, force=True)
	frappe.db.commit()


def run():
	try:
		_run()
	except Exception:
		RESULTS.append(("FAIL", "suite crashed", frappe.get_traceback(with_context=False)[-600:]))
	finally:
		print("\n=====SHIFT CHANGE CHECK=====")
		for status, name, detail in RESULTS:
			print(f"[{status}] {name}" + (f"  --  {detail}" if detail else ""))
		p = sum(1 for r in RESULTS if r[0] == "PASS")
		print(f"----- {p}/{len(RESULTS)} PASS -----")
		print("=====END=====")


def _run():
	cleanup()
	company = frappe.db.get_value("Company", {}, "name")
	emp = frappe.get_doc({
		"doctype": "Employee", "first_name": E, "gender": "Male", "employee_number": EMP_NO,
		"date_of_birth": "1995-01-01", "date_of_joining": "2026-01-01",
		"company": company, "status": "Active",
	}).insert(ignore_permissions=True)
	frappe.db.commit()

	def mk(shift, start, end):
		d = frappe.get_doc({"doctype": "Shift Assignment", "employee": emp.name, "shift_type": shift,
			"start_date": start, "end_date": end, "company": company, "status": "Active"})
		d.insert(ignore_permissions=True)
		d.submit()
		frappe.db.commit()
		return d

	def ci(dt, log_type):
		c = frappe.get_doc({"doctype": "Employee Checkin", "employee": emp.name,
			"time": get_datetime(dt), "log_type": log_type}).insert(ignore_permissions=True)
		frappe.db.commit()
		return c

	def att(date, shift):
		a = frappe.get_doc({"doctype": "Attendance", "employee": emp.name, "attendance_date": date,
			"status": "Present", "company": company, "shift": shift}).insert(ignore_permissions=True)
		a.submit()
		frappe.db.commit()
		return a

	def wipe():
		for x in frappe.get_all("Attendance", filters={"employee": emp.name}, pluck="name"):
			frappe.db.set_value("Employee Checkin", {"attendance": x}, "attendance", None)
			frappe.db.set_value("Attendance", x, "docstatus", 2)
			frappe.delete_doc("Attendance", x, force=True)
		for x in frappe.get_all("Employee Checkin", filters={"employee": emp.name}, pluck="name"):
			frappe.delete_doc("Employee Checkin", x, force=True)
		for x in frappe.get_all("Shift Assignment", filters={"employee": emp.name}, pluck="name"):
			frappe.db.set_value("Shift Assignment", x, "docstatus", 2)
			frappe.delete_doc("Shift Assignment", x, force=True)
		frappe.db.commit()

	def live():
		return frappe.get_all("Shift Assignment", filters={"employee": emp.name, "docstatus": 1},
			fields=["name", "shift_type", "start_date", "end_date"], order_by="start_date")

	from rbol.custom_shift_assignment import change_shift_from, get_change_shift_context

	# 0 - override still wired
	from frappe.model.document import get_controller
	cls = get_controller("Shift Assignment")
	ok("override active", cls.__name__ == "CustomShiftAssignment",
		cls.__module__ + "." + cls.__name__)

	# ---------------------------------------------------------------- 1
	# THE USE CASE: C shift 08-08 -> 08-31, worked last night, switch to B tomorrow
	a = mk("C", TODAY, MONTH_END)
	c_in = ci(TODAY + " 22:05:00", "IN")
	c_out = ci(TOMORROW + " 06:05:00", "OUT")
	at = att(TODAY, "C")
	frappe.db.set_value("Employee Checkin", c_in.name, "attendance", at.name)
	frappe.db.set_value("Employee Checkin", c_out.name, "attendance", at.name)
	frappe.db.commit()

	res = change_shift_from(a.name, TOMORROW, "B")
	frappe.db.commit()
	rows = live()
	ok("1 change C->B from tomorrow: two live assignments", len(rows) == 2,
		"; ".join(f"{r.shift_type} {r.start_date}->{r.end_date}" for r in rows))
	ok("1 old C shortened to today",
		rows and rows[0].shift_type == "C" and str(rows[0].end_date) == TODAY,
		str(rows[0].end_date) if rows else "-")
	ok("1 new B covers tomorrow -> month end",
		len(rows) > 1 and rows[1].shift_type == "B"
		and str(rows[1].start_date) == TOMORROW and str(rows[1].end_date) == MONTH_END)
	ok("1 last night's Attendance untouched",
		frappe.db.get_value("Attendance", at.name, "docstatus") == 1
		and frappe.db.get_value("Attendance", at.name, "shift") == "C")
	ok("1 old assignment still submitted (not cancelled)",
		frappe.db.get_value("Shift Assignment", a.name, "docstatus") == 1)
	ok("1 returns both names",
		res.get("previous_assignment") == a.name and res.get("new_assignment") == rows[1].name)

	# night-shift trap: the 06:05 punch belongs to LAST NIGHT's C, not to B
	ok("1 night-shift out-punch still mapped to C",
		frappe.db.get_value("Employee Checkin", c_out.name, "shift") == "C",
		"shift=" + str(frappe.db.get_value("Employee Checkin", c_out.name, "shift")))
	ok("1 night-shift in-punch still mapped to C",
		frappe.db.get_value("Employee Checkin", c_in.name, "shift") == "C")
	wipe()

	# ---------------------------------------------------------------- 2
	# unprocessed checkin on the switched days follows the NEW shift
	a = mk("C", TODAY, MONTH_END)
	att(TODAY, "C")
	later = ci("2026-08-10 22:10:00", "IN")   # a C punch three days out
	ok("2 punch starts on C", frappe.db.get_value("Employee Checkin", later.name, "shift") == "C")
	change_shift_from(a.name, TOMORROW, "B")
	frappe.db.commit()
	ok("2 unprocessed punch does NOT stay on C after the switch",
		frappe.db.get_value("Employee Checkin", later.name, "shift") != "C",
		"now shift=" + str(frappe.db.get_value("Employee Checkin", later.name, "shift"))
		+ " (22:10 is outside B 14:00-22:00, so unmapped is correct)")
	wipe()

	# ---------------------------------------------------------------- 3
	# change on the assignment's own first day -> old one cancelled outright
	a = mk("C", TOMORROW, MONTH_END)
	change_shift_from(a.name, TOMORROW, "B")
	frappe.db.commit()
	rows = live()
	ok("3 first-day change leaves exactly one live assignment", len(rows) == 1,
		"; ".join(f"{r.shift_type} {r.start_date}->{r.end_date}" for r in rows))
	ok("3 it is B for the full original range",
		rows and rows[0].shift_type == "B" and str(rows[0].start_date) == TOMORROW
		and str(rows[0].end_date) == MONTH_END)
	ok("3 old C assignment cancelled",
		frappe.db.get_value("Shift Assignment", a.name, "docstatus") == 2)
	wipe()

	# ---------------------------------------------------------------- 4
	# attendance already booked ON the change date -> must be refused
	a = mk("C", TODAY, MONTH_END)
	att(TOMORROW, "C")
	try:
		change_shift_from(a.name, TOMORROW, "B")
		frappe.db.commit()
		ok("4 refuses when attendance exists on the change date", False, "it went through")
	except frappe.ValidationError as e:
		frappe.db.rollback()
		ok("4 refuses when attendance exists on the change date", True,
			frappe.utils.strip_html(str(e))[:110])
	ok("4 nothing changed", len(live()) == 1 and str(live()[0].end_date) == MONTH_END)
	wipe()

	# ---------------------------------------------------------------- 5
	# open-ended assignment
	a = mk("C", TODAY, None)
	att(TODAY, "C")
	change_shift_from(a.name, TOMORROW, "B")
	frappe.db.commit()
	rows = live()
	ok("5 open-ended: C closed at today, B open-ended from tomorrow",
		len(rows) == 2 and str(rows[0].end_date) == TODAY and rows[1].shift_type == "B"
		and rows[1].end_date is None,
		"; ".join(f"{r.shift_type} {r.start_date}->{r.end_date}" for r in rows))
	wipe()

	# ---------------------------------------------------------------- 6
	# guard rails
	a = mk("C", TODAY, MONTH_END)
	for label, args in (
		("6 rejects a date before the assignment starts", (a.name, "2026-08-01", "B")),
		("6 rejects a date after the assignment ends", (a.name, "2026-09-05", "B")),
		("6 rejects switching to the same shift", (a.name, TOMORROW, "C")),
	):
		try:
			change_shift_from(*args)
			frappe.db.commit()
			ok(label, False, "it went through")
		except frappe.ValidationError as e:
			frappe.db.rollback()
			ok(label, True, frappe.utils.strip_html(str(e))[:80])
	wipe()

	# ---------------------------------------------------------------- 7
	# dialog defaults
	a = mk("C", TODAY, MONTH_END)
	att(TODAY, "C")
	ctx = get_change_shift_context(a.name)
	ok("7 context: earliest change date is the day after the last marked attendance",
		str(ctx["earliest_change_date"]) == TOMORROW, str(ctx["earliest_change_date"]))
	ok("7 context: reports last attendance date", str(ctx["last_attendance_date"]) == TODAY)
	ok("7 context: current shift + range", ctx["shift_type"] == "C"
		and str(ctx["start_date"]) == TODAY and str(ctx["end_date"]) == MONTH_END)
	wipe()

	# ---------------------------------------------------------------- 8
	# a CANCELLED attendance must not block a straight cancel any more
	a = mk("C", TODAY, MONTH_END)
	at = att(TODAY, "C")
	frappe.get_doc("Attendance", at.name).cancel()
	frappe.db.commit()
	try:
		d = frappe.get_doc("Shift Assignment", a.name)
		d.flags.ignore_permissions = True
		d.cancel()
		frappe.db.commit()
		ok("8 cancelled Attendance no longer blocks cancel", True)
	except Exception as e:
		frappe.db.rollback()
		ok("8 cancelled Attendance no longer blocks cancel", False,
			frappe.utils.strip_html(str(e))[:120])
	wipe()

	# ---------------------------------------------------------------- 9
	# a SUBMITTED attendance still blocks a straight cancel (protection intact)
	a = mk("C", TODAY, MONTH_END)
	att(TODAY, "C")
	try:
		d = frappe.get_doc("Shift Assignment", a.name)
		d.flags.ignore_permissions = True
		d.cancel()
		frappe.db.commit()
		ok("9 submitted Attendance still blocks a straight cancel", False, "cancel went through")
	except frappe.ValidationError as e:
		frappe.db.rollback()
		msg = frappe.utils.strip_html(str(e))
		ok("9 submitted Attendance still blocks a straight cancel", True)
		ok("9 the block explains the Change Shift From Date way out",
			"Change Shift From Date" in msg, msg[:150])
	wipe()

	# ---------------------------------------------------------------- 10
	# checkin-only assignment can still be cancelled (the 1421866 behaviour)
	a = mk("C", TOMORROW, MONTH_END)
	ci(TOMORROW + " 22:05:00", "IN")
	try:
		d = frappe.get_doc("Shift Assignment", a.name)
		d.flags.ignore_permissions = True
		d.cancel()
		frappe.db.commit()
		ok("10 checkin without Attendance still does not block cancel", True)
	except Exception as e:
		frappe.db.rollback()
		ok("10 checkin without Attendance still does not block cancel", False,
			frappe.utils.strip_html(str(e))[:120])
	wipe()

	# ---------------------------------------------------------------- 11
	# shortening an assignment by hand re-syncs punches in the dropped tail
	a = mk("C", TODAY, MONTH_END)
	tail = ci("2026-08-15 22:05:00", "IN")
	ok("11 tail punch starts on C", frappe.db.get_value("Employee Checkin", tail.name, "shift") == "C")
	d = frappe.get_doc("Shift Assignment", a.name)
	d.end_date = "2026-08-10"
	d.flags.ignore_permissions = True
	d.save()
	frappe.db.commit()
	ok("11 punch in the dropped tail no longer claims C",
		frappe.db.get_value("Employee Checkin", tail.name, "shift") != "C",
		"now shift=" + str(frappe.db.get_value("Employee Checkin", tail.name, "shift")))
	wipe()

	# ================================================================
	# ROTATION: a real day-wise A/B/C roster -- one Shift Assignment per day,
	# weekly rotation, attendance already marked for every day up to today, and
	# a cross-midnight C punch sitting on the very day we want to change.
	#   01-08, 02-08     B
	#   03-08 .. 09-08   C     <- today is 08-08, tomorrow is 09-08
	#   10-08 .. 16-08   A
	#   17-08 .. 21-08   B
	# ================================================================
	ROSTER = {}
	for i in range(21):
		day = str(add_days("2026-08-01", i))
		if day <= "2026-08-02":
			ROSTER[day] = "B"
		elif day <= "2026-08-09":
			ROSTER[day] = "C"
		elif day <= "2026-08-16":
			ROSTER[day] = "A"
		else:
			ROSTER[day] = "B"

	def build_rotation():
		wipe()
		by_day = {day: mk(shift, day, day) for day, shift in sorted(ROSTER.items())}
		for day, shift in sorted(ROSTER.items()):
			if day > TODAY:
				continue
			a = att(day, shift)
			if shift == "C":
				# 22:05 that evening and 06:05 the NEXT morning -- both belong
				# to this day's shift and both carry THIS day's Attendance
				for c in (ci(day + " 22:05:00", "IN"),
						ci(str(add_days(day, 1)) + " 06:05:00", "OUT")):
					frappe.db.set_value("Employee Checkin", c.name, "attendance", a.name)
		frappe.db.commit()
		return by_day

	def roster_now():
		return {
			str(r.start_date): r.shift_type
			for r in frappe.get_all("Shift Assignment",
				filters={"employee": emp.name, "docstatus": 1},
				fields=["shift_type", "start_date"], order_by="start_date")
		}

	# ---------------------------------------------------------------- 12
	# THE REPORTED BUG: day-wise roster, change 09-08 from C to B while the
	# 09-08 06:05 punch carries the 08-08 Attendance.
	by_day = build_rotation()
	out_punch = frappe.get_all("Employee Checkin",
		filters={"employee": emp.name,
			"time": ("between", [TOMORROW + " 00:00:00", TOMORROW + " 12:00:00"])},
		fields=["name", "shift", "shift_start", "attendance"])
	ok("12 setup: a punch sits on 09-08 morning", len(out_punch) == 1, str(out_punch))
	ok("12 setup: that punch belongs to the shift that started 08-08",
		len(out_punch) == 1 and str(out_punch[0].shift_start).startswith(TODAY),
		str(out_punch[0].shift_start) if out_punch else "-")
	ok("12 setup: and it carries the 08-08 Attendance",
		len(out_punch) == 1
		and frappe.db.get_value("Attendance", out_punch[0].attendance, "attendance_date") == getdate(TODAY))

	before_att = frappe.get_all("Attendance", filters={"employee": emp.name, "docstatus": 1},
		fields=["name", "attendance_date", "shift"], order_by="attendance_date")
	try:
		change_shift_from(by_day[TOMORROW].name, TOMORROW, "B")
		frappe.db.commit()
		ok("12 change 09-08 from C to B on a day-wise roster", True)
	except Exception as e:
		frappe.db.rollback()
		ok("12 change 09-08 from C to B on a day-wise roster", False,
			frappe.utils.strip_html(str(e))[:200])

	now = roster_now()
	ok("12 09-08 is now B", now.get(TOMORROW) == "B", str(now.get(TOMORROW)))
	ok("12 08-08 is still C", now.get(TODAY) == "C", str(now.get(TODAY)))
	ok("12 10-08 is untouched", now.get("2026-08-10") == "A", str(now.get("2026-08-10")))
	ok("12 no day gained or lost", len(now) == len(ROSTER), f"{len(now)} vs {len(ROSTER)}")
	ok("12 every other day unchanged",
		all(now.get(d) == s for d, s in ROSTER.items() if d != TOMORROW),
		str({d: (s, now.get(d)) for d, s in ROSTER.items() if d != TOMORROW and now.get(d) != s}))

	after_att = frappe.get_all("Attendance", filters={"employee": emp.name, "docstatus": 1},
		fields=["name", "attendance_date", "shift"], order_by="attendance_date")
	ok("12 all marked days survive untouched", before_att == after_att,
		f"{len(before_att)} -> {len(after_att)}")
	ok("12 the 09-08 morning punch still belongs to 08-08's C shift",
		frappe.db.get_value("Employee Checkin", out_punch[0].name, "shift") == "C"
		and str(frappe.db.get_value("Employee Checkin", out_punch[0].name, "shift_start")).startswith(TODAY),
		str(frappe.db.get_value("Employee Checkin", out_punch[0].name, ["shift", "shift_start"])))

	# ---------------------------------------------------------------- 13
	# the plain "delete the 09-08 shift" route must work too
	by_day = build_rotation()
	try:
		d = frappe.get_doc("Shift Assignment", by_day[TOMORROW].name)
		d.flags.ignore_permissions = True
		d.cancel()
		frappe.db.commit()
		ok("13 plain cancel of the 09-08 C assignment", True)
	except Exception as e:
		frappe.db.rollback()
		ok("13 plain cancel of the 09-08 C assignment", False,
			frappe.utils.strip_html(str(e))[:200])
	ok("13 08-08 C survives the cancel", roster_now().get(TODAY) == "C")
	ok("13 08-08 Attendance survives the cancel",
		frappe.db.get_value("Attendance",
			{"employee": emp.name, "attendance_date": TODAY}, "docstatus") == 1)

	# ---------------------------------------------------------------- 14
	# today itself is already marked -- that one must still be refused
	by_day = build_rotation()
	try:
		change_shift_from(by_day[TODAY].name, TODAY, "B")
		frappe.db.commit()
		ok("14 refuses to change a day that is already marked", False, "it went through")
	except frappe.ValidationError as e:
		frappe.db.rollback()
		ok("14 refuses to change a day that is already marked", True,
			frappe.utils.strip_html(str(e))[:110])
	ok("14 08-08 still C after the refusal", roster_now().get(TODAY) == "C")

	# ---------------------------------------------------------------- 15
	# LOOP: walk forward changing several days in a row
	build_rotation()
	plan = [(TOMORROW, "B"), ("2026-08-10", "C"), ("2026-08-11", "B"), ("2026-08-12", "C")]
	loop_ok = True
	loop_detail = []
	for day, new_shift in plan:
		try:
			target = frappe.get_all("Shift Assignment",
				filters={"employee": emp.name, "docstatus": 1, "start_date": day}, pluck="name")
			change_shift_from(target[0], day, new_shift)
			frappe.db.commit()
			loop_detail.append(f"{day}->{new_shift} ok")
		except Exception as e:
			frappe.db.rollback()
			loop_ok = False
			loop_detail.append(f"{day}->{new_shift} FAILED: " + frappe.utils.strip_html(str(e))[:90])
	ok("15 loop: four days changed one after another", loop_ok, "; ".join(loop_detail))
	now = roster_now()
	ok("15 loop: every changed day holds its new shift",
		all(now.get(d) == s for d, s in plan), str({d: now.get(d) for d, _ in plan}))
	ok("15 loop: days outside the plan are untouched",
		all(now.get(d) == s for d, s in ROSTER.items() if d not in dict(plan)),
		str({d: (s, now.get(d)) for d, s in ROSTER.items()
			if d not in dict(plan) and now.get(d) != s}))
	ok("15 loop: still one live assignment per day, none lost or duplicated",
		len(now) == len(ROSTER)
		and len(frappe.get_all("Shift Assignment",
			filters={"employee": emp.name, "docstatus": 1})) == len(ROSTER),
		f"{len(now)} distinct dates vs {len(ROSTER)} expected")

	# ---------------------------------------------------------------- 16
	# WEEK-BLOCK rotation (date ranges, not single days) -- change mid-block
	wipe()
	blocks = [("C", "2026-08-01", "2026-08-07"), ("A", "2026-08-08", "2026-08-14"),
		("B", "2026-08-15", "2026-08-21")]
	made = [mk(s, f, t) for s, f, t in blocks]
	att("2026-08-08", "A")
	try:
		change_shift_from(made[1].name, "2026-08-10", "C")
		frappe.db.commit()
		ok("16 week-block roster: change mid-block", True)
	except Exception as e:
		frappe.db.rollback()
		ok("16 week-block roster: change mid-block", False, frappe.utils.strip_html(str(e))[:200])
	rows = frappe.get_all("Shift Assignment", filters={"employee": emp.name, "docstatus": 1},
		fields=["shift_type", "start_date", "end_date"], order_by="start_date")
	shown = "; ".join(f"{r.shift_type} {r.start_date}->{r.end_date}" for r in rows)
	ok("16 result is C 01-07, A 08-09, C 10-14, B 15-21",
		shown == ("C 2026-08-01->2026-08-07; A 2026-08-08->2026-08-09; "
			"C 2026-08-10->2026-08-14; B 2026-08-15->2026-08-21"), shown)
	ok("16 no gap and no overlap between blocks",
		len(rows) == 4 and all(getdate(rows[i + 1].start_date) == add_days(rows[i].end_date, 1)
			for i in range(len(rows) - 1)), shown)
	wipe()
	wipe()

	# ---------------------------------------------------------------- 17
	# enable_auto_attendance is ON for the real A/B/C shift types, and the
	# scheduler decides which shift a punch belongs to via HRMS
	# get_actual_start_end_datetime_of_shift. That has to agree with the change,
	# otherwise auto-attendance would keep marking the old shift.
	from hrms.hr.doctype.shift_assignment.shift_assignment import (
		get_actual_start_end_datetime_of_shift as shift_at,
	)

	by_day = build_rotation()
	change_shift_from(by_day[TOMORROW].name, TOMORROW, "B")
	frappe.db.commit()

	for label, stamp, want_shift, want_day in (
		("22:30 on 08-08 -> C", TODAY + " 22:30:00", "C", TODAY),
		("06:05 on 09-08 still belongs to 08-08's C", TOMORROW + " 06:05:00", "C", TODAY),
		("15:00 on 09-08 -> the new B", TOMORROW + " 15:00:00", "B", TOMORROW),
		("08:00 on 10-08 -> A", "2026-08-10 08:00:00", "A", "2026-08-10"),
	):
		det = shift_at(emp.name, get_datetime(stamp), True)
		got_shift = det.shift_type.name if det and det.shift_type else None
		got_day = str(det.start_datetime)[:10] if det and det.start_datetime else None
		ok("17 auto-attendance lookup: " + label,
			got_shift == want_shift and got_day == want_day, f"{got_shift} starting {got_day}")
	wipe()

	cleanup()
