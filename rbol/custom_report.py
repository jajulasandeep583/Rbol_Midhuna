# Copyright (c) 2026, MIDHUNATECH
# Excel export of Trial Balance, Balance Sheet and Profit and Loss: groups look
# different from ledgers.
#
# Frappe 16.60 builds the Excel styles for a report through
# Report.get_xlsx_styles_from_module(), which only looks for a get_xlsx_styles()
# in the report's own module (erpnext here, which has none for Trial Balance).
# This override adds the styling for the reports listed below and leaves every
# other report exactly as Frappe exports it.
#
# In the file:
#   - group accounts: bold, and each level of the tree has its own look so nested
#     groups can be told apart: level 1 dark blue fill, level 2 light blue,
#     level 3 grey, level 4 bold italic, level 5 and deeper bold italic underlined
#   - ledger accounts: normal text
#   - every row indented by its level, even when "Include indentation" is not ticked
# Only the look of the Excel file changes; figures and columns are untouched.

from frappe.core.doctype.report.report import Report
from frappe.utils import cint

# these reports mark group rows: Trial Balance with is_group_account, the others with is_group
STYLED_REPORTS = {"Trial Balance", "Balance Sheet", "Profit and Loss Statement"}

GROUP_LEVELS = [
	{"bold": True, "bg_color": "#BDD7EE"},  # level 1: Application of Funds, Source of Funds, Income, Expenses
	{"bold": True, "bg_color": "#DDEBF7"},  # level 2: Current Assets, Loans (Liability) ...
	{"bold": True, "bg_color": "#EDEDED"},  # level 3: Bank Accounts, Bank OD A/c ...
	{"bold": True, "italic": True},  # level 4
	{"bold": True, "italic": True, "underline": 1},  # level 5 and deeper
]


class CustomReport(Report):
	def get_xlsx_styles_from_module(self, metadata):
		styles = super().get_xlsx_styles_from_module(metadata)
		if styles or self.name not in STYLED_REPORTS:
			return styles
		return get_group_ledger_styles(metadata)


def get_group_ledger_styles(metadata):
	from frappe.utils.xlsxutils import XLSXStyleBuilder

	builder = XLSXStyleBuilder(metadata)  # Frappe's normal styles: header, number formats, total row
	if not builder.row_is_dict:
		return builder.result

	if not metadata.has_indentation:
		builder.apply_indentations()

	level_ids = [builder.register_style(style) for style in GROUP_LEVELS]
	columns = list(metadata.column_map.keys())

	for row_idx, row in metadata.row_map.items():
		if not (row.get("is_group_account") or row.get("is_group")):
			continue
		indent = cint(row.get("indent"))
		style_id = level_ids[min(indent, len(level_ids) - 1)]
		# style cell by cell, so the fill stops at the last column instead of running across the sheet
		for col_idx in columns:
			builder.style_cell(row_idx, col_idx, style_id)

	return builder.result
