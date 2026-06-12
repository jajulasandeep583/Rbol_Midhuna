"""Self-diagnostics for the RBOL roster page (/roster).

Run on any site:  bench --site <site> execute rbol.doctor.run

Checks every link in the chain (app installed -> route rule -> www page ->
built assets -> served assets -> rbol roster API -> page render) and prints
the exact fix for anything broken.
"""

import os
import re

import frappe

OK = "\033[92mPASS\033[0m"
BAD = "\033[91mFAIL\033[0m"

ROSTER_API_FUNCS = [
	"get_events",
	"insert_shift",
	"break_shift",
	"swap_shift",
	"get_default_company",
	"get_schedule_from_assignment",
	"create_shift_schedule_assignment",
	"delete_shift_schedule_assignment",
]

# doctypes the vendored API reads/writes — these come from HRMS, which only
# needs to be installed; its python code version no longer matters
ROSTER_DOCTYPES = [
	"Shift Assignment",
	"Shift Type",
	"Shift Schedule",
	"Shift Schedule Assignment",
	"Leave Application",
]


def run():
	passed, failed = 0, 0

	def check(label, ok, fix=""):
		nonlocal passed, failed
		print(f"[{OK if ok else BAD}] {label}")
		if not ok:
			failed += 1
			if fix:
				print(f"       FIX: {fix}")
		else:
			passed += 1
		return ok

	bench_path = frappe.utils.get_bench_path()
	app_path = frappe.get_app_path("rbol")  # .../apps/rbol/rbol

	# 1. app installed on this site
	check(
		"rbol installed on this site",
		"rbol" in frappe.get_installed_apps(),
		"bench --site {} install-app rbol".format(frappe.local.site),
	)

	# 2. route rules loaded from hooks
	rules = frappe.get_hooks("website_route_rules") or []
	has_rule = any((r.get("from_route") or "") == "/roster" for r in rules)
	check(
		"website_route_rules has /roster",
		has_rule,
		"old app code OR stale cache: cd apps/rbol && git pull, then "
		"bench --site {} clear-cache && bench restart".format(frappe.local.site),
	)
	redirects = frappe.get_hooks("website_redirects") or []
	check(
		"old /roster-rbol link redirects to /roster",
		any((r.get("source") or "") == "/roster-rbol" for r in redirects),
		"cd apps/rbol && git pull, then clear-cache && bench restart",
	)

	# 3. www page + controller in the app
	www_html = os.path.join(app_path, "www", "roster.html")
	check("www/roster.html exists", os.path.exists(www_html), "cd apps/rbol && git pull")
	check(
		"www/roster.py exists",
		os.path.exists(os.path.join(app_path, "www", "roster.py")),
		"cd apps/rbol && git pull",
	)

	# 4. built bundle in the app matches what the page asks for
	js_ref = None
	if os.path.exists(www_html):
		with open(www_html) as f:
			m = re.search(r"assets/(index-[\w-]+\.js)", f.read())
			js_ref = m.group(1) if m else None
	check("page references a built js bundle", bool(js_ref), "cd apps/rbol/roster && yarn install && yarn build")
	app_js = os.path.join(app_path, "public", "roster", "assets", js_ref or "x")
	check(
		"referenced bundle exists in app (public/roster)",
		bool(js_ref) and os.path.exists(app_js),
		"git pull brings prebuilt assets; or rebuild: cd apps/rbol/roster && yarn install && yarn build",
	)

	# 5. served assets (sites/assets) match the app build — production nginx serves these
	served_js = os.path.join(bench_path, "sites", "assets", "rbol", "roster", "assets", js_ref or "x")
	check(
		"bundle reachable under sites/assets (what nginx serves)",
		bool(js_ref) and os.path.exists(served_js),
		"bench build --app rbol   (most common cause of blank page on production)",
	)

	# 6. rbol's own roster backend (vendored — no hrms.api dependency)
	try:
		import rbol.api.roster as roster_api

		missing = [f for f in ROSTER_API_FUNCS if not hasattr(roster_api, f)]
		check(
			"rbol.api.roster has all functions the UI calls",
			not missing,
			"cd apps/rbol && git pull (missing: {})".format(", ".join(missing)),
		)
	except Exception as e:
		check("rbol.api.roster importable", False, f"import failed: {e} — cd apps/rbol && git pull && bench restart")
	try:
		import rbol.api as rbol_api

		check(
			"rbol.api.get_current_user_info exists (login check)",
			hasattr(rbol_api, "get_current_user_info"),
			"cd apps/rbol && git pull && bench restart",
		)
	except Exception as e:
		check("rbol.api importable", False, f"import failed: {e}")

	# 7. the doctypes the API uses must exist (they ship with HRMS — any version)
	missing_dt = [dt for dt in ROSTER_DOCTYPES if not frappe.db.exists("DocType", dt)]
	check(
		"shift/leave doctypes exist (from HRMS, any version)",
		not missing_dt,
		"install HRMS on this site: bench --site {} install-app hrms (missing: {})".format(
			frappe.local.site, ", ".join(missing_dt)
		),
	)

	# 8. real render of the roster page through frappe's website renderer
	# (rendered by www name; the /roster route itself is check #2 —
	# it needs a live HTTP request context that bench execute doesn't have)
	try:
		from frappe.website.serve import get_response_content

		frappe.set_user("Administrator")
		html = get_response_content("roster")
		ok = bool(js_ref) and js_ref in (html or "")
		check(
			"roster page renders the built shell",
			ok,
			"bench --site {} clear-cache && bench --site {} clear-website-cache && bench restart".format(
				frappe.local.site, frappe.local.site
			),
		)
	except Exception as e:
		check("roster page renders the built shell", False, f"render failed: {e} — clear-cache + restart, then re-run")

	print(f"\n{passed} passed, {failed} failed")
	if failed == 0:
		print("All green. Open /roster — if the browser still shows an old/broken page: hard refresh (Ctrl+Shift+R) or try an incognito window.")
