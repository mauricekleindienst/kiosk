// Every text the screen shows. The screen is German only; a second language would be a second
// catalog with the same keys.

export const strings = {
  timeRegion: "Uhrzeit und Datum",
  calendarWeek: (week) => `KW ${week}`,
  holidayToday: (name) => `Heute: ${name}`,
  holidayTomorrow: (name) => `Morgen: ${name}`,
  holidayIn: (name, days) => `${name} in\u00a0${days}\u00a0Tagen`,

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

  newsLoading: "Nachrichten werden geladen…",
  newsEmpty: "Keine aktuellen Meldungen.",
  newsUnavailable: "Nachrichten sind gerade nicht verfügbar.",

  stale: (time) => `Keine Verbindung – Stand ${time} Uhr`,

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
