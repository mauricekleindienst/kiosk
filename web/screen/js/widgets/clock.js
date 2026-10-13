// The clock: digital or analog, with date, ISO week and the next holiday in Hesse.

import { el } from "../../../shared/js/dom.js";
import { formatClock, formatLongDate, isoDay, isoWeek, zonedParts } from "../../../shared/js/format.js";
import { nextHoliday } from "../../../shared/js/holidays.js";
import { strings } from "../strings.js";

const SVG = "http://www.w3.org/2000/svg";

function svg(tag, attributes) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
}

function analogFace(showSeconds) {
  const face = svg("svg", { class: "analog", viewBox: "0 0 200 200", "aria-hidden": "true" });
  face.append(svg("circle", { class: "analog-face", cx: 100, cy: 100, r: 96 }));
  for (let tick = 0; tick < 60; tick += 1) {
    const major = tick % 5 === 0;
    const line = svg("line", { class: major ? "analog-tick-major" : "analog-tick", x1: 100, y1: major ? 12 : 10, x2: 100, y2: major ? 26 : 16 });
    line.setAttribute("transform", `rotate(${tick * 6} 100 100)`);
    face.append(line);
  }
  const hands = {
    hour: svg("line", { class: "analog-hour", x1: 100, y1: 112, x2: 100, y2: 52 }),
    minute: svg("line", { class: "analog-minute", x1: 100, y1: 116, x2: 100, y2: 24 }),
    second: showSeconds ? svg("line", { class: "analog-second", x1: 100, y1: 122, x2: 100, y2: 20 }) : null,
  };
  face.append(hands.hour, hands.minute);
  if (hands.second) face.append(hands.second);
  face.append(svg("circle", { class: "analog-pin", cx: 100, cy: 100, r: 4 }));
  return { face, hands };
}

export function holidayText(today) {
  const holiday = nextHoliday(today);
  if (holiday.daysUntil === 0) return strings.holidayToday(holiday.name);
  if (holiday.daysUntil === 1) return strings.holidayTomorrow(holiday.name);
  return strings.holidayIn(holiday.name, holiday.daysUntil);
}

export function create(tile, widget, ctx) {
  const options = widget.options;
  tile.classList.add(`clock-${options.style}`);
  // The tile is the size container; queries style what is inside it, so everything goes in a box.
  const box = el("div", "clock-box");
  tile.append(box);
  let timeNode = null;
  let analog = null;
  if (options.style === "analog") {
    analog = analogFace(options.showSeconds);
    box.append(analog.face);
  } else {
    timeNode = el("p", "clock-time", "--:--");
    box.append(timeNode);
  }
  const dateBlock = el("div", "clock-date-block");
  const dateNode = el("p", "clock-date");
  const metaNode = el("p", "clock-meta");
  if (options.showDate) dateBlock.append(dateNode);
  if (options.showWeek || options.showHoliday) dateBlock.append(metaNode);
  if (dateBlock.children.length) box.append(dateBlock);
  if (options.showLogo && ctx.settings.logo) {
    const logo = el("img", "clock-logo");
    logo.src = ctx.uploadUrl(ctx.settings.logo);
    logo.alt = "";
    box.append(logo);
  }

  // Small tiles drop the extra lines rather than cut them: first the week line, then the date.
  const fit = () => {
    metaNode.hidden = false;
    dateNode.hidden = false;
    // Cut means: the date lines reach past the box (rounding in the big clock text does not count).
    const overflowing = () => {
      const limit = box.getBoundingClientRect();
      return [dateNode, metaNode].some((node) => {
        if (node.hidden || !node.isConnected) return false;
        const rect = node.getBoundingClientRect();
        return rect.bottom > limit.bottom + 1 || rect.right > limit.right + 1;
      });
    };
    if (overflowing()) metaNode.hidden = true;
    if (overflowing()) dateNode.hidden = true;
  };

  let lastDay = "";
  return {
    tick(now) {
      const parts = zonedParts(now, ctx.timeZone);
      if (timeNode) {
        const seconds = options.showSeconds ? `:${String(parts.second).padStart(2, "0")}` : "";
        const text = `${formatClock(now, ctx.timeZone)}${seconds}`;
        if (timeNode.textContent !== text) timeNode.textContent = text;
      } else {
        const minutes = parts.minute + parts.second / 60;
        analog.hands.hour.setAttribute("transform", `rotate(${((parts.hour % 12) + minutes / 60) * 30} 100 100)`);
        analog.hands.minute.setAttribute("transform", `rotate(${minutes * 6} 100 100)`);
        analog.hands.second?.setAttribute("transform", `rotate(${parts.second * 6} 100 100)`);
        tile.setAttribute("aria-label", formatClock(now, ctx.timeZone));
      }
      const today = isoDay(now, ctx.timeZone);
      if (today !== lastDay) {
        lastDay = today;
        dateNode.textContent = formatLongDate(now, ctx.timeZone);
        const meta = [options.showWeek ? strings.calendarWeek(isoWeek(today)) : null, options.showHoliday ? holidayText(today) : null];
        metaNode.textContent = meta.filter(Boolean).join(" · ");
        fit();
      }
    },
    render: fit,
  };
}
