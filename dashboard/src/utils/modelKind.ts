/**
 * Classify 3D model files by extension for in-browser WebGL preview.
 *
 * Kept separate from ``mediaKind`` (which backs ``/media/preview`` and chat
 * attachment routing) so 3D models load through the authenticated workspace
 * download stream without altering chat attachment MIME routing.
 */

export type Model3DKind = "glb" | "gltf" | "stl" | "obj" | "fbx";

const MODEL_3D_EXT: Record<string, Model3DKind> = {
  glb: "glb",
  gltf: "gltf",
  stl: "stl",
  obj: "obj",
  fbx: "fbx",
};

export function getModelKind(path: string): Model3DKind | null {
  const clean = (path.split(/[?#]/, 1)[0] ?? path).trim();
  const base = clean.split(/[\\/]/).pop() ?? "";
  const dot = base.lastIndexOf(".");
  if (dot <= 0 || dot === base.length - 1) return null;
  const ext = base.slice(dot + 1).toLowerCase();
  return MODEL_3D_EXT[ext] ?? null;
}
