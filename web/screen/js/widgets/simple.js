// The small widgets: logo, GIF, message, countdown, days-since counter, world clock, calendar, images.

import { el } from "../../../shared/js/dom.js";
import { daysBetween, formatClock, isoDay, isoWeek, zonedParts } from "../../../shared/js/format.js";
import { hesseHolidays } from "../../../shared/js/holidays.js";
import { strings } from "../strings.js";

const longDate = new Intl.DateTimeFormat("de-DE", { timeZone: "UTC", weekday: "long", day: "numeric", month: "long", year: "numeric" });
const shortDate = new Intl.DateTimeFormat("de-DE", { timeZone: "UTC", day: "numeric", month: "long", year: "numeric" });
const monthTitle = new Intl.DateTimeFormat("de-DE", { timeZone: "UTC", month: "long", year: "numeric" });
const atNoon = (day) => new Date(`${day}T12:00:00Z`);
const MIN_TEXT_FIT = 0.5;
const TEXT_FIT_STEP = 0.05;

/** Number, label and detail, in a box the tile's container queries can arrange. */
function bigBox(number, label, detail) {
  const text = el("div", "big-text");
  text.append(label, detail);
  const box = el("div", "big-box");
  box.append(number, text);
  return box;
}

export const logo = {
  create(tile, widget, ctx) {
    const options = widget.options;
    const image = options.image ?? ctx.settings.logo;
    tile.classList.add(`logo-pad-${options.padding}`, `logo-align-${options.align}`);
    tile.classList.toggle("tile-bare", !options.panel);
    if (image) {
      const img = el("img", "logo-image");
      img.src = ctx.uploadUrl(image);
      img.alt = "Logo";
      tile.append(img);
    } else {
      tile.append(el("p", "placeholder", strings.noLogo));
    }
    return { render() {} };
  },
};

export const gif = {
  create(tile, widget, ctx) {
    const options = widget.options;
    tile.classList.add(`gif-${options.fit}`);
    tile.classList.toggle("tile-bare", !options.panel);
    if (options.image) {
      // An <img> plays the animation on its own, in a loop, as the GIF defines it.
      const img = el("img", "gif-image");
      img.src = ctx.uploadUrl(options.image);
      img.alt = "";
      img.decoding = "async";
      tile.append(img);
    } else {
      tile.append(el("p", "placeholder", strings.noGif));
    }
    return { render() {} };
  },
};

export const message = {
  create(tile, widget) {
    const options = widget.options;
    tile.classList.add(`message-${options.size}`, `message-${options.align}`);
    tile.classList.toggle("message-highlight", options.highlight);
    if (options.title) tile.append(el("h2", "message-title", options.title));
    if (options.body) tile.append(el("p", "message-body", options.body));
    return {
      // Long texts shrink step by step until they fit the tile, down to half their size.
      render() {
        for (let fit = 1; fit >= MIN_TEXT_FIT; fit -= TEXT_FIT_STEP) {
          tile.style.setProperty("--fit", fit.toFixed(2));
          if (tile.scrollHeight <= tile.clientHeight + 1) break;
        }
      },
    };
  },
};

export const countdown = {
  create(tile, widget, ctx) {
    const options = widget.options;
    const number = el("p", "big-number");
    const unit = el("p", "big-label");
    const detail = el("p", "big-detail");
    tile.append(bigBox(number, unit, detail));
    let lastDay = "";
    return {
      render() {},
      tick(now) {
        const today = isoDay(now, ctx.timeZone);
        if (today === lastDay) return;
        lastDay = today;
        const days = daysBetween(today, options.date);
        tile.classList.toggle("countdown-today", days === 0);
        if (days > 1) {
          number.textContent = String(days);
          unit.textContent = `${strings.countdownDays(days)} ${strings.countdownUntil(options.label)}`;
        } else if (days === 1) {
          number.textContent = "1";
          unit.textContent = strings.countdownTomorrow(options.label);
        } else if (days === 0) {
          number.textContent = options.afterText;
          unit.textContent = options.label;
        } else {
          number.textContent = "";
          unit.textContent = strings.countdownPast(options.label);
        }
        detail.textContent = longDate.format(atNoon(options.date));
      },
    };
  },
};

export const counter = {
  create(tile, widget, ctx) {
    const options = widget.options;
    const number = el("p", "big-number");
    const unit = el("p", "big-label");
    const detail = el("p", "big-detail");
    tile.append(bigBox(number, unit, detail));
    let lastDay = "";
    return {
      render() {},
      tick(now) {
        const today = isoDay(now, ctx.timeZone);
        if (today === lastDay) return;
        lastDay = today;
        const days = Math.max(0, daysBetween(options.since, today));
        number.textContent = new Intl.NumberFormat("de-DE").format(days);
        unit.textContent = options.label;
        detail.textContent = strings.counterSince(shortDate.format(atNoon(options.since)));
      },
    };
  },
};

function offsetHours(now, zone, home) {
  const minutesOf = (tz) => {
    const p = zonedParts(now, tz);
    return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute) / 60000;
  };
  return (minutesOf(zone) - minutesOf(home)) / 60;
}

export const worldclock = {
  create(tile, widget, ctx) {
    const list = el("ul", "zones");
    tile.append(list);
    const rows = widget.options.zones.map((zone) => {
      const item = el("li", "zone");
      const label = el("span", "zone-label", zone.label);
      const detail = el("span", "zone-detail");
      const time = el("span", "zone-time");
      const text = el("span", "zone-text");
      text.append(label, detail);
      item.append(text, time);
      list.append(item);
      return { zone, time, detail };
    });
    let lastMinute = "";
    return {
      render() {},
      tick(now) {
        const minute = formatClock(now, ctx.timeZone);
        if (minute === lastMinute) return;
        lastMinute = minute;
        const home = isoDay(now, ctx.timeZone);
        for (const row of rows) {
          row.time.textContent = formatClock(now, row.zone.timeZone);
          const dayShift = strings.dayOffset(daysBetween(home, isoDay(now, row.zone.timeZone)));
          row.detail.textContent = [strings.hoursDifference(offsetHours(now, row.zone.timeZone, ctx.timeZone)), dayShift]
            .filter(Boolean).join(", ");
        }
        while (list.children.length > 1 && tile.scrollHeight > tile.clientHeight + 1) list.lastElementChild.remove();
      },
    };
  },
};

export const calendar = {
  create(tile, widget, ctx) {
    const options = widget.options;
    const title = el("h2", "calendar-title");
    const grid = el("div", "calendar-grid");
    grid.setAttribute("role", "grid");
    tile.append(title, grid);
    tile.classList.toggle("calendar-weeks", options.showWeekNumbers);
    let lastDay = "";
    return {
      render() {},
      tick(now) {
        const today = isoDay(now, ctx.timeZone);
        if (today === lastDay) return;
        lastDay = today;
        const [year, month] = today.split("-").map(Number);
        title.textContent = monthTitle.format(new Date(Date.UTC(year, month - 1, 15)));
        const holidays = new Map(options.showHolidays ? hesseHolidays(year).map((h) => [h.date, h.name]) : []);
        grid.replaceChildren();
        if (options.showWeekNumbers) grid.append(el("span", "calendar-head calendar-week", strings.weekShort));
        for (const name of strings.weekdaysShort) grid.append(el("span", "calendar-head", name));
        const first = new Date(Date.UTC(year, month - 1, 1));
        const offset = (first.getUTCDay() + 6) % 7;
        const start = new Date(first.getTime() - offset * 86400000);
        for (let week = 0; week < 6; week += 1) {
          const monday = new Date(start.getTime() + week * 7 * 86400000);
          if (week > 0 && monday.getUTCMonth() !== month - 1) break;
          if (options.showWeekNumbers) grid.append(el("span", "calendar-week", String(isoWeek(monday.toISOString().slice(0, 10)))));
          for (let weekday = 0; weekday < 7; weekday += 1) {
            const date = new Date(monday.getTime() + weekday * 86400000);
            const day = date.toISOString().slice(0, 10);
            const cell = el("span", "calendar-day", String(date.getUTCDate()));
            if (date.getUTCMonth() !== month - 1) cell.classList.add("calendar-other");
            if (weekday >= 5) cell.classList.add("calendar-weekend");
            if (holidays.has(day)) {
              cell.classList.add("calendar-holiday");
              cell.title = holidays.get(day);
            }
            if (day === today) {
              cell.classList.add("calendar-today");
              cell.setAttribute("aria-current", "date");
            }
            grid.append(cell);
          }
        }
      },
    };
  },
};

export const slideshow = {
  create(tile, widget, ctx) {
    const options = widget.options;
    tile.classList.add(`slideshow-${options.fit}`);
    if (!options.images.length) {
      tile.append(el("p", "placeholder", strings.noImages));
      return { render() {} };
    }
    const slides = options.images.map((id, index) => {
      const img = el("img", index === 0 ? "slide slide-visible" : "slide");
      img.src = ctx.uploadUrl(id);
      img.alt = "";
      img.decoding = "async";
      tile.append(img);
      return img;
    });
    let current = 0;
    const timer = slides.length > 1
      ? setInterval(() => {
        slides[current].classList.remove("slide-visible");
        current = (current + 1) % slides.length;
        slides[current].classList.add("slide-visible");
      }, options.seconds * 1000)
      : null;
    return { render() {}, destroy: () => clearInterval(timer) };
  },
};
