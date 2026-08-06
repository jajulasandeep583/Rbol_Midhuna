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
# Business rule here:
#   - Checkins alone must NOT block cancel/amend. They are kept untouched and can
#     be re-linked to a new shift (standard fetch_shift only rewrites derived
#     mapping fields and skips checkins that already have an Attendance).
#   - Checkins already consumed by an Attendance record DO still block, and the
#     untouched core validate_attendance() (still called by on_cancel) keeps the
#     standard Attendance protection fully intact.
#   - After submit/cancel of an assignment, unprocessed checkins in its range are
#     automatically re-synced via the same standard fetch_shift() used by the
#     built-in "Fetch Shift" list action — no checkin data is ever deleted.

import frappe
from frappe import _
from frappe.utils import get_link_to_form

from hrms.hr.doctype.shift_assignment.shift_assignment import ShiftAssignment

INLINE_RESYNC_LIMIT = 200


class CustomShiftAssignment(ShiftAssignment):
	def validate_employee_checkin(self):
		filters = {
			"employee": self.employee,
			"shift": self.shift_type,
			"attendance": ("is", "set"),
		}
		if self.end_date:
			filters["time"] = ("between", [self.start_date, self.end_date])
		else:
			filters["time"] = (">=", self.start_date)

		checkins_with_attendance = frappe.get_all(
			"Employee Checkin", filters=filters, fields=["name", "attendance"], limit=1
		)
		if checkins_with_attendance:
			row = checkins_with_attendance[0]
			frappe.throw(
				_(
					"Cannot cancel Shift Assignment {0}: Employee Checkin {1} is already processed into Attendance {2}. Cancel the Attendance first."
				).format(
					frappe.bold(self.name),
					get_link_to_form("Employee Checkin", row.name),
					get_link_to_form("Attendance", row.attendance),
				),
				title=_("Attendance Already Generated"),
			)

	def on_submit(self):
		# installed HRMS v16 has no on_submit on the core class; guard in case a
		# future release adds one
		parent = getattr(super(), "on_submit", None)
		if callable(parent):
			parent()
		self.resync_employee_checkins()

	def on_cancel(self):
		# core on_cancel still runs validate_employee_checkin (ours, via MRO) and
		# validate_attendance (core's, untouched)
		super().on_cancel()
		self.resync_employee_checkins()

	def get_resyncable_checkins(self) -> list[str]:
		filters = {
			"employee": self.employee,
			"attendance": ("is", "not set"),
		}
		if self.end_date:
			filters["time"] = ("between", [self.start_date, self.end_date])
		else:
			filters["time"] = (">=", self.start_date)
		return frappe.get_all("Employee Checkin", filters=filters, pluck="name", order_by="time asc")

	def resync_employee_checkins(self):
		"""Re-run standard fetch_shift on unprocessed checkins in this
		assignment's range so they follow the currently active assignment."""
		if self.flags.skip_checkin_resync:
			return
		checkins = self.get_resyncable_checkins()
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
