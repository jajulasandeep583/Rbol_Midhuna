# The plant runs on public holidays: let check-ins become attendance on holiday-list
# dates too. HRMS still never marks anyone Absent on a holiday, so employees who are
# not rostered keep their paid holiday.
import frappe


def execute():
	if not frappe.db.has_column("Shift Type", "mark_auto_attendance_on_holidays"):
		return
	frappe.db.sql("update `tabShift Type` set mark_auto_attendance_on_holidays = 1")
