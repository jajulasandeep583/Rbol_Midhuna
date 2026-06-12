<template>
	<div v-if="user.data" class="min-h-screen">
		<NavBar :user="user.data" />
		<MonthView />
		<Toasts />
	</div>
	<div v-else-if="loadFailed" class="min-h-screen flex items-center justify-center p-6">
		<div class="text-center max-w-md">
			<div class="text-5xl mb-4">&#9888;&#65039;</div>
			<h1 class="text-xl font-semibold mb-2">Could not load the roster</h1>
			<p class="text-gray-600 mb-6">
				Your session may have expired or your user does not have access. Try
				logging in again — if it keeps failing, contact your administrator.
			</p>
			<button
				class="px-4 py-2 rounded bg-gray-800 text-white"
				@click="relogin"
			>
				Log in again
			</button>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { Toasts, createResource } from "frappe-ui";

import NavBar from "../components/NavBar.vue";
import MonthView from "./MonthView.vue";

export type User = {
	[K in "name" | "first_name" | "full_name" | "user_image"]: string;
} & {
	roles: string[];
};

const loadFailed = ref(false);

const RELOAD_FLAG = "roster-rbol-reloaded";

function isGuest() {
	return /(?:^|;\s*)user_id=(?:Guest|$)/.test(document.cookie) || !/user_id=/.test(document.cookie);
}

function relogin() {
	sessionStorage.removeItem(RELOAD_FLAG);
	window.location.href = "/login?redirect-to=%2Froster";
}

// RESOURCES

const user = createResource({
	url: "rbol.api.get_current_user_info",
	auto: true,
	onSuccess() {
		sessionStorage.removeItem(RELOAD_FLAG);
	},
	onError() {
		// Not logged in -> go to login (once; /login bounces logged-in users
		// back here, so redirecting unconditionally caused an infinite loop).
		if (isGuest()) {
			window.location.href = "/login?redirect-to=%2Froster";
			return;
		}
		// Logged in but the call failed (stale CSRF token after a server
		// restart is the common case) -> one hard reload fetches a fresh
		// token; if it fails again, show the error screen instead of looping.
		if (!sessionStorage.getItem(RELOAD_FLAG)) {
			sessionStorage.setItem(RELOAD_FLAG, "1");
			window.location.reload();
			return;
		}
		loadFailed.value = true;
	},
});
</script>
