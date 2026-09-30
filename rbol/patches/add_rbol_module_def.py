# The app's module "Rbol Midhuna" only gets a Module Def at install-app time, and rbol was
# installed before the module held any DocType. Create it before model sync so the
# app's DocTypes/Reports (e.g. Public Holiday Work) can be imported on migrate.
import frappe


def execute():
	if frappe.db.exists("Module Def", "Rbol Midhuna"):
		return
	frappe.get_doc({"doctype": "Module Def", "module_name": "Rbol Midhuna", "app_name": "rbol", "custom": 0}).insert(
		ignore_permissions=True, ignore_if_duplicate=True
	)
