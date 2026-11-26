/// <reference types="vite/client" />

declare module "*.wasm?url" {
  const src: string;
  export default src;
}

// harfbuzzjs ships no types. src/lib/harfbuzz.ts uses only these two entry
// points: the Emscripten factory and the wrapper that turns it into the API.
declare module "harfbuzzjs/hb.js" {
  const createHarfBuzz: (options?: { locateFile?: (path: string) => string }) => Promise<unknown>;
  export default createHarfBuzz;
}

declare module "harfbuzzjs/hbjs.js" {
  const hbjs: (module: unknown) => unknown;
  export default hbjs;
}
