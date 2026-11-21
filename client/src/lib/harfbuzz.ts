// Stands in for the "harfbuzzjs" package that satori imports (aliased in
// vite.config.ts). The package's own index.js starts the Emscripten module with
// no options, so the loader looks for a bare "hb.wasm" next to the page: inside
// a bundled module chunk document.currentScript is null, the request hits the
// SPA route, and the build never ships the file, so card export fails in
// production. Here the wasm is a hashed Vite asset (/assets/hb-<hash>.wasm,
// served from 'self') and locateFile points the loader straight at it.
import createHarfBuzz from "harfbuzzjs/hb.js";
import hbjs from "harfbuzzjs/hbjs.js";
import hbWasmUrl from "harfbuzzjs/hb.wasm?url";

export default createHarfBuzz({ locateFile: () => hbWasmUrl }).then(hbjs);
