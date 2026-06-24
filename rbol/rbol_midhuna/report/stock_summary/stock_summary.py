# Copyright (c) 2026, Midhuna Tech and contributors
# Tally-style Stock Summary: Warehouse tree -> Item Group tree -> Item -> Stock Ledger drill-down
import frappe
from frappe.utils import flt, nowdate

METRICS = (
	"opening_qty", "opening_val",
	"in_qty", "in_val",
	"out_qty", "out_val",
	"close_qty", "close_val",
)


def _zero():
	return {k: 0.0 for k in METRICS}


def _add(dst, src):
	for k in METRICS:
		dst[k] += flt(src.get(k))


def execute(filters=None):
	filters = frappe._dict(filters or {})
	to_date = filters.get("to_date") or nowdate()
	company = filters.get("company") or frappe.db.get_default("Company")
	from_date = filters.get("from_date")
	if not from_date:
		fy_start = frappe.db.get_value(
			"Fiscal Year",
			{"year_start_date": ("<=", to_date), "year_end_date": (">=", to_date)},
			"year_start_date",
		)
		from_date = str(fy_start) if fy_start else to_date

	columns = _columns()
	data = _stock_data(company, from_date, to_date, filters)

	items_by_wh = {}
	for r in data:
		items_by_wh.setdefault(r["warehouse"], []).append(r)

	# ---- Item Group tree (shared) ----
	ig_list = frappe.db.sql(
		"select name, parent_item_group from `tabItem Group` order by lft", as_dict=True
	)
	ig_order = [g["name"] for g in ig_list]
	ig_parent = {g["name"]: (g["parent_item_group"] or "") for g in ig_list}
	ig_children = {}
	for g in ig_list:
		p = g["parent_item_group"] or ""
		if p:
			ig_children.setdefault(p, []).append(g["name"])

	# ---- Warehouse tree ----
	wh_list = frappe.db.sql(
		"select name, parent_warehouse, is_group from `tabWarehouse` where company=%s order by lft",
		company, as_dict=True,
	)
	wh_order = [w["name"] for w in wh_list]
	wh_parent = {w["name"]: (w["parent_warehouse"] or "") for w in wh_list}
	wh_children = {}
	for w in wh_list:
		p = w["parent_warehouse"] or ""
		if p:
			wh_children.setdefault(p, []).append(w["name"])

	# warehouses appearing in data but missing from tree (safety)
	for whn in items_by_wh:
		if whn not in wh_parent:
			wh_parent[whn] = ""
			wh_order.append(whn)

	# ---- Aggregate warehouse totals bottom-up ----
	wh_agg, wh_has = {}, {}
	for name in reversed(wh_order):
		agg = _zero()
		hd = False
		for it in items_by_wh.get(name, []):
			_add(agg, it)
			hd = True
		for ch in wh_children.get(name, []):
			if wh_has.get(ch):
				_add(agg, wh_agg[ch])
				hd = True
		wh_agg[name] = agg
		wh_has[name] = hd

	rows = []
	counter = [0]

	def emit_item_groups(wh_rid, wh_indent, items):
		items_by_group = {}
		for it in items:
			items_by_group.setdefault(it.get("item_group") or "Ungrouped", []).append(it)

		g_agg, g_has = {}, {}
		for name in reversed(ig_order):
			agg = _zero()
			hd = False
			for it in items_by_group.get(name, []):
				_add(agg, it)
				hd = True
			for ch in ig_children.get(name, []):
				if g_has.get(ch):
					_add(agg, g_agg[ch])
					hd = True
			g_agg[name] = agg
			g_has[name] = hd

		base = wh_indent + 1
		ginfo = {}  # group name -> (rid, depth)
		for name in ig_order:
			if name == "All Item Groups" or not g_has.get(name):
				continue
			pg = ig_parent.get(name)
			pinfo = ginfo.get(pg)
			if pinfo:
				parent_rid, eff_depth = pinfo[0], pinfo[1] + 1
			else:
				parent_rid, eff_depth = wh_rid, 0
			counter[0] += 1
			rid = "G" + str(counter[0])
			ginfo[name] = (rid, eff_depth)
			rows.append(_node(rid, parent_rid, name, g_agg[name], base + eff_depth, "group"))
			for it in sorted(items_by_group.get(name, []), key=lambda x: (x.get("item_name") or x.get("item_code") or "")):
				counter[0] += 1
				irid = "I" + str(counter[0])
				label = it.get("item_name") or it.get("item_code")
				if it.get("item_name") and it.get("item_code") and it.get("item_name") != it.get("item_code"):
					label = "%s (%s)" % (it.get("item_name"), it.get("item_code"))
				node = _node(irid, rid, label, it, base + eff_depth + 1, "item")
				node["item_code"] = it.get("item_code")
				node["warehouse"] = it.get("warehouse")
				rows.append(node)

	def emit_wh(name, parent_rid, indent):
		if not wh_has.get(name):
			return
		counter[0] += 1
		rid = "W" + str(counter[0])
		rows.append(_node(rid, parent_rid, name, wh_agg[name], indent, "warehouse"))
		if items_by_wh.get(name):
			emit_item_groups(rid, indent, items_by_wh[name])
		for ch in wh_children.get(name, []):
			emit_wh(ch, rid, indent + 1)

	for name in wh_order:
		if not (wh_parent.get(name) or ""):
			emit_wh(name, None, 0)

	# ---- summary cards ----
	tot = _zero()
	for it in data:
		_add(tot, it)
	report_summary = [
		{"value": tot["opening_val"], "label": "Opening Value", "datatype": "Currency", "currency": "INR", "indicator": "grey"},
		{"value": tot["in_val"], "label": "Inward Value", "datatype": "Currency", "currency": "INR", "indicator": "blue"},
		{"value": tot["out_val"], "label": "Outward Value", "datatype": "Currency", "currency": "INR", "indicator": "orange"},
		{"value": tot["close_val"], "label": "Closing Value", "datatype": "Currency", "currency": "INR", "indicator": "green"},
	]
	return columns, rows, None, None, report_summary


def _node(rid, parent_rid, label, src, indent, node_type):
	return {
		"row_id": rid,
		"parent_id": parent_rid,
		"node_type": node_type,
		"label": label,
		"opening_qty": flt(src.get("opening_qty")),
		"opening_val": flt(src.get("opening_val")),
		"in_qty": flt(src.get("in_qty")),
		"in_val": flt(src.get("in_val")),
		"out_qty": flt(src.get("out_qty")),
		"out_val": flt(src.get("out_val")),
		"close_qty": flt(src.get("close_qty")),
		"close_val": flt(src.get("close_val")),
		"indent": indent,
	}


def _stock_data(company, from_date, to_date, filters):
	cond = ""
	params = {"fd": from_date, "td": to_date, "co": company}
	if filters.get("warehouse"):
		cond += " AND sle.warehouse = %(wh)s"
		params["wh"] = filters.get("warehouse")
	if filters.get("item_group"):
		cond += " AND i.item_group = %(ig)s"
		params["ig"] = filters.get("item_group")
	return frappe.db.sql(
		"""
		SELECT
			sle.warehouse                                                       AS warehouse,
			sle.item_code                                                       AS item_code,
			i.item_name                                                         AS item_name,
			i.item_group                                                        AS item_group,
			i.stock_uom                                                         AS stock_uom,
			SUM(CASE WHEN sle.posting_date < %(fd)s THEN sle.actual_qty ELSE 0 END)                          AS opening_qty,
			SUM(CASE WHEN sle.posting_date < %(fd)s THEN sle.stock_value_difference ELSE 0 END)              AS opening_val,
			SUM(CASE WHEN sle.actual_qty > 0 AND sle.posting_date >= %(fd)s THEN sle.actual_qty ELSE 0 END)  AS in_qty,
			SUM(CASE WHEN sle.actual_qty > 0 AND sle.posting_date >= %(fd)s THEN sle.stock_value_difference ELSE 0 END) AS in_val,
			ABS(SUM(CASE WHEN sle.actual_qty < 0 AND sle.posting_date >= %(fd)s THEN sle.actual_qty ELSE 0 END)) AS out_qty,
			ABS(SUM(CASE WHEN sle.actual_qty < 0 AND sle.posting_date >= %(fd)s THEN sle.stock_value_difference ELSE 0 END)) AS out_val,
			SUM(sle.actual_qty)                                                 AS close_qty,
			SUM(sle.stock_value_difference)                                     AS close_val
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabItem` i ON i.name = sle.item_code
		WHERE sle.is_cancelled = 0
			AND sle.company = %(co)s
			AND sle.posting_date <= %(td)s
			{cond}
		GROUP BY sle.warehouse, sle.item_code
		HAVING ABS(close_qty) > 0.001 OR ABS(opening_qty) > 0.001
			OR ABS(in_qty) > 0.001 OR ABS(out_qty) > 0.001
			OR ABS(close_val) > 0.01 OR ABS(opening_val) > 0.01
			OR ABS(in_val) > 0.01 OR ABS(out_val) > 0.01
		ORDER BY sle.warehouse, i.item_name
		""".format(cond=cond),
		params,
		as_dict=True,
	)


def _columns():
	return [
		{"fieldname": "row_id", "label": "Row ID", "fieldtype": "Data", "hidden": 1},
		{"fieldname": "parent_id", "label": "Parent ID", "fieldtype": "Data", "hidden": 1},
		{"fieldname": "node_type", "label": "Type", "fieldtype": "Data", "hidden": 1},
		{"fieldname": "item_code", "label": "Item Code", "fieldtype": "Data", "hidden": 1},
		{"fieldname": "warehouse", "label": "Warehouse", "fieldtype": "Data", "hidden": 1},
		{"fieldname": "label", "label": "Particulars", "fieldtype": "Data", "width": 360},
		{"fieldname": "opening_qty", "label": "Opening Qty", "fieldtype": "Float", "precision": 3, "width": 110},
		{"fieldname": "opening_val", "label": "Opening Value", "fieldtype": "Currency", "width": 130},
		{"fieldname": "in_qty", "label": "Inward Qty", "fieldtype": "Float", "precision": 3, "width": 110},
		{"fieldname": "in_val", "label": "Inward Value", "fieldtype": "Currency", "width": 130},
		{"fieldname": "out_qty", "label": "Outward Qty", "fieldtype": "Float", "precision": 3, "width": 110},
		{"fieldname": "out_val", "label": "Outward Value", "fieldtype": "Currency", "width": 130},
		{"fieldname": "close_qty", "label": "Closing Qty", "fieldtype": "Float", "precision": 3, "width": 110},
		{"fieldname": "close_val", "label": "Closing Value", "fieldtype": "Currency", "width": 140},
	]
