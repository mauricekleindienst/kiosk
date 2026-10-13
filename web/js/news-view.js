// Renders a list of headlines. The first one is the lead and gets more room.

import { clear, el } from "./dom.js";
import { formatAge } from "./format.js";
import { strings } from "./strings.js";

export function renderNews(body, source, now, { lead = false } = {}) {
  clear(body);
  const items = source?.data;
  if (!items) {
    body.append(el("p", "placeholder", source?.error ? strings.newsUnavailable : strings.newsLoading));
    return;
  }
  if (!items.length) {
    body.append(el("p", "placeholder", strings.newsEmpty));
    return;
  }
  const list = el("ol", "headlines");
  items.forEach((item, index) => {
    const entry = el("li", lead && index === 0 ? "headline headline-lead" : "headline");
    const title = el("p", "headline-title", item.title);
    // The full title stays available where the line clamp cuts it.
    title.title = item.title;
    entry.append(title);
    const meta = [item.source, item.published ? formatAge(Date.parse(item.published), now) : null].filter(Boolean).join(" · ");
    entry.append(el("p", "headline-meta", meta));
    list.append(entry);
  });
  body.append(list);
  // Keep only the headlines that fit completely; a half-cut line looks broken on a wall screen.
  while (list.children.length > 1 && body.scrollHeight > body.clientHeight + 1) list.lastElementChild.remove();
}
