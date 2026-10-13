// Widget types and the module that draws each of them. Every type in shared/widgets.json needs one.

import * as clock from "./clock.js";
import { stockWidget as stock, transitWidget as transit } from "./markets.js";
import * as news from "./news.js";
import { calendar, counter, countdown, logo, message, slideshow, worldclock } from "./simple.js";
import * as weather from "./weather.js";

export const WIDGETS = { clock, weather, news, logo, message, countdown, worldclock, calendar, slideshow, counter, stock, transit };
