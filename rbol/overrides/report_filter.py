"""Strip restricted-warehouse rows out of every script report.

Every script report — desk view, export, prepared report and report-backed
dashboard chart — ultimately gets its rows from
`frappe.desk.query_report.run`, so filtering there covers Stock Ledger, Stock
Balance, Stock Projected Qty, Stock Analytics and anything added later without
touching a single report file.

Two seams are used, because there are two callers:

* `override_whitelisted_methods` → :func:`run` handles the desk request.
* :func:`install_report_filter` (from `before_request` / `before_job`) wraps the
  module-level `query_report.run`, because `_export_query` calls that name
  directly — an `override_whitelisted_methods` entry alone leaves CSV/Excel
  export, background exports and dashboard charts leaking.

The wrapper re-checks the current user on every call, so it is safe for the
patch to stay installed for the life of the process.
"""

import frappe
from frappe.desk import query_report

from rbol.overrides.permissions import RESTRICTED_WAREHOUSE, has_access

WAREHOUSE_FIELDS = ("warehouse", "s_warehouse", "t_warehouse", "from_warehouse", "to_warehouse")
NUMERIC_FIELDTYPES = {"Currency", "Float", "Int", "Percent"}


def _columns_meta(columns):
	"""Normalise report columns to a list of (fieldname, fieldtype) by position."""
	meta = []
	for col in columns or []:
		if isinstance(col, dict):
			meta.append((col.get("fieldname"), col.get("fieldtype")))
		elif isinstance(col, str):
			# legacy "Label:Fieldtype/Options:Width"
			parts = col.split(":")
			label = parts[0].strip()
			fieldtype = parts[1].split("/")[0].strip() if len(parts) > 1 else "Data"
			meta.append((frappe.scrub(label), fieldtype))
		else:
			meta.append((None, None))
	return meta


def _warehouse_positions(meta):
	return [idx for idx, (fieldname, _ft) in enumerate(meta) if fieldname in WAREHOUSE_FIELDS]


def _is_total_row(row, positions):
	"""Only rows we are *sure* are totals.

	Never guess by position — a report whose last row is ordinary data would
	have its numbers overwritten with the running sum.
	"""
	if isinstance(row, dict):
		if row.get("is_total_row"):
			return True
		if any(row.get(f) for f in WAREHOUSE_FIELDS):
			return False
		label = next((v for v in row.values() if isinstance(v, str)), "")
	elif isinstance(row, list | tuple):
		if positions and any(len(row) > pos and row[pos] for pos in positions):
			return False
		label = row[0] if row and isinstance(row[0], str) else ""
	else:
		return False

	return label.strip().lower().startswith("total")


def _row_is_restricted(row, positions):
	if isinstance(row, dict):
		return any(row.get(f) == RESTRICTED_WAREHOUSE for f in WAREHOUSE_FIELDS)
	if isinstance(row, list | tuple):
		return any(len(row) > pos and row[pos] == RESTRICTED_WAREHOUSE for pos in positions)
	return False


def _recompute_total(total_row, kept_rows, meta):
	"""Re-add a report-embedded total row from the rows that survived.

	Without this the hidden stock still shows up in the total — the number
	itself is a leak.
	"""
	for pos, (fieldname, fieldtype) in enumerate(meta):
		if fieldtype not in NUMERIC_FIELDTYPES:
			continue

		total = 0.0
		for row in kept_rows:
			if isinstance(row, dict):
				value = row.get(fieldname)
			elif isinstance(row, list | tuple) and len(row) > pos:
				value = row[pos]
			else:
				continue
			total += frappe.utils.flt(value)

		if isinstance(total_row, dict):
			if fieldname in total_row:
				total_row[fieldname] = total
		elif isinstance(total_row, list) and len(total_row) > pos:
			total_row[pos] = total

	return total_row


def strip_restricted_rows(result, columns):
	if not result:
		return result

	meta = _columns_meta(columns)
	positions = _warehouse_positions(meta)
	if not positions and not any(
		isinstance(row, dict) and any(f in row for f in WAREHOUSE_FIELDS) for row in result[:5]
	):
		# report has no warehouse column at all — nothing to do
		return result

	kept, totals = [], []
	removed = False

	for row in result:
		if _row_is_restricted(row, positions):
			removed = True
			continue
		if _is_total_row(row, positions):
			totals.append(row)
			continue
		kept.append(row)

	if not removed:
		return result

	for total_row in totals:
		kept.append(_recompute_total(total_row, kept, meta))

	return kept


def filter_report_data(data):
	"""Filter a `query_report.run` payload for the *current* user."""
	if not isinstance(data, dict) or has_access():
		return data

	data["result"] = strip_restricted_rows(data.get("result"), data.get("columns"))
	return data


@frappe.whitelist()
def run(*args, **kwargs):
	"""Whitelisted replacement for `frappe.desk.query_report.run`."""
	return filter_report_data(query_report.run(*args, **kwargs))


# --- module-level patch (covers export / dashboard charts) ------------------

_original_run = None


def install_report_filter(*args, **kwargs):
	"""Idempotent; called from `before_request` and `before_job`."""
	global _original_run

	if getattr(query_report.run, "_rbol_warehouse_filter", False):
		return

	_original_run = query_report.run

	def wrapped_run(*a, **kw):
		return filter_report_data(_original_run(*a, **kw))

	wrapped_run._rbol_warehouse_filter = True
	wrapped_run.__name__ = getattr(_original_run, "__name__", "run")
	wrapped_run.__doc__ = getattr(_original_run, "__doc__", None)

	query_report.run = wrapped_run
