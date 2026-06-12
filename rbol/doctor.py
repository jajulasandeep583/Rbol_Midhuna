"""Self-diagnostics for the roster-rbol page.

Run on any site:  bench --site <site> execute rbol.doctor.run

Checks every link in the chain (app installed -> route rule -> www page ->
built assets -> served assets -> HRMS APIs -> page render) and prints the
exact fix for anything broken.
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
	has_rule = any((r.get("from_route") or "").startswith("/roster-rbol") for r in rules)
	check(
		"website_route_rules has /roster-rbol",
		has_rule,
		"old app code OR stale cache: cd apps/rbol && git pull, then "
		"bench --site {} clear-cache && bench restart".format(frappe.local.site),
	)

	# 3. www page + controller in the app
	www_html = os.path.join(app_path, "www", "roster_rbol.html")
	check("www/roster_rbol.html exists", os.path.exists(www_html), "cd apps/rbol && git pull (must include commit 2d23949+)")
	check(
		"www/roster_rbol.py exists",
		os.path.exists(os.path.join(app_path, "www", "roster_rbol.py")),
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

	# 6. HRMS backend the UI calls
	hrms_ok = check(
		"hrms installed on this site",
		"hrms" in frappe.get_installed_apps(),
		"the roster UI needs HRMS: bench --site {} install-app hrms".format(frappe.local.site),
	)
	if hrms_ok:
		try:
			import hrms.api.roster as roster_api

			missing = [f for f in ROSTER_API_FUNCS if not hasattr(roster_api, f)]
			check(
				"hrms.api.roster has all functions the UI calls",
				not missing,
				"this HRMS version changed/removed: {} — report which, the UI must be adapted".format(", ".join(missing)),
			)
		except Exception as e:
			check("hrms.api.roster importable", False, f"import failed: {e}")
		try:
			import hrms.api as hrms_api

			check(
				"hrms.api.get_current_user_info exists (login check)",
				hasattr(hrms_api, "get_current_user_info"),
				"HRMS version changed this API — UI login check must be adapted",
			)
		except Exception as e:
			check("hrms.api importable", False, f"import failed: {e}")

	# 7. real render of the roster page through frappe's website renderer
	# (rendered by www name; the /roster-rbol hyphen route itself is check #2 —
	# it needs a live HTTP request context that bench execute doesn't have)
	try:
		from frappe.website.serve import get_response_content

		frappe.set_user("Administrator")
		html = get_response_content("roster_rbol")
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
		print("All green. If the browser still shows an old/broken page: hard refresh (Ctrl+Shift+R) or try an incognito window.")
