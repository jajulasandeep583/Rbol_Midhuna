"""Company heading on top of every report's Excel export.

An exported report used to start straight at the column titles, so the file
looked hand-typed. Every Excel export now starts with the company name and
address, the report name, the period and who generated it when:

	RADICAL BIO ORGANICS LIMITED
	Survey No. 36 38 41, 43, Yalal Road, Jakkepally
	Vikarabad, Telangana - 501144
	GSTIN: 36AAECR6026Q1ZV
	Debtors Summary
	As on 27-Nov-2026
	Generated on 27-Nov-2026 16:45 by Administrator

`frappe.desk.query_report.build_xlsx_data` already knows how to put rows above
the table (the "Include filters" tick-box of the export window), and keeps the
styling of the rows below in step. The heading is fed through that same path,
so the table, its number formats and the group colours are untouched.

Only the Excel file changes. CSV exports stay as plain data, because a heading
would break anything that reads the file. The screen and PDF are not touched.

If anything goes wrong while building the heading the export falls back to the
plain file - an export must never fail because of its heading.
"""

import frappe
from frappe.desk import query_report
from frappe.utils import cint, formatdate, getdate, now_datetime

DATE_FORMAT = "dd-MMM-yyyy"

# filter names reports use for their period, tried in this order
RANGE_FILTERS = (
	("from_date", "to_date"),
	("period_start_date", "period_end_date"),
	("start_date", "end_date"),
	("from_posting_date", "to_posting_date"),
)
AS_ON_FILTERS = ("as_on_date", "report_date", "to_date", "posting_date", "date")

TITLE_STYLE = {"bold": True, "font_size": 14}
PLAIN_STYLE = {"bold": False}
REPORT_STYLE = {"bold": True, "font_size": 12}
NOTE_STYLE = {"bold": False, "italic": True, "font_color": "#595959"}


def _date(value):
	try:
		return formatdate(getdate(value), DATE_FORMAT)
	except Exception:
		return None


def get_company(filters):
	company = filters.get("company")
	if isinstance(company, list):
		company = company[0] if len(company) == 1 else None
	if company and frappe.db.exists("Company", company):
		return company

	company = frappe.defaults.get_user_default("Company")
	if company and frappe.db.exists("Company", company):
		return company

	companies = frappe.get_all("Company", pluck="name", limit=2)
	return companies[0] if len(companies) == 1 else None


def get_address_lines(company):
	rows = frappe.db.sql(
		"""
		select a.address_line1, a.address_line2, a.city, a.state, a.pincode
		from `tabAddress` a
		join `tabDynamic Link` l on l.parent = a.name and l.parenttype = 'Address'
		where l.link_doctype = 'Company' and l.link_name = %s and ifnull(a.disabled, 0) = 0
		order by a.is_your_company_address desc, a.is_primary_address desc, a.creation
		limit 1
		""",
		company,
		as_dict=True,
	)
	if not rows:
		return []

	a = rows[0]
	street = ", ".join(p.strip().rstrip(",") for p in (a.address_line1, a.address_line2) if p and p.strip())
	town = ", ".join(p.strip() for p in (a.city, a.state) if p and p.strip())
	if a.pincode:
		town = (town + " - " + a.pincode.strip()) if town else a.pincode.strip()

	return [line for line in (street, town) if line]


def get_period_line(filters):
	if filters.get("filter_based_on") == "Fiscal Year" and filters.get("from_fiscal_year"):
		start = frappe.db.get_value("Fiscal Year", filters.get("from_fiscal_year"), "year_start_date")
		end = frappe.db.get_value(
			"Fiscal Year", filters.get("to_fiscal_year") or filters.get("from_fiscal_year"), "year_end_date"
		)
		if start and end:
			return f"{_date(start)} to {_date(end)}"

	for start_key, end_key in RANGE_FILTERS:
		start, end = _date(filters.get(start_key)), _date(filters.get(end_key))
		if filters.get(start_key) and filters.get(end_key) and start and end:
			return f"{start} to {end}"

	for key in AS_ON_FILTERS:
		if filters.get(key) and _date(filters.get(key)):
			return f"As on {_date(filters.get(key))}"

	if filters.get("fiscal_year"):
		return f"Fiscal Year {filters.get('fiscal_year')}"

	return None


def get_header_lines(data):
	"""Return the heading as a list of (text, style) rows, top to bottom."""
	filters = data.get("filters") or {}
	if isinstance(filters, str):
		filters = frappe.parse_json(filters) or {}
	if not isinstance(filters, dict):
		filters = {}

	lines = []

	company = get_company(filters)
	if company:
		company_name, gstin = frappe.db.get_value("Company", company, ["company_name", "gstin"]) or (company, None)
		lines.append(((company_name or company).upper(), TITLE_STYLE))
		lines += [(line, PLAIN_STYLE) for line in get_address_lines(company)]
		if gstin:
			lines.append((f"GSTIN: {gstin}", PLAIN_STYLE))

	lines.append((data.get("report_name") or "Report", REPORT_STYLE))

	period = get_period_line(filters)
	if period:
		lines.append((period, PLAIN_STYLE))

	user = frappe.utils.get_fullname(frappe.session.user) or frappe.session.user
	lines.append((f"Generated on {now_datetime().strftime('%d-%b-%Y %H:%M')} by {user}", NOTE_STYLE))

	# the rows travel as a dict, so each text has to be different
	seen, unique = set(), []
	for text, style in lines:
		if text and text not in seen:
			seen.add(text)
			unique.append((text, style))

	return unique


def build_with_header(original, data, kwargs):
	lines = get_header_lines(data)
	if not lines:
		return original(data, **kwargs)

	user_filters = data.get("applied_filters") if cint(kwargs.get("include_filters")) else None

	# a value has to be non-empty or the row is skipped; it is blanked again below
	applied = {text: " " for text, _style in lines}
	for key, value in (user_filters or {}).items():
		if value and key not in applied:
			applied[key] = value

	data["applied_filters"] = applied
	try:
		result, column_widths, styles = original(data, **{**kwargs, "include_filters": 1})
	finally:
		data["applied_filters"] = user_filters

	for row_idx, (text, style) in enumerate(lines):
		if result[row_idx] and result[row_idx][0] == text:
			result[row_idx] = [text]  # one cell, so long text runs across the sheet
			if styles:
				styles["styles"].append(style)
				styles["cell_styles"].setdefault((row_idx, 0), []).append(len(styles["styles"]) - 1)

	return result, column_widths, styles


def install_export_header(*args, **kwargs):
	"""Idempotent; called from `before_request` and `before_job`."""
	if getattr(query_report.build_xlsx_data, "_rbol_export_header", False):
		return

	original = query_report.build_xlsx_data

	def wrapped_build_xlsx_data(data, *a, **kw):
		# CSV (no styles) and any caller using positional arguments get the standard file
		if a or not kw.get("build_styles"):
			return original(data, *a, **kw)

		try:
			return build_with_header(original, data, kw)
		except Exception:
			frappe.log_error(title="Report Excel heading failed, plain file exported")
			return original(data, **kw)

	wrapped_build_xlsx_data._rbol_export_header = True
	wrapped_build_xlsx_data.__name__ = getattr(original, "__name__", "build_xlsx_data")
	wrapped_build_xlsx_data.__doc__ = getattr(original, "__doc__", None)

	query_report.build_xlsx_data = wrapped_build_xlsx_data
