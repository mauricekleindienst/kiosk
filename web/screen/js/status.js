// Decides whether a block's data is too old to be trusted, and says so in one quiet line.

import { el, icon } from "../../shared/js/dom.js";
import { formatClock } from "../../shared/js/format.js";
import { strings } from "./strings.js";

// Data counts as stale after three missed refreshes; one late refresh is normal.
const STALE_AFTER_REFRESHES = 3;

export function isStale(source, now, serverReachable) {
  if (!source?.fetchedAt) return false;
  const ageMinutes = (now - Date.parse(source.fetchedAt)) / 60000;
  return !serverReachable || ageMinutes > STALE_AFTER_REFRESHES * source.refreshMinutes;
}

/** Fills `node` with the stale notice, or hides it when the data is fresh. */
export function renderStatus(node, source, now, serverReachable, timeZone) {
  if (!isStale(source, now, serverReachable)) {
    node.hidden = true;
    node.replaceChildren();
    return;
  }
  node.hidden = false;
  node.replaceChildren(
    icon("offline", "status-icon"),
    el("span", null, strings.stale(formatClock(new Date(source.fetchedAt), timeZone))),
  );
}

/** A panel head with a title and a place for the stale notice. */
export function panelHead(tile, titleText) {
  const head = el("header", "panel-head");
  const title = el("h2", "panel-title", titleText);
  const status = el("p", "status");
  status.hidden = true;
  head.append(title, status);
  tile.append(head);
  return { title, status };
}
