app_name = "rbol"
app_title = "rbol_midhuna"
app_publisher = "Harish Ankalla"
app_description = "This was created by Harish"
app_email = "harish.ankalla25@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "rbol",
# 		"logo": "/assets/rbol/logo.png",
# 		"title": "rbol_midhuna",
# 		"route": "/rbol",
# 		"has_permission": "rbol.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/rbol/css/rbol.css"
# app_include_js = "/assets/rbol/js/rbol.js"

# include js, css files in header of web template
# web_include_css = "/assets/rbol/css/rbol.css"
# web_include_js = "/assets/rbol/js/rbol.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "rbol/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "rbol/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "rbol.utils.jinja_methods",
# 	"filters": "rbol.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "rbol.install.before_install"
# after_install = "rbol.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "rbol.uninstall.before_uninstall"
# after_uninstall = "rbol.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "rbol.utils.before_app_install"
# after_app_install = "rbol.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "rbol.utils.before_app_uninstall"
# after_app_uninstall = "rbol.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "rbol.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Restricted warehouse ("Central Location - RBOL" -> DGM Finance only).
# Covers list views, link pickers, /api/resource and report-builder views.
permission_query_conditions = {
	"Warehouse": "rbol.overrides.permissions.warehouse_query",
	"Stock Ledger Entry": "rbol.overrides.permissions.stock_ledger_entry_query",
	"Bin": "rbol.overrides.permissions.bin_query",
}

# DocType Class
# ---------------
# Override standard doctype classes
override_doctype_class = {
    "Shift Request": "rbol.custom_shift_request.CustomShiftRequest",
    "Shift Assignment": "rbol.custom_shift_assignment.CustomShiftAssignment",
}

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events
# NOTE: on_submit is already handled by CustomShiftRequest class override
# Commenting out to avoid double processing
# doc_events = {
#     "Shift Request": {
#         "on_submit": "rbol.shift_request_utils.handle_shift_update"
#     }
# }

doc_events = {
	"Stock Ledger Entry": {
		"before_insert": "rbol.overrides.permissions.block_restricted_warehouse",
	},
}

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"rbol.tasks.all"
# 	],
# 	"daily": [
# 		"rbol.tasks.daily"
# 	],
# 	"hourly": [
# 		"rbol.tasks.hourly"
# 	],
# 	"weekly": [
# 		"rbol.tasks.weekly"
# 	],
# 	"monthly": [
# 		"rbol.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "rbol.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "rbol.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "rbol.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Overriding Methods
# ------------------
# Script reports build their own SQL, so a Permission Query never reaches them.
# Filter the rows on the way out instead — one seam covers every report.
override_whitelisted_methods = {
	"frappe.desk.query_report.run": "rbol.overrides.report_filter.run",
}

# Request Events
# ----------------
# `_export_query` calls the module-level `query_report.run` directly, so the
# override above does not reach CSV/Excel export or report-backed dashboard
# charts. Wrapping it here does. Idempotent, and re-checks the user per call.
before_request = ["rbol.overrides.report_filter.install_report_filter"]
# after_request = ["rbol.utils.after_request"]

# Job Events
# ----------
before_job = ["rbol.overrides.report_filter.install_report_filter"]
# after_job = ["rbol.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"rbol.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# RBOL Roster (vendored HRMS v16.7.1 roster frontend + API, served at /roster,
# independent of the installed HRMS version)
website_route_rules = [
	{"from_route": "/roster", "to_route": "roster"},
	{"from_route": "/roster/<path:app_path>", "to_route": "roster"},
]

website_redirects = [
	{"source": "/roster-rbol", "target": "/roster"},
]
