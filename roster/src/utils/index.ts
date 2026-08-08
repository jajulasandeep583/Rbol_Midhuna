import { toast } from "frappe-ui";

export { default as dayjs } from "./dayjs";

// Frappe errors arrive as {messages: [...]}, but a client-side throw (a bad
// transform, a network hiccup) arrives as a plain Error with no `messages`.
// Reading messages[0] blind turned every such throw into a second, useless
// TypeError and hid the real one -- which is exactly how a single unrenderable
// row managed to blank the roster silently.
export const errorMessage = (error: unknown): string => {
	const e = error as { messages?: string[]; message?: string } | undefined;
	return e?.messages?.[0] || e?.message || "Something went wrong. Please try again.";
};

export const raiseToast = (type: "success" | "error", message: string) => {
	if (type === "success")
		return toast({
			title: "Success",
			text: message,
			icon: "check-circle",
			position: "bottom-right",
			iconClasses: "text-green-500",
		});

	const div = document.createElement("div");
	div.innerHTML = message;
	// strip html tags
	const text =
		div.textContent || div.innerText || "Failed to perform action. Please try again later.";
	toast({
		title: "Error",
		text: text,
		icon: "alert-circle",
		position: "bottom-right",
		iconClasses: "text-red-500",
		timeout: 7,
	});
};

export const goTo = (path: string) => {
	window.location.href = path;
};
