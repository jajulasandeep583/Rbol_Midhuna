/**
 * Keep frappe-ui dropdown listboxes inside the viewport.
 *
 * frappe-ui's Autocomplete caps its listbox at a fixed `max-h-[15rem]` and
 * positions the popover with Popper. Popper will flip the popover to the other
 * side of the trigger, but it never *shrinks* it - so a list that is taller
 * than the space below its trigger simply runs off the bottom of the screen.
 * The list scrolls internally, but its own bottom edge is off-screen, so the
 * last few options can never be brought into view. Raising the cap in CSS
 * makes the truncation better and the clipping worse; there is no fixed number
 * that is right for both a trigger near the top of the page and one near the
 * bottom.
 *
 * So size each open listbox to the room it actually has: as tall as it needs,
 * up to MAX, but never past the viewport edge. Anything that doesn't fit
 * scrolls inside a list whose bottom you can actually see.
 */

// 28rem ~ 13 rows. Past that a dropdown is worse than typing to filter.
const MAX_HEIGHT = 448
// Never squeeze below ~3 rows; on a tiny viewport, scrolling beats a sliver.
const MIN_HEIGHT = 132
// Breathing room so the list never sits flush against the viewport edge.
const EDGE_GAP = 12

const LISTBOX_SELECTOR = '[role="listbox"]'

let scheduled = false

function fit(list: HTMLElement) {
	const rect = list.getBoundingClientRect()
	if (!rect.height) return // closed

	// Popper records where it ended up; a flipped dropdown grows upwards.
	const popper = list.closest<HTMLElement>("[data-popper-placement]")
	const placement = popper?.dataset.popperPlacement ?? "bottom"

	const available = placement.startsWith("top")
		? rect.bottom - EDGE_GAP
		: window.innerHeight - rect.top - EDGE_GAP

	const next = `${Math.round(Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, available)))}px`
	if (list.style.maxHeight === next) return
	list.style.maxHeight = next

	// A flipped dropdown is anchored by its top, so shrinking it leaves a gap
	// between the list and its trigger. Popper recomputes on window resize.
	if (placement.startsWith("top")) window.dispatchEvent(new Event("resize"))
}

function fitAll() {
	scheduled = false
	document.querySelectorAll<HTMLElement>(LISTBOX_SELECTOR).forEach(fit)
}

function schedule() {
	if (scheduled) return
	scheduled = true
	requestAnimationFrame(fitAll)
}

export function keepDropdownsInViewport() {
	if (typeof window === "undefined") return

	// Popover teleports every dropdown into this one container, creating it on
	// first use. Create it up front (Popover reuses it) so we have something to
	// observe from the start.
	let root = document.getElementById("frappeui-popper-root")
	if (!root) {
		root = document.createElement("div")
		root.id = "frappeui-popper-root"
		document.body.appendChild(root)
	}

	// Dropdowns are shown with v-show and moved with an inline transform, so we
	// need attribute changes as well as insertions.
	new MutationObserver(schedule).observe(root, {
		childList: true,
		subtree: true,
		attributes: true,
		attributeFilter: ["style", "class", "data-popper-placement"],
	})

	window.addEventListener("resize", schedule)
	window.addEventListener("scroll", schedule, true)
}
