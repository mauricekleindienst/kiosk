// Share price with the day's curve, and departures from a stop.

import { clear, el } from "../../../shared/js/dom.js";
import { formatClock } from "../../../shared/js/format.js";
import { panelHead, renderStatus } from "../status.js";
import { strings } from "../strings.js";

const SVG = "http://www.w3.org/2000/svg";

function svg(tag, attributes) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
}

function money(value, currency) {
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: currency || "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function signed(value, format) {
  const text = format(Math.abs(value));
  if (value > 0) return `+${text}`;
  if (value < 0) return `−${text}`;
  return text;
}

/** The day's curve as a line from left to right, with yesterday's close as a dotted reference. */
function chart(quote) {
  const points = quote.points;
  const box = svg("svg", { class: "stock-chart", viewBox: "0 0 300 100", preserveAspectRatio: "none", "aria-hidden": "true" });
  if (points.length < 2) return box;
  const start = Date.parse(quote.sessionStart ?? points[0][0]);
  const end = Math.max(Date.parse(quote.sessionEnd ?? points.at(-1)[0]), Date.parse(points.at(-1)[0]));
  const values = points.map(([, value]) => value);
  if (quote.previousClose != null) values.push(quote.previousClose);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const x = (iso) => (((Date.parse(iso) - start) / Math.max(end - start, 1)) * 300).toFixed(1);
  const y = (value) => (96 - ((value - low) / span) * 92).toFixed(1);
  if (quote.previousClose != null) {
    const level = y(quote.previousClose);
    box.append(svg("line", { class: "stock-baseline", x1: 0, x2: 300, y1: level, y2: level }));
  }
  const line = points.map(([time, value]) => `${x(time)},${y(value)}`).join(" ");
  box.append(svg("polyline", { class: "stock-line", points: line }));
  return box;
}

export const stockWidget = {
  create(tile, widget, ctx) {
    const options = widget.options;
    const { status } = panelHead(tile, options.label || options.symbol);
    const body = el("div", "panel-body stock-body");
    tile.append(body);
    return {
      render(state, now, reachable) {
        const source = state?.widgets?.[widget.id];
        renderStatus(status, source, now, reachable, ctx.timeZone);
        clear(body);
        const quote = source?.data;
        if (!quote) {
          body.append(el("p", "placeholder", source?.error ? strings.stockUnavailable : strings.stockLoading));
          return;
        }
        const direction = quote.change > 0 ? "up" : quote.change < 0 ? "down" : "flat";
        tile.dataset.direction = direction;
        const figures = el("div", "stock-figures");
        figures.append(el("p", "stock-price", money(quote.price, quote.currency)));
        if (quote.change != null) {
          const percent = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
          figures.append(el("p", `stock-change stock-${direction}`,
            `${signed(quote.change, (v) => money(v, quote.currency))} (${signed(quote.changePercent, (v) => `${percent.format(v)} %`)})`));
        }
        const meta = [quote.exchange, quote.time ? strings.stockAsOf(formatClock(new Date(quote.time), ctx.timeZone)) : null].filter(Boolean).join(" · ");
        figures.append(el("p", "stock-meta", meta));
        body.append(figures);
        if (options.showChart) body.append(chart(quote));
      },
    };
  },
};

const PRODUCT_LABELS = { tram: "Tram", bus: "Bus", suburban: "S", subway: "U", regional: "RB", regionalExpress: "RE", national: "IC", nationalExpress: "ICE", ferry: "Fähre", taxi: "AST" };

export const transitWidget = {
  create(tile, widget, ctx) {
    const options = widget.options;
    const { title, status } = panelHead(tile, options.title || options.stop?.name || strings.transitTitle);
    const body = el("div", "panel-body");
    tile.append(body);
    return {
      render(state, now, reachable) {
        clear(body);
        if (!options.stop) {
          body.append(el("p", "placeholder", strings.transitNoStop));
          return;
        }
        const source = state?.widgets?.[widget.id];
        renderStatus(status, source, now, reachable, ctx.timeZone);
        const departures = source?.data;
        if (!departures) {
          body.append(el("p", "placeholder", source?.error ? strings.transitUnavailable : strings.transitLoading));
          return;
        }
        // Only what can still be reached on foot; cancelled ones stay visible until their time.
        const reachableFrom = now.getTime() + options.walkMinutes * 60_000;
        const upcoming = departures.filter((departure) => Date.parse(departure.when) >= reachableFrom).slice(0, options.limit);
        if (!upcoming.length) {
          body.append(el("p", "placeholder", strings.transitNone));
          return;
        }
        title.textContent = options.title || options.stop.name;
        const list = el("ol", "departures");
        for (const departure of upcoming) {
          const item = el("li", departure.cancelled ? "departure departure-cancelled" : "departure");
          item.append(el("span", "departure-line", departure.line || PRODUCT_LABELS[departure.product] || ""));
          const middle = el("span", "departure-text");
          middle.append(el("span", "departure-direction", departure.direction));
          const detail = [];
          if (departure.platform) detail.push(strings.transitPlatform(departure.platform));
          middle.append(el("span", "departure-detail", detail.join(" · ")));
          item.append(middle);
          const time = el("span", "departure-time");
          if (departure.cancelled) {
            time.append(el("span", "departure-state departure-state-cancelled", strings.transitCancelled));
          } else {
            const minutes = Math.max(0, Math.round((Date.parse(departure.when) - now.getTime()) / 60_000));
            time.append(el("span", "departure-countdown", minutes === 0 ? strings.transitNow : strings.transitIn(minutes)));
          }
          const planned = el("span", "departure-planned", formatClock(new Date(departure.planned ?? departure.when), ctx.timeZone));
          time.append(planned);
          if (!departure.cancelled && departure.delayMinutes > 0) {
            time.append(el("span", departure.delayMinutes >= 5 ? "departure-delay departure-delay-late" : "departure-delay", `+${departure.delayMinutes}`));
          }
          item.append(time);
          list.append(item);
        }
        body.append(list);
        while (list.children.length > 1 && body.scrollHeight > body.clientHeight + 1) list.lastElementChild.remove();
      },
    };
  },
};
