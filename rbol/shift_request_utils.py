import frappe
from frappe.utils import add_days, getdate

def handle_shift_update(doc, method):
    """
    When a Shift Request is submitted and approved:
    - Cancel all existing Shift Assignments in the date range
    - Create new Shift Assignments for each day
    """

    if doc.status != "Approved":
        return

    employee = doc.employee
    start = getdate(doc.from_date)
    end = getdate(doc.to_date)
    shift_type = doc.shift_type

    current = start
    while current <= end:

        existing = frappe.get_all(
            "Shift Assignment",
            filters={
                "employee": employee,
                "start_date": current,
                "docstatus": 1,
            },
            fields=["name"]
        )

        for s in existing:
            shift_doc = frappe.get_doc("Shift Assignment", s.name)
            shift_doc.cancel()

        # 2. Create new shift for the day
        new_assignment = frappe.get_doc({
            "doctype": "Shift Assignment",
            "employee": employee,
            "shift_type": shift_type,
            "start_date": current,
            "end_date": current
        })

        new_assignment.insert(ignore_permissions=True)
        new_assignment.submit()

        current = add_days(current, 1)

    frappe.msgprint(
        f"Shift updated to '{shift_type}' from {doc.from_date} to {doc.to_date} for {employee}"
    )
