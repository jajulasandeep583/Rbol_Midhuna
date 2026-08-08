// Copyright (c) 2026, MIDHUNATECH
// Adds "Change Shift From Date" to a submitted Shift Assignment.
//
// Why: to move somebody from C to B for tomorrow you would otherwise have to
// cancel the running assignment, and that is blocked the moment last night's
// attendance exists. This action shortens the running assignment to the day
// before instead and raises a new one for the new shift -- days already worked
// are never touched.

frappe.ui.form.on("Shift Assignment", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(__("Change Shift From Date"), () => open_change_shift_dialog(frm));
		frm.page.set_inner_btn_group_as_primary &&
			frm.page.set_inner_btn_group_as_primary(__("Actions"));
	},
});

function open_change_shift_dialog(frm) {
	frappe.call({
		method: "rbol.custom_shift_assignment.get_change_shift_context",
		args: { assignment: frm.doc.name },
		freeze: true,
		callback(r) {
			if (!r.message) return;
			const ctx = r.message;

			const d = new frappe.ui.Dialog({
				title: __("Change Shift From Date"),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "summary",
						options: summary_html(ctx),
					},
					{
						fieldtype: "Date",
						fieldname: "from_date",
						label: __("Change From Date"),
						reqd: 1,
						default: ctx.default_change_date,
						description: __(
							"The employee stays on {0} up to the day before this date, and moves to the new shift from this date onwards.",
							[ctx.shift_type]
						),
					},
					{ fieldtype: "Column Break" },
					{
						fieldtype: "Link",
						fieldname: "new_shift_type",
						label: __("New Shift"),
						options: "Shift Type",
						reqd: 1,
						get_query: () => ({ filters: { name: ["!=", ctx.shift_type] } }),
					},
					{ fieldtype: "Section Break" },
					{
						fieldtype: "Link",
						fieldname: "shift_location",
						label: __("Shift Location"),
						options: "Shift Location",
						default: frm.doc.shift_location,
					},
					{ fieldtype: "Column Break" },
					{
						fieldtype: "Select",
						fieldname: "new_status",
						label: __("Status"),
						options: "Active\nInactive",
						default: frm.doc.status,
					},
				],
				primary_action_label: __("Change Shift"),
				primary_action(values) {
					if (
						ctx.earliest_change_date &&
						values.from_date < ctx.earliest_change_date
					) {
						frappe.msgprint({
							title: __("Attendance Already Marked"),
							indicator: "red",
							message: __(
								"Attendance is already marked up to {0}. Choose {1} or later.",
								[
									frappe.datetime.str_to_user(ctx.last_attendance_date),
									frappe.datetime.str_to_user(ctx.earliest_change_date),
								]
							),
						});
						return;
					}
					d.hide();
					frappe.call({
						method: "rbol.custom_shift_assignment.change_shift_from",
						args: {
							assignment: frm.doc.name,
							from_date: values.from_date,
							new_shift_type: values.new_shift_type,
							new_status: values.new_status,
							shift_location: values.shift_location,
						},
						freeze: true,
						freeze_message: __("Changing shift..."),
						callback(res) {
							if (res.message && res.message.new_assignment) {
								frappe.set_route(
									"Form",
									"Shift Assignment",
									res.message.new_assignment
								);
							} else {
								frm.reload_doc();
							}
						},
					});
				},
			});
			d.show();
		},
	});
}

function summary_html(ctx) {
	const fmt = (v) => (v ? frappe.datetime.str_to_user(v) : __("open ended"));
	let html = `<div class="text-muted" style="margin-bottom:8px">
		${__("Currently")}: <b>${frappe.utils.escape_html(ctx.employee_name || ctx.employee)}</b>
		&mdash; ${__("shift")} <b>${frappe.utils.escape_html(ctx.shift_type)}</b>,
		${fmt(ctx.start_date)} &rarr; ${fmt(ctx.end_date)}</div>`;
	if (ctx.last_attendance_date) {
		html += `<div class="text-muted" style="margin-bottom:8px">
			${__("Attendance already marked up to")}
			<b>${frappe.datetime.str_to_user(ctx.last_attendance_date)}</b>.
			${__("Those days stay exactly as they are.")}</div>`;
	}
	return html;
}
