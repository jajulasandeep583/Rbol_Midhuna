// Copyright (c) 2026, MIDHUNATECH
// Chart of Accounts: adds a "Hide zero balances" tick-box next to "Show all (including disabled)".
//
// Ticked: every account showing 0.00 is hidden, and so is any group whose accounts are all zero.
// A group stays visible as long as one account under it has a balance, even when the group itself
// nets to zero. The choice is remembered per user (in the browser). Nothing is changed in the
// accounts themselves; this only decides what the tree draws.

(function () {
	const settings = frappe.treeview_settings && frappe.treeview_settings["Account"];
	if (!settings || settings.rbol_hide_zero) return;
	settings.rbol_hide_zero = true;

	const STORE_KEY = "rbol_coa_hide_zero";
	const ZERO = 0.005; // anything the tree prints as 0.00

	const is_on = () => {
		try {
			return localStorage.getItem(STORE_KEY) === "1";
		} catch (e) {
			return false;
		}
	};
	const remember = (on) => {
		try {
			localStorage.setItem(STORE_KEY, on ? "1" : "0");
		} catch (e) {
			// private window: the tick-box still works for this visit
		}
	};

	// names of the accounts to hide, for the company the tree is showing
	function load_hidden(tree) {
		if (tree.rbol_hidden_promise) return tree.rbol_hidden_promise;
		const company = tree.args && tree.args.company;
		if (!company) return Promise.resolve(new Set());

		tree.rbol_hidden_promise = Promise.all([
			frappe.xcall("erpnext.accounts.utils.get_account_balances_coa", {
				company: company,
				include_default_fb_balances: true,
			}),
			frappe.db.get_list("Account", {
				filters: { company: company },
				fields: ["name", "parent_account", "is_group"],
				limit: 0,
			}),
		]).then(([balances, accounts]) => {
			const balance_of = {};
			(balances || []).forEach((b) => (balance_of[b.value] = b.balance || 0));

			const parent_of = {};
			const keep = new Set();
			(accounts || []).forEach((a) => (parent_of[a.name] = a.parent_account));
			(accounts || []).forEach((a) => {
				if (a.is_group || Math.abs(balance_of[a.name] || 0) < ZERO) return;
				// a ledger with a balance: keep it and every group above it
				let name = a.name;
				while (name && !keep.has(name)) {
					keep.add(name);
					name = parent_of[name];
				}
			});

			const hidden = new Set();
			(accounts || []).forEach((a) => {
				if (!keep.has(a.name)) hidden.add(a.name);
			});
			return hidden;
		});
		return tree.rbol_hidden_promise;
	}

	function apply(tree) {
		if (!tree || !tree.nodes) return;
		const on = is_on();
		const paint = (hidden) => {
			Object.keys(tree.nodes).forEach((name) => {
				const node = tree.nodes[name];
				if (!node || node.is_root || !node.parent) return;
				$(node.parent).toggleClass("hidden", !!(on && hidden.has(name)));
			});
		};
		if (!on) return paint(new Set());
		load_hidden(tree).then(paint);
	}

	const can_see_balances = () => (frappe.boot.user.can_read || []).indexOf("GL Entry") !== -1;

	const base_onload = settings.onload;
	settings.onload = function (treeview) {
		base_onload && base_onload.apply(this, arguments);
		if (!can_see_balances() || !treeview.page || treeview.page.fields_dict.rbol_hide_zero) return;

		const field = treeview.page.add_field(
			{
				fieldname: "rbol_hide_zero",
				fieldtype: "Check",
				label: __("Hide zero balances"),
				change: function () {
					remember(cint(field.get_value()));
					apply(treeview.tree || cur_tree);
				},
			},
			treeview.$filter_area || treeview.page.filters
		);
		if (is_on()) field.set_value(1);
	};

	const base_on_node_render = settings.on_node_render;
	settings.on_node_render = function (node, deep) {
		base_on_node_render && base_on_node_render.apply(this, arguments);
		if (can_see_balances()) apply(cur_tree);
	};
})();
