// Ready-made layouts. Applying one keeps the options of existing widgets of the same type, so
// feeds, texts and dates carry over.

import { newWidgetId } from "../../shared/js/layout.js";
import { defaultOptions } from "./forms.js";

export const TEMPLATES = [
  {
    name: "Standard",
    description: "Uhr, Nachrichten groß, Region und Wetter rechts.",
    slots: [
      { type: "clock", x: 0, y: 0, w: 7, h: 2 },
      { type: "news", x: 0, y: 2, w: 7, h: 4 },
      { type: "news", x: 0, y: 6, w: 7, h: 2, options: { lead: false, columns: "2" } },
      { type: "weather", x: 7, y: 0, w: 5, h: 8 },
    ],
  },
  {
    name: "Nachrichten im Fokus",
    description: "Zwei breite Nachrichtenspalten, Uhr und Wetter kompakt oben.",
    slots: [
      { type: "clock", x: 0, y: 0, w: 5, h: 2, options: { showHoliday: false } },
      { type: "weather", x: 5, y: 0, w: 4, h: 2 },
      { type: "logo", x: 9, y: 0, w: 3, h: 2 },
      { type: "news", x: 0, y: 2, w: 7, h: 6 },
      { type: "news", x: 7, y: 2, w: 5, h: 6, options: { lead: false } },
    ],
  },
  {
    name: "Empfang",
    description: "Logo, große Begrüßung für Besuch, Uhr und Wetter.",
    slots: [
      { type: "logo", x: 0, y: 0, w: 4, h: 2 },
      { type: "clock", x: 4, y: 0, w: 8, h: 2 },
      { type: "message", x: 0, y: 2, w: 8, h: 4, options: { size: "huge", highlight: true } },
      { type: "weather", x: 8, y: 2, w: 4, h: 6 },
      { type: "news", x: 0, y: 6, w: 8, h: 2, options: { lead: false, columns: "2" } },
    ],
  },
  {
    name: "Werk und Produktion",
    description: "Tage ohne Arbeitsunfall, Countdown, Nachrichten und Wetter.",
    slots: [
      { type: "clock", x: 0, y: 0, w: 6, h: 2 },
      { type: "counter", x: 6, y: 0, w: 3, h: 2 },
      { type: "countdown", x: 9, y: 0, w: 3, h: 2 },
      { type: "news", x: 0, y: 2, w: 7, h: 6 },
      { type: "weather", x: 7, y: 2, w: 5, h: 6 },
    ],
  },
  {
    name: "Hochformat",
    description: "Für hochkant montierte Bildschirme.",
    slots: [
      { type: "clock", x: 0, y: 0, w: 12, h: 1 },
      { type: "weather", x: 0, y: 1, w: 12, h: 3 },
      { type: "news", x: 0, y: 4, w: 12, h: 2 },
      { type: "news", x: 0, y: 6, w: 12, h: 2, options: { lead: false, columns: "2" } },
    ],
  },
  {
    name: "Übersicht",
    description: "Uhr, Kalender, Weltzeit, Wetter und Nachrichten.",
    slots: [
      { type: "clock", x: 0, y: 0, w: 5, h: 2 },
      { type: "calendar", x: 0, y: 2, w: 3, h: 4 },
      { type: "worldclock", x: 3, y: 2, w: 2, h: 4 },
      { type: "message", x: 0, y: 6, w: 5, h: 2 },
      { type: "news", x: 5, y: 0, w: 4, h: 8 },
      { type: "weather", x: 9, y: 0, w: 3, h: 8, options: { hourlyCount: 6 } },
    ],
  },
];

/** The widgets of `template`, reusing existing widgets of the same type in order. */
export function applyTemplate(template, current, catalog) {
  const unused = [...current];
  const widgets = [];
  for (const slot of template.slots) {
    const index = unused.findIndex((widget) => widget.type === slot.type);
    const existing = index >= 0 ? unused.splice(index, 1)[0] : null;
    const base = existing ?? { id: newWidgetId([...widgets, ...unused], slot.type), type: slot.type, options: defaultOptions(catalog.types[slot.type]) };
    widgets.push({
      ...base,
      x: slot.x, y: slot.y, w: slot.w, h: slot.h,
      // The template's layout options win; content (feeds, texts, dates) stays.
      options: { ...base.options, ...(slot.options ?? {}) },
    });
  }
  return widgets;
}
