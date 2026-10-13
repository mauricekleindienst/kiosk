// Weather: warnings, current conditions, the next hours and the coming days. Parts the tile has
// no room for are left out, smallest first (container queries in screen.css, days by measuring).

import { clear, el, icon } from "../../../shared/js/dom.js";
import {
  formatClock, formatMillimetres, formatPercent, formatSpeed, formatTemperature, isoDay, weekdayShort, zonedParts,
} from "../../../shared/js/format.js";
import { panelHead, renderStatus } from "../status.js";
import { strings } from "../strings.js";

// Below this chance of rain the hourly row stays empty; "10 %" on every hour is noise.
const SHOW_PRECIPITATION_FROM_PERCENT = 20;
// Gusts are worth a mention when they clearly exceed the mean wind (DWD reports both in km/h).
const GUST_NOTE_FROM_KMH = 10;
// However tall the warnings get, at least this many days of the forecast stay on screen.
const MIN_DAYS_SHOWN = 3;
// One hour column needs about this many rem to stay readable.
const HOUR_COLUMN_REM = 3.4;

function alertsBlock(alerts, timeZone, now) {
  const list = el("ul", "alerts");
  for (const alert of alerts) {
    const item = el("li", `alert alert-${alert.severity}`);
    item.append(icon("warning", "alert-icon"));
    const text = el("div", "alert-text");
    text.append(el("p", "alert-label", strings.warningLabel(alert.severity)));
    const until = alert.expires ? untilText(new Date(alert.expires), timeZone, now) : "";
    text.append(el("p", "alert-headline", [alert.headline, until].filter(Boolean).join(" · ")));
    item.append(text);
    list.append(item);
  }
  return list;
}

function untilText(expires, timeZone, now) {
  const time = formatClock(expires, timeZone);
  const day = isoDay(expires, timeZone);
  return day === isoDay(now, timeZone) ? strings.until(time) : strings.untilDay(weekdayShort(day), time);
}

function nowBlock(weather) {
  const block = el("div", "now");
  const current = weather.current;
  const today = weather.daily[0];
  const iconName = current?.icon ?? weather.hourly[0]?.icon ?? "cloudy";
  block.append(icon(iconName, "now-icon"));
  const text = el("div", "now-text");
  const temperature = current?.temperature ?? weather.hourly[0]?.temperature;
  text.append(el("p", "now-temperature", formatTemperature(temperature)));
  text.append(el("p", "now-condition", strings.conditions[iconName]));
  if (today) {
    text.append(el("p", "now-range", strings.todayRange(formatTemperature(today.max), formatTemperature(today.min))));
  }
  block.append(text);
  return block;
}

function fact(iconName, label, value) {
  const item = el("li", "fact");
  item.append(icon(iconName, "fact-icon"));
  const text = el("span", "fact-text");
  text.append(el("span", "fact-label", label));
  text.append(el("span", "fact-value", value));
  item.append(text);
  return item;
}

function factsBlock(weather, timeZone) {
  const list = el("ul", "facts");
  const current = weather.current;
  if (current?.windSpeed != null) {
    const gusty = current.windGust != null && current.windGust >= current.windSpeed + GUST_NOTE_FROM_KMH;
    const label = gusty ? strings.windWithGusts(formatSpeed(current.windGust)) : strings.wind;
    list.append(fact("wind-small", label, formatSpeed(current.windSpeed)));
  }
  if (current?.humidity != null) list.append(fact("droplet", strings.humidity, formatPercent(current.humidity)));
  const today = weather.daily[0];
  if (today?.precipitationProbability != null) {
    const label = today.precipitation > 0 ? strings.precipitationWithAmount(formatMillimetres(today.precipitation)) : strings.precipitation;
    list.append(fact("umbrella", label, formatPercent(today.precipitationProbability)));
  }
  if (weather.sun.sunrise && weather.sun.sunset) {
    const rise = formatClock(new Date(weather.sun.sunrise), timeZone);
    const set = formatClock(new Date(weather.sun.sunset), timeZone);
    list.append(fact("sunrise", strings.sun, `${rise}–${set}`));
  }
  return list;
}

function hoursBlock(hourly, timeZone) {
  const list = el("ol", "hours");
  list.style.setProperty("--hours", String(hourly.length));
  for (const hour of hourly) {
    const item = el("li", "hour");
    const { hour: clockHour } = zonedParts(new Date(hour.time), timeZone);
    item.append(el("span", "hour-time", String(clockHour)));
    item.append(icon(hour.icon, "hour-icon", strings.conditions[hour.icon]));
    item.append(el("span", "hour-temperature", formatTemperature(hour.temperature)));
    const chance = hour.precipitationProbability;
    item.append(el("span", "hour-precipitation", chance != null && chance >= SHOW_PRECIPITATION_FROM_PERCENT ? formatPercent(chance) : ""));
    item.title = strings.hourLabel(clockHour);
    list.append(item);
  }
  return list;
}

function daysBlock(daily) {
  const list = el("ol", "days");
  const lowest = Math.min(...daily.map((day) => day.min));
  const highest = Math.max(...daily.map((day) => day.max));
  const span = Math.max(highest - lowest, 1);
  daily.forEach((day, index) => {
    const item = el("li", "day");
    item.append(el("span", "day-name", index === 0 ? strings.today : weekdayShort(day.date)));
    item.append(icon(day.icon, "day-icon", strings.conditions[day.icon]));
    const chance = day.precipitationProbability;
    item.append(el("span", "day-precipitation", chance != null && chance >= SHOW_PRECIPITATION_FROM_PERCENT ? formatPercent(chance) : ""));
    item.append(el("span", "day-min", formatTemperature(day.min)));
    const bar = el("span", "day-bar");
    const fill = el("span", "day-bar-fill");
    // Custom properties through the CSSOM; the CSP forbids style attributes, not this.
    fill.style.setProperty("--from", ((day.min - lowest) / span).toFixed(3));
    fill.style.setProperty("--to", ((day.max - lowest) / span).toFixed(3));
    bar.append(fill);
    item.append(bar);
    item.append(el("span", "day-max", formatTemperature(day.max)));
    list.append(item);
  });
  return list;
}

export function create(tile, widget, ctx) {
  const options = widget.options;
  const { title, status } = panelHead(tile, strings.weatherTitle(ctx.settings.location.name));
  const body = el("div", "panel-body");
  const source = el("p", "source-note", strings.weatherSource);
  tile.append(body, source);

  return {
    render(state, now, reachable) {
      const entry = state?.weather;
      renderStatus(status, entry, now, reachable, ctx.timeZone);
      clear(body);
      const weather = entry?.data;
      if (!weather) {
        body.append(el("p", "placeholder", entry?.error ? strings.weatherUnavailable : strings.weatherLoading));
        return;
      }
      title.textContent = strings.weatherTitle(weather.location);
      if (options.showAlerts && weather.alerts.length) body.append(alertsBlock(weather.alerts, ctx.timeZone, now));
      body.append(nowBlock(weather));
      const facts = options.showFacts ? factsBlock(weather, ctx.timeZone) : null;
      if (facts) body.append(facts);
      if (options.showHourly && weather.hourly.length) {
        const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
        const fitting = Math.max(3, Math.floor(body.clientWidth / (HOUR_COLUMN_REM * rem)));
        body.append(hoursBlock(weather.hourly.slice(0, Math.min(options.hourlyCount, fitting)), ctx.timeZone));
      }
      if (options.showDaily && weather.daily.length) {
        const days = daysBlock(weather.daily.slice(0, options.dailyCount));
        body.append(days);
        // Warnings take room; the forecast gives up its last days rather than run out of the panel.
        const overflowing = () => body.scrollHeight > body.clientHeight + 1;
        while (days.children.length > MIN_DAYS_SHOWN && overflowing()) days.lastElementChild.remove();
        // In a small tile the coming days matter more than wind and humidity.
        if (overflowing() && facts) facts.remove();
        if (overflowing()) days.remove();
      }
    },
  };
}
