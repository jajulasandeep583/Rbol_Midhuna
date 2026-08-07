# Installs "Stock Summary" as a DB-stored (non-standard) Script Report so the
# Python and client code live inside the Report document itself (visible and
# editable in the UI, and carried with the database). Idempotent — safe to run
# on every migrate. Wired via rbol/patches.txt.
import os

import frappe

REPORT = "Stock Summary"
ROLES = ["System Manager", "Stock Manager", "Stock User", "Accounts Manager", "Accounts User"]


def install():
	folder = os.path.dirname(__file__)
	with open(os.path.join(folder, "report_script.py"), encoding="utf-8") as f:
		script = f.read()
	with open(os.path.join(folder, "report_script.js"), encoding="utf-8") as f:
		js = f.read()

	if frappe.db.exists("Report", REPORT):
		# raw write first so the normal save passes the "cannot edit a standard
		# report" guard when an older standard copy is present.
		frappe.db.set_value("Report", REPORT, "is_standard", "No", update_modified=False)
		frappe.db.commit()
		doc = frappe.get_doc("Report", REPORT)
	else:
		doc = frappe.new_doc("Report")
		doc.report_name = REPORT
		for role in ROLES:
			doc.append("roles", {"role": role})

	doc.report_type = "Script Report"
	doc.is_standard = "No"
	doc.module = "Stock"
	doc.ref_doctype = "Stock Ledger Entry"
	doc.disabled = 0
	doc.prepared_report = 0
	doc.report_script = script
	doc.javascript = js
	doc.query = ""
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	frappe.clear_cache()


def execute():
	"""Patch entry point — frappe calls <patchmodule>.execute()."""
	install()
