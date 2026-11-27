/**
 * Interactive WebGL 3D model viewer (GLB / GLTF / STL / OBJ / FBX).
 *
 * Loaded lazily so ``three`` stays out of the initial bundle.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Tooltip } from "antd";
import {
  AlertCircle,
  ArrowDownToLine,
  Box,
  Grid3x3,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  RotateCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import cx from "classnames";
import { isNotFoundApiError } from "../utils/apiError";
import type { Model3DKind } from "../utils/modelKind";
import DocumentPreviewLoading from "./DocumentPreviewLoading";
import styles from "./Model3DPreviewCore.module.less";

export interface Model3DPreviewCoreProps {
  kind: Model3DKind;
  filename: string;
  fetchBlob: (
    onProgress?: (loaded: number, total: number) => void,
    signal?: AbortSignal,
  ) => Promise<Blob>;
  onDownload?: () => void | Promise<void>;
}

interface LoadedModel {
  root: THREE.Object3D;
  animations: THREE.AnimationClip[];
  triangleCount: number;
}

interface CameraPreset {
  position: THREE.Vector3;
  target: THREE.Vector3;
}

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}

function forEachMaterial(
  root: THREE.Object3D,
  visitor: (material: THREE.Material) => void,
): void {
  root.traverse((obj) => {
    if (!(obj instanceof THREE.Mesh)) return;
    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
    for (const mat of mats) {
      if (mat) visitor(mat);
    }
  });
}

function disposeObject3D(root: THREE.Object3D): void {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  root.traverse((obj) => {
    if (!(obj instanceof THREE.Mesh)) return;
    if (obj.geometry) geometries.add(obj.geometry);
    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
    for (const mat of mats) {
      if (!mat) continue;
      materials.add(mat);
      for (const value of Object.values(mat)) {
        if (value instanceof THREE.Texture) {
          textures.add(value);
        }
      }
    }
  });
  for (const tex of textures) tex.dispose();
  for (const mat of materials) mat.dispose();
  for (const geom of geometries) geom.dispose();
}

function countTriangles(root: THREE.Object3D): number {
  let triangles = 0;
  root.traverse((obj) => {
    if (!(obj instanceof THREE.Mesh)) return;
    const geom = obj.geometry;
    if (!geom) return;
    if (geom.index) {
      triangles += Math.floor(geom.index.count / 3);
    } else {
      const pos = geom.getAttribute("position");
      if (pos) triangles += Math.floor(pos.count / 3);
    }
  });
  return triangles;
}

export async function parseModelBlob(
  kind: Model3DKind,
  blob: Blob,
): Promise<LoadedModel> {
  let root: THREE.Object3D;
  let animations: THREE.AnimationClip[] = [];

  if (kind === "glb" || kind === "gltf") {
    const { GLTFLoader } = await import(
      "three/examples/jsm/loaders/GLTFLoader.js"
    );
    const loader = new GLTFLoader();
    const buffer = await blob.arrayBuffer();
    const gltf = await loader.parseAsync(buffer, "");
    root = gltf.scene || gltf.scenes[0];
    animations = gltf.animations ?? [];
  } else if (kind === "stl") {
    const { STLLoader } = await import(
      "three/examples/jsm/loaders/STLLoader.js"
    );
    const loader = new STLLoader();
    const geometry = loader.parse(await blob.arrayBuffer());
    geometry.computeVertexNormals();
    const hasColors = Boolean(geometry.getAttribute("color"));
    const material = new THREE.MeshStandardMaterial({
      color: hasColors ? 0xffffff : 0xcbd5e1,
      vertexColors: hasColors,
      roughness: 0.45,
      metalness: 0.15,
    });
    root = new THREE.Mesh(geometry, material);
  } else if (kind === "obj") {
    const { OBJLoader } = await import(
      "three/examples/jsm/loaders/OBJLoader.js"
    );
    const loader = new OBJLoader();
    root = loader.parse(await blob.text());
    root.traverse((obj) => {
      if (obj instanceof THREE.Mesh && !obj.material) {
        obj.material = new THREE.MeshStandardMaterial({
          color: 0xcbd5e1,
          roughness: 0.5,
          metalness: 0.1,
        });
      }
    });
  } else {
    const { FBXLoader } = await import(
      "three/examples/jsm/loaders/FBXLoader.js"
    );
    const loader = new FBXLoader();
    root = loader.parse(await blob.arrayBuffer(), "");
    animations = root.animations ?? [];
  }

  if (!root) {
    throw new Error("Empty 3D scene");
  }

  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) {
    disposeObject3D(root);
    throw new Error("Model contains no renderable geometry");
  }

  return {
    root,
    animations,
    triangleCount: countTriangles(root),
  };
}

function centerAndFrameModel(
  root: THREE.Object3D,
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
): { preset: CameraPreset; floorY: number; gridSize: number } {
  const box = new THREE.Box3().setFromObject(root);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());

  // Shift model so its bounding-box center rests at world origin.
  root.position.sub(center);

  const maxDim = Math.max(size.x, size.y, size.z, 0.001);
  const fovRad = THREE.MathUtils.degToRad(camera.fov);
  const distance = (maxDim / (2 * Math.tan(fovRad / 2))) * 1.65;

  camera.near = Math.max(maxDim * 0.002, 0.001);
  camera.far = Math.max(maxDim * 80, 100);
  camera.updateProjectionMatrix();

  const direction = new THREE.Vector3(0.75, 0.48, 0.9).normalize();
  const position = direction.multiplyScalar(distance);
  const target = new THREE.Vector3(0, 0, 0);

  camera.position.copy(position);
  controls.target.copy(target);
  controls.minDistance = maxDim * 0.25;
  controls.maxDistance = maxDim * 12;
  controls.update();

  return {
    preset: {
      position: position.clone(),
      target: target.clone(),
    },
    floorY: -size.y / 2,
    gridSize: Math.max(maxDim * 2.4, 1),
  };
}

export default function Model3DPreviewCore({
  kind,
  filename,
  fetchBlob,
  onDownload,
}: Model3DPreviewCoreProps) {
  const { t } = useTranslation();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadPhase, setLoadPhase] = useState<"file" | "parse">("file");
  const [downloadPercent, setDownloadPercent] = useState<number | null>(null);
  const [error, setError] = useState<"missing" | "webgl" | "error" | null>(
    null,
  );
  const [reloadNonce, setReloadNonce] = useState(0);
  const [triangleCount, setTriangleCount] = useState<number | null>(null);
  const [hasAnimations, setHasAnimations] = useState(false);

  const [autoRotate, setAutoRotate] = useState(true);
  const [wireframe, setWireframe] = useState(false);
  const [showGrid, setShowGrid] = useState(true);
  const [playingAnim, setPlayingAnim] = useState(true);

  const controlsRef = useRef<OrbitControls | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const presetRef = useRef<CameraPreset | null>(null);
  const modelRootRef = useRef<THREE.Object3D | null>(null);
  const gridRef = useRef<THREE.GridHelper | null>(null);
  const playingAnimRef = useRef(playingAnim);
  playingAnimRef.current = playingAnim;

  const onBlobProgress = useCallback((loaded: number, total: number) => {
    if (total > 0) setDownloadPercent((loaded / total) * 100);
  }, []);

  const handleRetry = useCallback(() => {
    setError(null);
    setReloadNonce((n) => n + 1);
  }, []);

  const handleResetView = useCallback(() => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    const preset = presetRef.current;
    if (!camera || !controls || !preset) return;
    camera.position.copy(preset.position);
    controls.target.copy(preset.target);
    controls.update();
  }, []);

  useEffect(() => {
    if (controlsRef.current) {
      controlsRef.current.autoRotate = autoRotate;
    }
  }, [autoRotate]);

  useEffect(() => {
    if (gridRef.current) {
      gridRef.current.visible = showGrid;
    }
  }, [showGrid]);

  useEffect(() => {
    const root = modelRootRef.current;
    if (!root) return;
    forEachMaterial(root, (mat) => {
      if ("wireframe" in mat) {
        (mat as THREE.Material & { wireframe: boolean }).wireframe = wireframe;
        mat.needsUpdate = true;
      }
    });
  }, [wireframe]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const abort = new AbortController();
    let cancelled = false;
    let frameId = 0;
    let renderer: THREE.WebGLRenderer | null = null;
    let scene: THREE.Scene | null = null;
    let controls: OrbitControls | null = null;
    let onUserInteract: (() => void) | null = null;
    let onContextLost: ((event: Event) => void) | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let envTarget: THREE.WebGLRenderTarget | null = null;
    let pmremGenerator: THREE.PMREMGenerator | null = null;
    let loadedRoot: THREE.Object3D | null = null;
    let grid: THREE.GridHelper | null = null;
    let mixer: THREE.AnimationMixer | null = null;
    let lastFrameTime = performance.now();

    setLoading(true);
    setLoadPhase("file");
    setDownloadPercent(null);
    setError(null);
    setTriangleCount(null);
    setHasAnimations(false);
    setAutoRotate(true);
    setWireframe(false);
    setShowGrid(true);
    setPlayingAnim(true);

    const run = async () => {
      try {
        const blob = await fetchBlob(onBlobProgress, abort.signal);
        if (cancelled) return;

        setLoadPhase("parse");
        const parsed = await parseModelBlob(kind, blob);
        if (cancelled) {
          disposeObject3D(parsed.root);
          return;
        }
        loadedRoot = parsed.root;

        const width = Math.max(host.clientWidth, 300);
        const height = Math.max(host.clientHeight, 280);

        try {
          renderer = new THREE.WebGLRenderer({
            antialias: true,
            alpha: true,
            powerPreference: "high-performance",
          });
        } catch {
          disposeObject3D(parsed.root);
          loadedRoot = null;
          if (!cancelled) {
            setError("webgl");
            setLoading(false);
          }
          return;
        }

        onContextLost = (event: Event) => {
          event.preventDefault();
          if (frameId) {
            cancelAnimationFrame(frameId);
            frameId = 0;
          }
          if (!cancelled) {
            setError("webgl");
            setLoading(false);
          }
        };
        renderer.domElement.addEventListener("webglcontextlost", onContextLost);

        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.setSize(width, height, false);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.05;

        host.innerHTML = "";
        host.appendChild(renderer.domElement);

        scene = new THREE.Scene();
        pmremGenerator = new THREE.PMREMGenerator(renderer);
        const roomEnv = new RoomEnvironment();
        envTarget = pmremGenerator.fromScene(roomEnv, 0.04);
        roomEnv.dispose();
        scene.environment = envTarget.texture;

        const hemi = new THREE.HemisphereLight(0xffffff, 0x475569, 0.7);
        scene.add(hemi);
        const keyLight = new THREE.DirectionalLight(0xffffff, 1.1);
        keyLight.position.set(4, 8, 6);
        scene.add(keyLight);
        const fillLight = new THREE.DirectionalLight(0xe2e8f0, 0.5);
        fillLight.position.set(-5, -2, -4);
        scene.add(fillLight);

        const camera = new THREE.PerspectiveCamera(
          45,
          width / height,
          0.01,
          100,
        );
        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controls.autoRotate = true;
        controls.autoRotateSpeed = 1.5;

        onUserInteract = () => {
          setAutoRotate(false);
        };
        controls.addEventListener("start", onUserInteract);

        const { preset, floorY, gridSize } = centerAndFrameModel(
          loadedRoot,
          camera,
          controls,
        );
        scene.add(loadedRoot);

        grid = new THREE.GridHelper(gridSize, 16, 0x64748b, 0x94a3b8);
        grid.position.y = floorY;
        const gridMats = Array.isArray(grid.material)
          ? grid.material
          : [grid.material];
        for (const m of gridMats) {
          m.opacity = 0.25;
          m.transparent = true;
        }
        scene.add(grid);

        if (parsed.animations.length > 0) {
          mixer = new THREE.AnimationMixer(loadedRoot);
          for (const clip of parsed.animations) {
            mixer.clipAction(clip).play();
          }
          setHasAnimations(true);
        }

        cameraRef.current = camera;
        controlsRef.current = controls;
        presetRef.current = preset;
        modelRootRef.current = loadedRoot;
        gridRef.current = grid;

        setTriangleCount(parsed.triangleCount);
        setLoading(false);

        const syncSize = () => {
          if (
            cancelled ||
            !renderer ||
            !host ||
            host.clientWidth === 0 ||
            host.clientHeight === 0
          ) {
            return;
          }
          const nextW = host.clientWidth;
          const nextH = host.clientHeight;
          camera.aspect = nextW / nextH;
          camera.updateProjectionMatrix();
          renderer.setSize(nextW, nextH, false);
        };

        resizeObserver = new ResizeObserver(syncSize);
        resizeObserver.observe(host);

        const activeScene = scene;
        const activeRenderer = renderer;
        const activeControls = controls;
        const animate = () => {
          if (cancelled) return;
          frameId = requestAnimationFrame(animate);
          const now = performance.now();
          const delta = (now - lastFrameTime) / 1000;
          lastFrameTime = now;
          if (mixer && playingAnimRef.current) {
            mixer.update(delta);
          }
          activeControls.update();
          activeRenderer.render(activeScene, camera);
        };
        animate();
      } catch (err) {
        if (cancelled || isAbortError(err)) return;
        setError(isNotFoundApiError(err) ? "missing" : "error");
        setLoading(false);
      }
    };

    void run();

    return () => {
      cancelled = true;
      abort.abort();
      if (frameId) cancelAnimationFrame(frameId);
      resizeObserver?.disconnect();
      if (controls && onUserInteract) {
        controls.removeEventListener("start", onUserInteract);
      }
      controls?.dispose();
      controlsRef.current = null;
      cameraRef.current = null;
      presetRef.current = null;
      modelRootRef.current = null;
      gridRef.current = null;
      mixer?.stopAllAction();
      if (loadedRoot) {
        disposeObject3D(loadedRoot);
      }
      if (grid) {
        grid.geometry.dispose();
        const mats = Array.isArray(grid.material)
          ? grid.material
          : [grid.material];
        for (const m of mats) m.dispose();
      }
      if (scene) {
        scene.environment = null;
      }
      envTarget?.dispose();
      pmremGenerator?.dispose();
      if (renderer) {
        if (onContextLost) {
          renderer.domElement.removeEventListener(
            "webglcontextlost",
            onContextLost,
          );
        }
        renderer.dispose();
        renderer.domElement.remove();
      }
    };
  }, [fetchBlob, kind, onBlobProgress, reloadNonce]);

  return (
    <div
      className={styles.root}
      aria-label={filename}
      data-testid="model-3d-preview"
    >
      <div ref={hostRef} className={styles.canvasHost} />

      {loading && !error && (
        <div className={styles.loadingOverlay}>
          <DocumentPreviewLoading phase={loadPhase} percent={downloadPercent} />
        </div>
      )}

      {error === "missing" && (
        <div className={styles.errorOverlay} role="status">
          <div className={styles.errorState}>
            <AlertCircle
              size={32}
              strokeWidth={1.6}
              className={styles.errorIcon}
            />
            <p className={styles.errorText}>
              {t("workspace.fileMaybeDeleted", "文件可能已被删除")}
            </p>
          </div>
        </div>
      )}

      {(error === "webgl" || error === "error") && (
        <div className={styles.errorOverlay} role="status">
          <div className={styles.errorState}>
            <AlertCircle
              size={32}
              strokeWidth={1.6}
              className={styles.errorIcon}
            />
            <p className={styles.errorText}>
              {error === "webgl"
                ? t(
                    "workspace.model3dWebglUnavailable",
                    "当前环境不支持 WebGL 3D 渲染，请下载模型后使用本地软件查看",
                  )
                : t("workspace.mediaLoadFailed", "无法加载预览")}
            </p>
            <div className={styles.errorActions}>
              {error === "error" && (
                <Button
                  size="small"
                  icon={<RefreshCw size={14} />}
                  onClick={handleRetry}
                >
                  {t("workspace.retryPreview", "重试")}
                </Button>
              )}
              {onDownload && (
                <Button
                  size="small"
                  type="primary"
                  icon={<ArrowDownToLine size={14} />}
                  onClick={() => void onDownload()}
                >
                  {t("common.download")}
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {!loading && !error && (
        <>
          <div className={styles.metaBadge}>
            <Box size={12} strokeWidth={2} aria-hidden />
            <span>{kind.toUpperCase()}</span>
            {triangleCount !== null && triangleCount > 0 && (
              <span>
                · {triangleCount.toLocaleString()}{" "}
                {t("workspace.model3dTriangles", "面")}
              </span>
            )}
          </div>

          <div className={styles.hintBadge}>
            {t("workspace.model3dOrbitHint", "左键旋转 · 滚轮缩放 · 右键平移")}
          </div>

          <div className={styles.toolbar}>
            {hasAnimations && (
              <Tooltip
                title={
                  playingAnim
                    ? t("workspace.model3dPauseAnim", "暂停动画")
                    : t("workspace.model3dPlayAnim", "播放动画")
                }
              >
                <button
                  type="button"
                  className={cx(
                    styles.toolbarBtn,
                    playingAnim && styles.toolbarBtnActive,
                  )}
                  onClick={() => setPlayingAnim((v) => !v)}
                  aria-label={
                    playingAnim
                      ? t("workspace.model3dPauseAnim", "暂停动画")
                      : t("workspace.model3dPlayAnim", "播放动画")
                  }
                >
                  {playingAnim ? <Pause size={15} /> : <Play size={15} />}
                </button>
              </Tooltip>
            )}
            <Tooltip title={t("workspace.model3dAutoRotate", "自动旋转")}>
              <button
                type="button"
                className={cx(
                  styles.toolbarBtn,
                  autoRotate && styles.toolbarBtnActive,
                )}
                onClick={() => setAutoRotate((v) => !v)}
                aria-label={t("workspace.model3dAutoRotate", "自动旋转")}
              >
                <RotateCw size={15} />
              </button>
            </Tooltip>
            <Tooltip title={t("workspace.model3dWireframe", "线框模式")}>
              <button
                type="button"
                className={cx(
                  styles.toolbarBtn,
                  wireframe && styles.toolbarBtnActive,
                )}
                onClick={() => setWireframe((v) => !v)}
                aria-label={t("workspace.model3dWireframe", "线框模式")}
              >
                <Box size={15} />
              </button>
            </Tooltip>
            <Tooltip title={t("workspace.model3dGrid", "参考网格")}>
              <button
                type="button"
                className={cx(
                  styles.toolbarBtn,
                  showGrid && styles.toolbarBtnActive,
                )}
                onClick={() => setShowGrid((v) => !v)}
                aria-label={t("workspace.model3dGrid", "参考网格")}
              >
                <Grid3x3 size={15} />
              </button>
            </Tooltip>
            <Tooltip title={t("workspace.model3dResetView", "重置视角")}>
              <button
                type="button"
                className={styles.toolbarBtn}
                onClick={handleResetView}
                aria-label={t("workspace.model3dResetView", "重置视角")}
              >
                <RotateCcw size={15} />
              </button>
            </Tooltip>
          </div>
        </>
      )}
    </div>
  );
}
