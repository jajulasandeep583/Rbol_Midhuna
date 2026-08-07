"""Warehouse-level access control for RBOL.

`Central Location - RBOL` holds stock that only the DGM Finance team is allowed
to see or transact in. Two Server Scripts used to do this (`Warehouse
Permission` + `Permission Query-warehouse`); they are replaced by this module
because a Permission Query only constrains list views / `get_list` — script
reports (Stock Ledger, Stock Balance, ...) build their own SQL and were never
covered by it. See `rbol.overrides.report_filter` for the report side.
"""

import frappe

RESTRICTED_WAREHOUSE = "Central Location - RBOL"
ALLOWED_ROLE = "DGM Finance"


def has_access(user: str | None = None) -> bool:
	"""True when `user` may see/transact in the restricted warehouse."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return ALLOWED_ROLE in frappe.get_roles(user)


def _condition(table: str, field: str, user: str | None) -> str:
	if has_access(user):
		return ""
	return "(`tab{0}`.`{1}` is null or `tab{0}`.`{1}` != {2})".format(
		table, field, frappe.db.escape(RESTRICTED_WAREHOUSE)
	)


# --- permission_query_conditions hooks -------------------------------------
# Applied to list views, link searches, /api/resource and report-builder views.


def warehouse_query(user=None, doctype=None):
	return _condition("Warehouse", "name", user)


def stock_ledger_entry_query(user=None, doctype=None):
	return _condition("Stock Ledger Entry", "warehouse", user)


def bin_query(user=None, doctype=None):
	return _condition("Bin", "warehouse", user)


# --- doc event -------------------------------------------------------------


def block_restricted_warehouse(doc, method=None):
	"""Stop anyone without the role from moving stock into/out of the warehouse."""
	if doc.get("warehouse") == RESTRICTED_WAREHOUSE and not has_access():
		frappe.throw(
			frappe._("Only {0} can transact in {1}").format(ALLOWED_ROLE, RESTRICTED_WAREHOUSE),
			title=frappe._("Not Permitted"),
		)
