// Copyright (c) 2026, Harish Ankalla and contributors
// For license information, please see license.txt

// Who worked on public holidays (from the Public Holiday Work register).
frappe.query_reports["Public Holiday Attendance"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: `${new Date().getFullYear()}-01-01`,
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: `${new Date().getFullYear()}-12-31`,
			reqd: 1,
		},
		{ fieldname: "holiday_name", label: __("Holiday"), fieldtype: "Data" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "shift_type", label: __("Shift"), fieldtype: "Link", options: "Shift Type" },
		{ fieldname: "grade", label: __("Grade"), fieldtype: "Link", options: "Employee Grade" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
	],
};
