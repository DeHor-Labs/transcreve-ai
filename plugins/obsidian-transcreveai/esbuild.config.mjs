import builtins from "builtin-modules";
import esbuild from "esbuild";

const production = process.argv[2] === "production";

const context = await esbuild.context({
  banner: {
    js: "/* TranscreveAI Obsidian plugin */",
  },
  bundle: true,
  entryPoints: ["src/main.ts"],
  external: [
    "obsidian",
    "electron",
    "@codemirror/autocomplete",
    "@codemirror/collab",
    "@codemirror/commands",
    "@codemirror/language",
    "@codemirror/lint",
    "@codemirror/search",
    "@codemirror/state",
    "@codemirror/view",
    ...builtins,
  ],
  format: "cjs",
  logLevel: "info",
  minify: production,
  outfile: "main.js",
  platform: "browser",
  sourcemap: production ? false : "inline",
  target: "es2022",
});

if (production) {
  await context.rebuild();
  await context.dispose();
} else {
  await context.watch();
}
