export function setup() {
  window.dispatchEvent(new Event("plugin-test:setup"));
  return () => window.dispatchEvent(new Event("plugin-test:cleanup"));
}
