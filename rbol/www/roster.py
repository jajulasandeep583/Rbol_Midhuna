import frappe

no_cache = 1


def get_context(context):
	# Render fresh on every request (no_cache=1) so the CSRF token baked into
	# the page always matches the current session. Without this, Frappe caches
	# the HTML in Redis and serves a stale token after the session rotates,
	# causing intermittent CSRFTokenError on /roster.
	context.csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosemgrep
	return context
