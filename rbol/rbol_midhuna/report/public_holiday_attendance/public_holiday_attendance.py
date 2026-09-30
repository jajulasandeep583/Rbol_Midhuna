# Copyright (c) 2026, Harish Ankalla and contributors
# For license information, please see license.txt

# Who worked on public holidays - from the Public Holiday Work register.
# Attendance only (shift, punches, hours); holiday pay is deliberately left out.

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data), get_summary(data)


def get_columns():
	return [
		{"label": _("Holiday Date"), "fieldname": "holiday_date", "fieldtype": "Date", "width": 105},
		{"label": _("Holiday"), "fieldname": "holiday_name", "fieldtype": "Data", "width": 150},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 150},
		{"label": _("Designation"), "fieldname": "designation", "fieldtype": "Data", "width": 140},
		{"label": _("Grade"), "fieldname": "grade", "fieldtype": "Data", "width": 80},
		{"label": _("Shift"), "fieldname": "shift_type", "fieldtype": "Link", "options": "Shift Type", "width": 130},
		{"label": _("In Time"), "fieldname": "in_time", "fieldtype": "Datetime", "width": 150},
		{"label": _("Out Time"), "fieldname": "out_time", "fieldtype": "Datetime", "width": 150},
		{"label": _("Hours"), "fieldname": "working_hours", "fieldtype": "Float", "precision": 2, "width": 70},
		{"label": _("Status"), "fieldname": "attendance_status", "fieldtype": "Data", "width": 85},
		{"label": _("Attendance"), "fieldname": "attendance", "fieldtype": "Link", "options": "Attendance", "width": 150},
	]


def get_data(filters):
	conditions = {"status": ["!=", "Cancelled"]}
	if filters.from_date and filters.to_date:
		conditions["holiday_date"] = ["between", [filters.from_date, filters.to_date]]
	for field in ("employee", "department", "shift_type", "grade"):
		if filters.get(field):
			conditions[field] = filters.get(field)
	if filters.holiday_name:
		conditions["holiday_name"] = ["like", f"%{filters.holiday_name}%"]
	return frappe.get_all(
		"Public Holiday Work",
		filters=conditions,
		fields=[
			"holiday_date", "holiday_name", "employee", "employee_name", "department", "designation", "grade",
			"shift_type", "in_time", "out_time", "working_hours", "attendance_status", "attendance",
		],
		order_by="holiday_date desc, department asc, employee asc",
	)


def get_summary(data):
	if not data:
		return []
	return [
		{"label": _("Employees Worked"), "value": len({d.employee for d in data}), "indicator": "Blue", "datatype": "Int"},
		{"label": _("Holidays"), "value": len({d.holiday_date for d in data}), "indicator": "Green", "datatype": "Int"},
		{"label": _("Half Days"), "value": sum(1 for d in data if d.attendance_status == "Half Day"), "indicator": "Orange", "datatype": "Int"},
		{"label": _("Total Hours"), "value": flt(sum(flt(d.working_hours) for d in data), 2), "indicator": "Blue", "datatype": "Float"},
	]


def get_chart(data):
	if not data:
		return None
	per_day = {}
	for d in data:
		key = f"{frappe.format(d.holiday_date, 'Date')} {d.holiday_name or ''}".strip()
		per_day[key] = per_day.get(key, 0) + 1
	labels = list(reversed(list(per_day)))
	return {
		"data": {"labels": labels, "datasets": [{"name": _("Employees Worked"), "values": [per_day[k] for k in labels]}]},
		"type": "bar",
		"colors": ["#2490ef"],
	}
