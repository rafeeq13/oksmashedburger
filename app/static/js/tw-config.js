/* Brand Tailwind config — mirrors the inline config in layouts/base.html so the
   GrapesJS builder canvas renders the site's real brand colors and fonts.
   Loaded AFTER the Tailwind Play CDN (which re-processes on config change). */
window.tailwind = window.tailwind || {};
tailwind.config = {
  theme: {
    extend: {
      colors: {
        okyellow: '#FFC72C', okamber: '#E0A200', softyellow: '#FFF3CC',
        jet: '#141414', slate: '#6B6B6B', okgreen: '#2E7D32',
        okred: '#C62828', okbrandred: '#E11B22'
      },
      fontFamily: { display: ['Poppins', 'sans-serif'], body: ['Quicksand', 'sans-serif'] }
    }
  }
};
