# Copyright (c) 2026, MIDHUNATECH
# Upgrade-safe override of HRMS Shift Assignment (verified against HRMS v16
# installed on this bench). Registered in hooks.py via override_doctype_class,
# same pattern as CustomShiftRequest.
#
# Core behaviour being changed:
#   ShiftAssignment.on_cancel() -> validate_employee_checkin() throws
#   "Cannot cancel Shift Assignment ... linked to Employee Checkin" whenever ANY
#   Employee Checkin exists in the assignment's employee/shift/date range.
#
# Business rules here:
#   - Checkins alone must NOT block cancel/amend. They are kept untouched and can
#     be re-linked to a new shift (standard fetch_shift only rewrites derived
#     mapping fields and skips checkins that already have an Attendance).
#   - Checkins already consumed by an Attendance record DO still block a full
#     cancel, as does an Attendance of its own -- cancelling the assignment they
#     were booked against would orphan them.
#   - But days that are already over must never freeze the REST of the roster.
#     A plant running A/B/C rotations has to be able to say "he worked C last
#     night, from tomorrow put him on B" without touching last night's record.
#     change_shift_from() does exactly that: it shortens the running assignment
#     to the day before the change and raises a fresh assignment for the new
#     shift from that day onwards. No cancel, so no attendance is disturbed.
#   - After submit/cancel/date-change of an assignment, unprocessed checkins in
#     the affected window are automatically re-synced via the same standard
#     fetch_shift() used by the built-in "Fetch Shift" list action -- no checkin
#     data is ever deleted.
#
# Night shifts (C = 22:00 -> 06:00) are safe by construction: a Shift Assignment
# is keyed on the date the shift STARTS, and fetch_shift maps a punch by
# shift_actual_start/end, so the 06:05 out-punch on the following morning stays
# attached to the previous night's C shift even after that next day has been
# switched to B.

import frappe
from frappe import _
from frappe.utils import add_days, get_link_to_form, getdate

from hrms.hr.doctype.shift_assignment.shift_assignment import ShiftAssignment

INLINE_RESYNC_LIMIT = 200


class CustomShiftAssignment(ShiftAssignment):
	def validate_employee_checkin(self):
		row = self.get_blocking_checkin()
		if row:
			frappe.throw(
				_(
					"Cannot cancel Shift Assignment {0}: Employee Checkin {1} is already processed into Attendance {2}."
				).format(
					frappe.bold(self.name),
					get_link_to_form("Employee Checkin", row.name),
					get_link_to_form("Attendance", row.attendance),
				)
				+ "<br><br>"
				+ self._change_shift_hint(),
				title=_("Attendance Already Generated"),
			)

	def get_blocking_checkin(self):
		"""A punch blocks only if it belongs to a shift this assignment covers
		AND has already been rolled into an Attendance.

		"Belongs to" is decided by shift_start -- the moment the shift the punch
		was mapped to began -- NOT by the punch's own clock time. On a night
		shift they are different days: C runs 22:00 -> 06:00, so the out-punch
		at 06:05 on the 9th belongs to the shift that started on the 8th and its
		Attendance is dated the 8th. Judging by clock time made a day-wise
		assignment for the 9th refuse to budge because of the 8th's record.
		"""
		base = {
			"employee": self.employee,
			"shift": self.shift_type,
			"attendance": ("is", "set"),
		}
		fields = ["name", "attendance", "time", "shift_start"]

		rows = frappe.get_all(
			"Employee Checkin",
			filters=dict(base, shift_start=self._date_range_filter()),
			fields=fields,
			limit=1,
		)
		if rows:
			return rows[0]

		# punches that were never mapped to a shift have no shift_start to go
		# on, so fall back to their own timestamp
		rows = frappe.get_all(
			"Employee Checkin",
			filters=dict(base, shift_start=("is", "not set"), time=self._date_range_filter()),
			fields=fields,
			limit=1,
		)
		return rows[0] if rows else None

	def validate_attendance(self):
		"""Same protection as core, minus two defects: core counts CANCELLED
		Attendance as blocking, and its ["between", [start, None]] filter is
		undefined for open-ended assignments."""
		attendances = frappe.get_all(
			"Attendance",
			filters={
				"employee": self.employee,
				"shift": self.shift_type,
				"docstatus": ("!=", 2),
				"attendance_date": self._date_range_filter(),
			},
			fields=["name", "attendance_date"],
			order_by="attendance_date asc",
			limit=1,
		)
		if attendances:
			row = attendances[0]
			frappe.throw(
				_("Cannot cancel Shift Assignment {0}: Attendance {1} is already marked for {2}.").format(
					frappe.bold(self.name),
					get_link_to_form("Attendance", row.name),
					frappe.bold(frappe.format(row.attendance_date, {"fieldtype": "Date"})),
				)
				+ "<br><br>"
				+ self._change_shift_hint(),
				title=_("Attendance Already Marked"),
			)

	def _date_range_filter(self):
		if self.end_date:
			return ("between", [self.start_date, self.end_date])
		return (">=", self.start_date)

	def _change_shift_hint(self):
		return _(
			"If you only want to move this employee to a different shift from a certain date onwards, "
			"use <b>Change Shift From Date</b> on this Shift Assignment instead of cancelling it. "
			"That keeps every day already worked exactly as it is."
		)

	# ---------------------------------------------------------------- lifecycle

	def on_submit(self):
		# installed HRMS v16 has no on_submit on the core class; guard in case a
		# future release adds one
		parent = getattr(super(), "on_submit", None)
		if callable(parent):
			parent()
		self.resync_employee_checkins()

	def on_cancel(self):
		# core on_cancel still runs validate_employee_checkin and
		# validate_attendance -- both ours, via MRO
		super().on_cancel()
		self.resync_employee_checkins()

	def on_update_after_submit(self):
		# end_date / status are allow-on-submit, so an assignment can be
		# shortened or extended in place. Re-map checkins across the union of
		# the old and new window, otherwise days that just lost (or gained) this
		# assignment keep a stale shift on their punches.
		super().on_update_after_submit()
		before = self.get_doc_before_save()
		start, end = getdate(self.start_date), getdate(self.end_date) if self.end_date else None
		if before:
			start = min(start, getdate(before.start_date))
			# either side open-ended means the union is open-ended
			end = None if (end is None or not before.end_date) else max(end, getdate(before.end_date))
		self.resync_employee_checkins((start, end))

	# ------------------------------------------------------------ checkin sync

	def get_resyncable_checkins(self, window: tuple | None = None) -> list[str]:
		start_date, end_date = window if window else (self.start_date, self.end_date)
		filters = {
			"employee": self.employee,
			"attendance": ("is", "not set"),
		}
		if end_date:
			# a night shift starting on end_date punches out the next morning
			filters["time"] = ("between", [start_date, add_days(getdate(end_date), 1)])
		else:
			filters["time"] = (">=", start_date)
		return frappe.get_all("Employee Checkin", filters=filters, pluck="name", order_by="time asc")

	def resync_employee_checkins(self, window: tuple | None = None):
		"""Re-run standard fetch_shift on unprocessed checkins in this
		assignment's range so they follow the currently active assignment."""
		if self.flags.skip_checkin_resync:
			return
		checkins = self.get_resyncable_checkins(window)
		if not checkins:
			return

		if len(checkins) > INLINE_RESYNC_LIMIT:
			frappe.enqueue(
				"rbol.custom_shift_assignment.resync_checkins",
				queue="long",
				timeout=1800,
				enqueue_after_commit=True,
				job_name=f"resync_checkins::{self.name}",
				checkins=checkins,
			)
			frappe.msgprint(
				_("{0} Employee Checkins are being re-mapped to the current shift in the background.").format(
					len(checkins)
				),
				alert=True,
				indicator="blue",
			)
		else:
			updated = resync_checkins(checkins)
			if updated:
				frappe.msgprint(
					_("{0} Employee Checkins re-mapped to the current shift.").format(updated),
					alert=True,
					indicator="green",
				)


def resync_checkins(checkins: list) -> int:
	"""Same pattern as core employee_checkin.bulk_fetch_shift (the "Fetch Shift"
	list action): fetch_shift + save with ignore_validate. fetch_shift itself
	never rewrites a checkin that has an Attendance linked; we also skip them."""
	updated = 0
	for name in checkins:
		try:
			doc = frappe.get_doc("Employee Checkin", name)
			if doc.attendance:
				continue
			doc.fetch_shift()
			doc.flags.ignore_validate = True
			doc.save(ignore_permissions=True)
			updated += 1
		except Exception:
			frappe.log_error(
				title="rbol: checkin resync failed",
				message=f"Employee Checkin: {name}\n\n{frappe.get_traceback()}",
			)
	return updated


# --------------------------------------------------------------------- action


@frappe.whitelist()
def change_shift_from(
	assignment: str,
	from_date: str,
	new_shift_type: str,
	new_status: str | None = None,
	shift_location: str | None = None,
) -> dict:
	"""Move an employee onto a different shift from `from_date` onwards without
	disturbing the days already worked under the running assignment.

	  before:  C  01-08 ............................ 31-08
	  after:   C  01-08 .. 08-08 | B  09-08 ........ 31-08

	The running assignment is shortened in place (end_date is allow-on-submit,
	so it is never cancelled and the Attendance booked against it is untouched).
	Only when the change starts on the assignment's own first day is there
	nothing left to keep, and then it is cancelled -- which still runs the full
	checkin/attendance protection above.
	"""
	doc = frappe.get_doc("Shift Assignment", assignment)
	doc.check_permission("write")

	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted Shift Assignment can be changed."))

	from_date = getdate(from_date)
	start_date = getdate(doc.start_date)
	end_date = getdate(doc.end_date) if doc.end_date else None

	if from_date < start_date:
		frappe.throw(
			_("Change date {0} is before this assignment starts ({1}).").format(
				frappe.format(from_date, {"fieldtype": "Date"}),
				frappe.format(start_date, {"fieldtype": "Date"}),
			)
		)
	if end_date and from_date > end_date:
		frappe.throw(
			_("Change date {0} is after this assignment ends ({1}).").format(
				frappe.format(from_date, {"fieldtype": "Date"}),
				frappe.format(end_date, {"fieldtype": "Date"}),
			)
		)
	if new_shift_type == doc.shift_type:
		frappe.throw(_("{0} is already the shift on this assignment.").format(frappe.bold(new_shift_type)))

	_validate_nothing_recorded_from(doc, from_date, end_date)

	if from_date == start_date:
		# nothing of the old assignment survives -- cancel it outright
		doc.flags.ignore_permissions = True
		doc.flags.skip_checkin_resync = True
		doc.cancel()
		old_state = _("cancelled")
	else:
		doc.end_date = add_days(from_date, -1)
		doc.flags.ignore_permissions = True
		doc.flags.skip_checkin_resync = True
		doc.save()
		old_state = _("shortened to {0}").format(frappe.format(doc.end_date, {"fieldtype": "Date"}))

	new = frappe.new_doc("Shift Assignment")
	new.employee = doc.employee
	new.company = doc.company
	new.shift_type = new_shift_type
	new.start_date = from_date
	new.end_date = end_date
	new.status = new_status or doc.status
	new.shift_location = shift_location if shift_location is not None else doc.shift_location
	new.insert(ignore_permissions=True)
	new.submit()

	frappe.msgprint(
		_("{0} moved to shift {1} from {2}. Previous assignment {3} {4}.").format(
			frappe.bold(doc.employee_name or doc.employee),
			frappe.bold(new_shift_type),
			frappe.bold(frappe.format(from_date, {"fieldtype": "Date"})),
			get_link_to_form("Shift Assignment", doc.name),
			old_state,
		),
		title=_("Shift Changed"),
		indicator="green",
	)

	return {"previous_assignment": doc.name, "new_assignment": new.name}


def _validate_nothing_recorded_from(doc, from_date, end_date):
	"""Days from `from_date` onwards are the ones being handed to the new shift.
	If attendance has already been marked for any of them, the change would
	silently contradict a booked record -- block with the exact date."""
	filters = {
		"employee": doc.employee,
		"shift": doc.shift_type,
		"docstatus": ("!=", 2),
	}
	if end_date:
		filters["attendance_date"] = ("between", [from_date, end_date])
	else:
		filters["attendance_date"] = (">=", from_date)

	rows = frappe.get_all(
		"Attendance", filters=filters, fields=["name", "attendance_date"], order_by="attendance_date asc"
	)
	if rows:
		frappe.throw(
			_(
				"Attendance is already marked on {0} for shift {1} (e.g. {2}). Pick a change date after that, or cancel the Attendance first."
			).format(
				frappe.bold(frappe.format(rows[0].attendance_date, {"fieldtype": "Date"})),
				frappe.bold(doc.shift_type),
				get_link_to_form("Attendance", rows[0].name),
			),
			title=_("Attendance Already Marked"),
		)


@frappe.whitelist()
def get_change_shift_context(assignment: str) -> dict:
	"""Sensible defaults for the Change Shift dialog: earliest date that is not
	already booked, and the current shift so the form can exclude it."""
	doc = frappe.get_doc("Shift Assignment", assignment)
	doc.check_permission("read")

	last_booked = frappe.get_all(
		"Attendance",
		filters={
			"employee": doc.employee,
			"shift": doc.shift_type,
			"docstatus": ("!=", 2),
			"attendance_date": (">=", doc.start_date),
		},
		fields=["attendance_date"],
		order_by="attendance_date desc",
		limit=1,
	)
	last_date = last_booked[0].attendance_date if last_booked else None

	earliest = add_days(getdate(last_date), 1) if last_date else getdate(doc.start_date)
	default = max(earliest, getdate(frappe.utils.nowdate()))
	if doc.end_date and default > getdate(doc.end_date):
		default = getdate(doc.end_date)

	return {
		"employee": doc.employee,
		"employee_name": doc.employee_name,
		"shift_type": doc.shift_type,
		"start_date": doc.start_date,
		"end_date": doc.end_date,
		"earliest_change_date": earliest,
		"default_change_date": default,
		"last_attendance_date": last_date,
	}
