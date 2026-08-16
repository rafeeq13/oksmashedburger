/* Contrast maths for the design editors.
 *
 * The point of this file is that a colour pair can be judged BEFORE it ships:
 * the editor asks it whether the text a client just picked can actually be read
 * on the background they picked, in every state, and what to use instead when
 * it cannot.
 *
 * WCAG 2.1: relative luminance, then (L1 + 0.05) / (L2 + 0.05).
 */
(function (root) {
  "use strict";

  var NAMED = {
    black: "#000000", white: "#ffffff", red: "#ff0000", green: "#008000",
    blue: "#0000ff", yellow: "#ffff00", transparent: null, inherit: null,
    currentcolor: null, none: null, initial: null, unset: null, revert: null
  };

  /* Accepts #rgb, #rrggbb, #rrggbbaa, rgb()/rgba() and the few keywords that
     turn up in this codebase. Returns [r, g, b, a] or null when the value
     carries no colour of its own (transparent, inherit, a gradient). */
  function parse(value) {
    if (!value) return null;
    var v = String(value).trim().toLowerCase();
    if (Object.prototype.hasOwnProperty.call(NAMED, v)) {
      if (NAMED[v] === null) return null;
      v = NAMED[v];
    }
    if (v.charAt(0) === "#") {
      var h = v.slice(1);
      if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
      if (h.length === 8) {
        return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16),
                parseInt(h.slice(4, 6), 16), parseInt(h.slice(6, 8), 16) / 255];
      }
      if (h.length !== 6) return null;
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16),
              parseInt(h.slice(4, 6), 16), 1];
    }
    var m = v.match(/^rgba?\(([^)]+)\)/);
    if (m) {
      var p = m[1].split(/[,\s/]+/).filter(Boolean).map(parseFloat);
      if (p.length < 3 || p.some(isNaN)) return null;
      return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    }
    return null;
  }

  function hex(rgb) {
    function two(n) {
      var s = Math.max(0, Math.min(255, Math.round(n))).toString(16);
      return s.length === 1 ? "0" + s : s;
    }
    return "#" + two(rgb[0]) + two(rgb[1]) + two(rgb[2]);
  }

  /* A translucent colour is only readable in terms of what is behind it, so
     flatten it against its backdrop before measuring anything. */
  function flatten(rgb, backdrop) {
    if (!rgb) return null;
    var a = rgb.length > 3 ? rgb[3] : 1;
    if (a >= 1) return [rgb[0], rgb[1], rgb[2], 1];
    var b = backdrop || [255, 255, 255, 1];
    return [rgb[0] * a + b[0] * (1 - a),
            rgb[1] * a + b[1] * (1 - a),
            rgb[2] * a + b[2] * (1 - a), 1];
  }

  function luminance(rgb) {
    var c = [rgb[0], rgb[1], rgb[2]].map(function (v) {
      v = v / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }

  /* The number the editor shows. Returns null when either colour is unknown —
     better to say nothing than to invent a verdict. */
  function ratio(fg, bg, backdrop) {
    var f = flatten(parse(fg), parse(backdrop) || parse(bg));
    var b = flatten(parse(bg), parse(backdrop));
    if (!f || !b) return null;
    var l1 = luminance(f), l2 = luminance(b);
    var hi = Math.max(l1, l2), lo = Math.min(l1, l2);
    return (hi + 0.05) / (lo + 0.05);
  }

  /* WCAG AA is 4.5:1 for body-sized text and 3:1 for large text; 3:1 is also
     the bar for a border or icon that carries meaning. */
  function verdict(r, opts) {
    opts = opts || {};
    var need = opts.large ? 3 : (opts.ui ? 3 : 4.5);
    if (r === null) return { level: "unknown", text: "Not checked", need: need };
    if (r < 1.15) {
      return { level: "same", text: "Text and background are the same colour",
               need: need, ratio: r };
    }
    if (r < need) {
      return { level: "fail", text: "Low contrast — this will be hard to read",
               need: need, ratio: r };
    }
    if (r < 7) return { level: "pass", text: "Readable", need: need, ratio: r };
    return { level: "great", text: "Easy to read", need: need, ratio: r };
  }

  function show(r) {
    if (r === null) return "—";
    return (Math.round(r * 10) / 10).toFixed(1) + ":1";
  }

  /* Suggest a foreground from the site's own palette rather than inventing a
     colour: the brand should survive being made readable. */
  function suggestFor(bg, palette, opts) {
    var b = parse(bg);
    if (!b) return [];
    var want = (opts && opts.large) ? 3 : 4.5;
    var seen = {};
    var out = [];
    (palette || []).concat(["#ffffff", "#141414", "#000000"]).forEach(function (c) {
      var p = parse(c);
      if (!p) return;
      var key = hex(p);
      if (seen[key]) return;
      seen[key] = 1;
      var r = ratio(key, bg);
      if (r !== null && r >= want) out.push({ color: key, ratio: r });
    });
    out.sort(function (a, b2) { return b2.ratio - a.ratio; });
    return out.slice(0, 4);
  }

  /* The colours this site already uses, read off the page so the suggestions
     stay inside the existing identity. */
  function palette(doc) {
    var names = ["--ok-jet", "--ok-ink", "--ok-amber", "--ok-yellow", "--ok-red",
                 "--ok-slate", "--ok-cream", "--ok-soft", "--ok-line",
                 "--theme-ink", "--theme-body", "--theme-primary", "--theme-accent"];
    var cs = getComputedStyle((doc || document).documentElement);
    var out = [];
    names.forEach(function (n) {
      var v = (cs.getPropertyValue(n) || "").trim();
      if (v && parse(v)) out.push(hex(parse(v)));
    });
    return out;
  }

  root.okContrast = {
    parse: parse, hex: hex, ratio: ratio, verdict: verdict, show: show,
    flatten: flatten, luminance: luminance,
    suggestFor: suggestFor, palette: palette
  };
})(window);
