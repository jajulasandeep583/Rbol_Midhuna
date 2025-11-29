import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_link_to_form
from datetime import timedelta
import hrms
from hrms.hr.doctype.shift_assignment.shift_assignment import has_overlapping_timings
from hrms.hr.utils import share_doc_with_approver, validate_active_employee
from hrms.mixins.pwa_notifications import PWANotificationsMixin


class OverlappingShiftRequestError(frappe.ValidationError):
	pass


class CustomShiftRequest(Document, PWANotificationsMixin):

	def validate(self):
		validate_active_employee(self.employee)
		self.validate_from_to_dates("from_date", "to_date")
		self.validate_overlapping_shift_requests()
		self.validate_approver()
		self.validate_default_shift()

	def on_update(self):
		share_doc_with_approver(self, self.approver)
		self.notify_approval_status()
		self.publish_update()

		if self.docstatus == 0 and self.status == "Approved":
			frappe.msgprint("Shift Request auto-submitted because status is Approved.")
			self.submit()
			return

	def after_delete(self):
		self.publish_update()

	def after_insert(self):
		self.notify_approver()

	def publish_update(self):
		employee_user = frappe.db.get_value("Employee", self.employee, "user_id", cache=True)
		hrms.refetch_resource("hrms:my_shift_requests", employee_user)
		hrms.refetch_resource("hrms:team_shift_requests")

	def on_submit(self):
		if self.status not in ["Approved", "Rejected"]:
			frappe.throw(_("Only Shift Request with status 'Approved' or 'Rejected' can be submitted"))

		if self.status == "Rejected":
			return

		employee = self.employee
		shift_type = self.shift_type
		req_date = frappe.utils.getdate(self.from_date)
		req_end = frappe.utils.getdate(self.to_date)

		if req_date != req_end:
			frappe.throw("Shift Request should be only for one date.")

		old_assignments = frappe.get_all(
			"Shift Assignment",
			filters={
				"employee": employee,
				"start_date": ("<=", req_date),
				"end_date": (">=", req_date),
				"docstatus": 1
			},
			fields=["name", "start_date", "end_date"]
		)

		for old in old_assignments:
			old_doc = frappe.get_doc("Shift Assignment", old.name)
			start = frappe.utils.getdate(old.start_date)
			end = frappe.utils.getdate(old.end_date)
			old_doc.cancel()

			if start < req_date:
				part1 = frappe.get_doc({
					"doctype": "Shift Assignment",
					"employee": employee,
					"company": self.company,
					"shift_type": old_doc.shift_type,
					"start_date": start,
					"end_date": req_date - timedelta(days=1)
				})
				part1.insert(ignore_permissions=True)
				part1.submit()

			if end > req_date:
				part2 = frappe.get_doc({
					"doctype": "Shift Assignment",
					"employee": employee,
					"company": self.company,
					"shift_type": old_doc.shift_type,
					"start_date": req_date + timedelta(days=1),
					"end_date": end
				})
				part2.insert(ignore_permissions=True)
				part2.submit()

		new_assignment = frappe.get_doc({
			"doctype": "Shift Assignment",
			"employee": employee,
			"company": self.company,
			"shift_type": shift_type,
			"start_date": req_date,
			"end_date": req_date,
			"shift_request": self.name
		})
		new_assignment.insert(ignore_permissions=True)
		new_assignment.submit()

		frappe.msgprint(
			f"Shift updated to '{shift_type}' for {req_date} without affecting remaining dates."
		)

	def on_cancel(self):
		shift_assignment_list = frappe.db.get_all(
			"Shift Assignment",
			{"employee": self.employee, "shift_request": self.name, "docstatus": 1}
		)
		for shift in shift_assignment_list:
			shift_assignment_doc = frappe.get_doc("Shift Assignment", shift["name"])
			shift_assignment_doc.cancel()

	def validate_default_shift(self):
		default_shift = frappe.get_value("Employee", self.employee, "default_shift")
		if self.shift_type == default_shift:
			frappe.throw(
				_("You can not request for your Default Shift: {0}").format(frappe.bold(self.shift_type))
			)

	def validate_approver(self):
		department = frappe.get_value("Employee", self.employee, "department")
		shift_approver = frappe.get_value("Employee", self.employee, "shift_request_approver")
		approvers = frappe.db.sql(
			"""select approver from `tabDepartment Approver` 
			   where parent= %s and parentfield = 'shift_request_approver'""",
			(department),
		)
		approver_list = [a[0] for a in approvers]
		approver_list.append(shift_approver)

		if self.approver not in approver_list:
			frappe.throw(_("Only Approvers can Approve this Request."))

	def validate_overlapping_shift_requests(self):
		overlapping_dates = self.get_overlapping_dates()
		if overlapping_dates:
			for d in overlapping_dates:
				if has_overlapping_timings(self.shift_type, d.shift_type):
					self.throw_overlap_error(d)

	def get_overlapping_dates(self):
		if not self.name:
			self.name = "New Shift Request"

		shift = frappe.qb.DocType("Shift Request")
		query = (
			frappe.qb.from_(shift)
			.select(shift.name, shift.shift_type)
			.where(
				(shift.employee == self.employee)
				& (shift.docstatus < 2)
				& (shift.name != self.name)
				& ((shift.to_date >= self.from_date) | (shift.to_date.isnull()))
			)
		)

		if self.to_date:
			query = query.where(shift.from_date <= self.to_date)

		return query.run(as_dict=True)

	def throw_overlap_error(self, shift_details):
		shift_details = frappe._dict(shift_details)
		msg = _(
			"Employee {0} has already applied for Shift {1}: {2} that overlaps within this period"
		).format(
			frappe.bold(self.employee),
			frappe.bold(shift_details.shift_type),
			get_link_to_form("Shift Request", shift_details.name),
		)
		frappe.throw(msg, title=_("Overlapping Shift Requests"), exc=OverlappingShiftRequestError)
