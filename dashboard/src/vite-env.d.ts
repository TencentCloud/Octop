/// <reference types="vite/client" />
/// <reference types="vite-plugin-svgr/client" />

declare module "*.less" {
  const classes: { [key: string]: string };
  export default classes;
}
