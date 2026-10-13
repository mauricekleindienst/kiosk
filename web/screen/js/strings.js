// Every text the screen shows. The screen is German only; a second language would be a second
// catalog with the same keys.

export const strings = {
  calendarWeek: (week) => `KW ${week}`,
  holidayToday: (name) => `Heute: ${name}`,
  holidayTomorrow: (name) => `Morgen: ${name}`,
  holidayIn: (name, days) => `${name} in ${days} Tagen`,

  weatherTitle: (place) => (place ? `Wetter in ${place}` : "Wetter"),
  weatherLoading: "Wetterdaten werden geladen…",
  weatherUnavailable: "Wetterdaten sind gerade nicht verfügbar. Der Bildschirm versucht es jede Minute erneut.",
  weatherSource: "Quelle: Deutscher Wetterdienst",
  todayRange: (max, min) => `Max ${max} · Min ${min}`,
  wind: "Wind",
  windWithGusts: (speed) => `Wind, Böen ${speed}`,
  humidity: "Luftfeuchte",
  precipitation: "Niederschlag",
  precipitationWithAmount: (amount) => `Niederschlag, ${amount}`,
  sun: "Sonne",
  today: "Heute",
  hourLabel: (hour) => `${hour} Uhr`,
  warningLabel: (severity) =>
    ({ minor: "Wetterwarnung", moderate: "Markante Wetterwarnung", severe: "Unwetterwarnung", extreme: "Extremes Unwetter" })[severity] ??
    "Wetterwarnung",
  until: (time) => `bis ${time} Uhr`,
  untilDay: (day, time) => `bis ${day} ${time} Uhr`,

  newsLoading: "Nachrichten werden geladen…",
  newsEmpty: "Keine aktuellen Meldungen.",
  newsUnavailable: "Nachrichten sind gerade nicht verfügbar.",

  stale: (time) => `Keine Verbindung – Stand ${time} Uhr`,

  countdownDays: (days) => (days === 1 ? "Tag" : "Tage"),
  countdownUntil: (label) => `bis ${label}`,
  countdownTomorrow: (label) => `Morgen: ${label}`,
  countdownPast: (label) => `${label} ist vorbei.`,
  counterSince: (date) => `seit ${date}`,
  noImages: "Noch keine Bilder ausgewählt. Bilder kommen in der Verwaltung unter „Logo und Bilder“ dazu.",
  noLogo: "Noch kein Logo hochgeladen.",
  dayOffset: (days) => (days === 1 ? "morgen" : days === -1 ? "gestern" : ""),
  hoursDifference: (hours) => {
    if (hours === 0) return "gleiche Zeit";
    const sign = hours > 0 ? "+" : "−";
    const value = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(Math.abs(hours));
    return `${sign}${value} Std.`;
  },
  weekShort: "KW",
  weekdaysShort: ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],

  setupTitle: "Verwaltung einrichten",
  setupText: "Im Firmennetz öffnen:",
  setupCode: "Code",

  conditions: {
    "clear-day": "Sonnig",
    "clear-night": "Klar",
    "partly-cloudy-day": "Teils bewölkt",
    "partly-cloudy-night": "Teils bewölkt",
    cloudy: "Bewölkt",
    fog: "Nebel",
    wind: "Windig",
    rain: "Regen",
    sleet: "Schneeregen",
    snow: "Schnee",
    hail: "Hagel",
    thunderstorm: "Gewitter",
  },
};
