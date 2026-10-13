// The screen's icons as SVG shapes on a 24 x 24 grid. They are built in the DOM so their colors
// come from the design tokens (classes i-*) instead of colors baked into an image.

// A cloud is three circles over a flat base. Its outline is the same shapes grown by the line
// width in the line color, covered by the shapes in the surface color: a clean union outline.
const CLOUD_PARTS = [
  ["circle", { cx: 8.5, cy: 15, r: 4 }],
  ["circle", { cx: 13, cy: 11.5, r: 5 }],
  ["circle", { cx: 17.5, cy: 15, r: 4 }],
  ["rect", { x: 8.5, y: 13, width: 9, height: 6 }],
];
const LINE = 1.5;
const RAISED = "translate(0 -3.5)";
const SMALL_SUN_RAYS = "M7 1.5v1.5M1.5 7h1.5M3.1 3.1l1.06 1.06M10.9 3.1l-1.06 1.06M3.1 10.9l1.06-1.06";

function cloud(transform, tone = "") {
  const extra = transform ? { transform } : {};
  const grown = CLOUD_PARTS.map(([tag, a]) => [
    tag,
    tag === "circle" ? { ...a, r: a.r + LINE, ...extra } : { ...a, height: a.height + LINE, ...extra },
  ]);
  return [
    ...grown.map(([tag, a]) => [tag, { ...a, class: `i-cloud-line ${tone}`.trim() }]),
    ...CLOUD_PARTS.map(([tag, a]) => [tag, { ...a, ...extra, class: "i-cloud" }]),
  ];
}

export const ICONS = {
  "clear-day": [
    ["path", { d: "M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.28 5.28l1.42 1.42M17.3 17.3l1.42 1.42M5.28 18.72l1.42-1.42M17.3 6.7l1.42-1.42", class: "i-line" }],
    ["circle", { cx: 12, cy: 12, r: 4.5, class: "i-sun" }],
  ],
  "clear-night": [["path", { d: "M19.5 14.6A8 8 0 1 1 9.4 4.5a6.4 6.4 0 0 0 10.1 10.1Z", class: "i-moon" }]],
  "partly-cloudy-day": [
    ["path", { d: SMALL_SUN_RAYS, class: "i-line" }],
    ["circle", { cx: 7, cy: 7, r: 3, class: "i-sun" }],
    ...cloud("translate(1 1)"),
  ],
  "partly-cloudy-night": [
    ["path", { d: "M10.4 8.4A4.4 4.4 0 1 1 5 2.6a3.6 3.6 0 0 0 5.4 5.8Z", class: "i-moon" }],
    ...cloud("translate(1 1)"),
  ],
  cloudy: [...cloud("translate(7.5 -2) scale(0.65)", "i-muted"), ...cloud("translate(-1.5 1)")],
  fog: [...cloud(RAISED), ["path", { d: "M4 18.5h16M6.5 21.5h11", class: "i-line i-muted" }]],
  wind: [["path", { d: "M3 9h10.5a2.5 2.5 0 1 0-2.5-2.5M3 13h14.5a2.5 2.5 0 1 1-2.5 2.5M3 17h7", class: "i-line" }]],
  rain: [...cloud(RAISED), ["path", { d: "M8.5 18l-1 2.5M12.5 18l-1 2.5M16.5 18l-1 2.5", class: "i-line i-rain" }]],
  sleet: [
    ...cloud(RAISED),
    ["path", { d: "M9 18l-1 2.5M15 18l-1 2.5", class: "i-line i-rain" }],
    ["circle", { cx: 12, cy: 19.5, r: 0.9, class: "i-snow" }],
  ],
  snow: [
    ...cloud(RAISED),
    ["circle", { cx: 8, cy: 18.5, r: 0.9, class: "i-snow" }],
    ["circle", { cx: 12, cy: 20.5, r: 0.9, class: "i-snow" }],
    ["circle", { cx: 16, cy: 18.5, r: 0.9, class: "i-snow" }],
  ],
  hail: [
    ...cloud(RAISED),
    ["circle", { cx: 8.5, cy: 19, r: 1.1, class: "i-hail" }],
    ["circle", { cx: 12.5, cy: 20.5, r: 1.1, class: "i-hail" }],
    ["circle", { cx: 16, cy: 18.5, r: 1.1, class: "i-hail" }],
  ],
  thunderstorm: [...cloud(RAISED), ["path", { d: "M12.5 15.5l-2.5 4h3l-1.5 3.5", class: "i-line i-bolt" }]],

  warning: [["path", { d: "M12 3.5 21.5 20h-19ZM12 10v4.5M12 17.2v.1", class: "i-line" }]],
  offline: [...cloud("translate(-1 -1)"), ["path", { d: "M3.5 3.5l17 17", class: "i-line" }]],
  "wind-small": [["path", { d: "M3 9h10.5a2.5 2.5 0 1 0-2.5-2.5M3 13h14.5a2.5 2.5 0 1 1-2.5 2.5M3 17h7", class: "i-line" }]],
  droplet: [["path", { d: "M12 3.5s6 6.4 6 10.5a6 6 0 0 1-12 0c0-4.1 6-10.5 6-10.5Z", class: "i-line" }]],
  umbrella: [["path", { d: "M3 12a9 9 0 0 1 18 0ZM12 12v6.5a2 2 0 0 1-4 0M12 3v0", class: "i-line" }]],
  sunrise: [["path", { d: "M6.5 16a5.5 5.5 0 0 1 11 0M3 19.5h18M12 3v6M9 6l3-3 3 3", class: "i-line" }]],
  sunset: [["path", { d: "M6.5 16a5.5 5.5 0 0 1 11 0M3 19.5h18M12 3v6M9 6l3 3 3-3", class: "i-line" }]],
};
