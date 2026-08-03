/** Compiles the STATIC Tailwind CSS used by the GrapesJS builder canvas
 *  (app/static/vendor/grapesjs/tailwind.css). We use a pre-built file instead of
 *  the runtime Tailwind Play CDN because the CDN's live MutationObserver re-ran on
 *  every canvas DOM change during a drag and broke block drag-and-drop.
 *
 *  Rebuild after adding new Tailwind classes to templates:
 *    printf '@tailwind base;@tailwind components;@tailwind utilities;' > tailwind.input.css
 *    npx -y tailwindcss@3.4.17 -c tailwind.build.config.js -i tailwind.input.css \
 *        -o app/static/vendor/grapesjs/tailwind.css --minify
 *    rm tailwind.input.css
 *
 *  Theme mirrors the inline config in layouts/base.html (and static/js/tw-config.js).
 */
module.exports = {
  content: ['./app/templates/**/*.html'],
  theme: {
    extend: {
      colors: {
        okyellow: '#FFC72C', okamber: '#E0A200', softyellow: '#FFF3CC',
        jet: '#141414', slate: '#6B6B6B', okgreen: '#2E7D32',
        okred: '#C62828', okbrandred: '#E11B22',
      },
      fontFamily: { display: ['Poppins', 'sans-serif'], body: ['Quicksand', 'sans-serif'] },
    },
  },
};
