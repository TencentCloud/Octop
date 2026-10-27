const KNOWN_EXTENSIONS = [".ts", ".js", ".mjs", ".cjs", ".json", ".node"];

export function resolve(specifier, context, nextResolve) {
  if (!specifier.startsWith("./") && !specifier.startsWith("../")) {
    return nextResolve(specifier, context);
  }
  const base = specifier.slice(specifier.lastIndexOf("/") + 1);
  if (KNOWN_EXTENSIONS.some((ext) => base.endsWith(ext))) {
    return nextResolve(specifier, context);
  }
  return nextResolve(`${specifier}.ts`, context);
}
