// Headlines from one feed. The first one can be the lead and get more room.

import { clear, el } from "../../../shared/js/dom.js";
import { formatAge } from "../../../shared/js/format.js";
import { panelHead, renderStatus } from "../status.js";
import { strings } from "../strings.js";

export function create(tile, widget, ctx) {
  const options = widget.options;
  const { status } = panelHead(tile, options.title);
  const body = el("div", "panel-body");
  tile.append(body);
  tile.classList.toggle("news-two-columns", options.columns === "2");

  return {
    render(state, now, reachable) {
      const source = state?.news?.[widget.id];
      renderStatus(status, source, now, reachable, ctx.timeZone);
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
      items.slice(0, options.limit).forEach((item, index) => {
        const lead = options.lead && index === 0;
        const entry = el("li", lead ? "headline headline-lead" : "headline");
        const title = el("p", "headline-title", item.title);
        // The full title stays available where the line clamp cuts it.
        title.title = item.title;
        entry.append(title);
        const meta = [
          options.showSource ? item.source : null,
          options.showAge && item.published ? formatAge(Date.parse(item.published), now) : null,
        ].filter(Boolean).join(" · ");
        if (meta) entry.append(el("p", "headline-meta", meta));
        list.append(entry);
      });
      body.append(list);
      // Keep only the headlines that fit completely; a half-cut line looks broken on a wall screen.
      while (list.children.length > 1 && body.scrollHeight > body.clientHeight + 1) list.lastElementChild.remove();
    },
  };
}
