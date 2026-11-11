import { loader } from "@monaco-editor/react";

// Full AMD build, same origin as the page. Vite serves node_modules'
// monaco-editor/min/vs here in dev and copies it to dist/monaco/vs on build.
// Workers are loaded relative to this prefix, so they stay on this host.
loader.config({
  paths: {
    vs: "/monaco/vs",
  },
});

export { default } from "@monaco-editor/react";
