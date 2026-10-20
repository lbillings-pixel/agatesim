import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import type { CutPlane, VoxelVolume } from "../api";
import { camera, clampPitch, dot, facing, type Orbit, type Vec3 } from "../lib/orbit";

// Ray-marching through the volume's colours (a 3D texture), stopping at the first
// solid voxel: the cavity's filling with its outer surface and, if the cut is on,
// the part between the viewer and the cut removed, so the cut face shows. The cut
// logic mirrors keptSegment in lib/orbit.ts.
const VERTEX = `#version 300 es
out vec2 ndc;
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  ndc = p * 2.0 - 1.0;
  gl_Position = vec4(ndc, 0.0, 1.0);
}`;

const FRAGMENT = `#version 300 es
precision highp float;
precision highp sampler3D;
uniform sampler3D volume;
uniform vec3 boxLo;
uniform vec3 boxSize;
uniform vec3 eye;
uniform vec3 forward;
uniform vec3 right;
uniform vec3 up;
uniform float tanHalf;
uniform float aspect;
uniform bool cutOn;
uniform vec3 cutNormal;
uniform float cutOffset;
uniform float stepMm;
uniform vec3 texel;
uniform highp sampler3D tdepTex;
uniform bool growthOn;
uniform float cutoff; // show material deposited by this code (0..254)
in vec2 ndc;
out vec4 colour;

// Whether material is shown at uvw: solid, and already deposited when animating.
float shown(vec3 uvw) {
  if (texture(volume, uvw).a <= 0.5) return 0.0;
  if (growthOn && texture(tdepTex, uvw).r * 255.0 > cutoff + 0.5) return 0.0;
  return 1.0;
}

void main() {
  vec3 dir = normalize(forward + ndc.x * tanHalf * aspect * right + ndc.y * tanHalf * up);
  vec3 inv = 1.0 / dir;
  vec3 a = (boxLo - eye) * inv;
  vec3 b = (boxLo + boxSize - eye) * inv;
  vec3 lo = min(a, b);
  vec3 hi = max(a, b);
  float near = max(max(max(lo.x, lo.y), lo.z), 0.0);
  float far = min(min(hi.x, hi.y), hi.z);
  if (far <= near) discard;
  bool atCut = false;
  if (cutOn) {
    float rate = dot(cutNormal, dir);
    float start = dot(cutNormal, eye) - cutOffset;
    if (abs(rate) < 1e-9) {
      if (start > 0.0) discard;
    } else {
      float t = -start / rate;
      if (rate > 0.0) far = min(far, t);
      else if (t > near) { near = t; atCut = true; }
    }
    if (far <= near) discard;
  }
  float t = near;
  for (int i = 0; i < 2048; i++) {
    if (t > far) break;
    vec3 p = eye + t * dir;
    vec3 uvw = (p - boxLo) / boxSize;
    vec4 s = texture(volume, uvw);
    if (s.a > 0.5 && shown(uvw) > 0.5) {
      vec3 n;
      if (atCut && i == 0) {
        n = cutNormal;
      } else if (growthOn) {
        // The growth front: shade by where shown material ends.
        vec3 o = 1.5 * texel;
        vec3 g = vec3(
          shown(uvw + vec3(o.x, 0.0, 0.0)) - shown(uvw - vec3(o.x, 0.0, 0.0)),
          shown(uvw + vec3(0.0, o.y, 0.0)) - shown(uvw - vec3(0.0, o.y, 0.0)),
          shown(uvw + vec3(0.0, 0.0, o.z)) - shown(uvw - vec3(0.0, 0.0, o.z)));
        n = length(g) > 1e-4 ? -normalize(g) : -dir;
      } else {
        vec3 g = vec3(
          texture(volume, uvw + vec3(texel.x, 0.0, 0.0)).a - texture(volume, uvw - vec3(texel.x, 0.0, 0.0)).a,
          texture(volume, uvw + vec3(0.0, texel.y, 0.0)).a - texture(volume, uvw - vec3(0.0, texel.y, 0.0)).a,
          texture(volume, uvw + vec3(0.0, 0.0, texel.z)).a - texture(volume, uvw - vec3(0.0, 0.0, texel.z)).a);
        n = length(g) > 1e-4 ? -normalize(g) : -dir;
      }
      vec3 rgb = s.rgb / s.a;
      float head = max(dot(n, -dir), 0.0);
      float key = max(dot(n, normalize(vec3(0.35, -0.45, 0.82))), 0.0);
      colour = vec4(rgb * (0.38 + 0.42 * head + 0.28 * key), 1.0);
      return;
    }
    t += stepMm;
  }
  discard;
}`;

interface Gl {
  gl: WebGL2RenderingContext;
  program: WebGLProgram;
  texture: WebGLTexture;
  tdep: WebGLTexture;
  uniforms: Record<string, WebGLUniformLocation | null>;
}

function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("WebGL: can't create a shader");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(`WebGL shader: ${gl.getShaderInfoLog(shader) ?? "compile error"}`);
  }
  return shader;
}

function setup(canvas: HTMLCanvasElement): Gl {
  const gl = canvas.getContext("webgl2", { antialias: false, premultipliedAlpha: false });
  if (!gl) throw new Error("This browser has no WebGL2, which the 3D view needs.");
  const program = gl.createProgram();
  gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX));
  gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(`WebGL program: ${gl.getProgramInfoLog(program) ?? "link error"}`);
  }
  const texture = gl.createTexture();
  const tdep = gl.createTexture();
  const names = [
    "volume", "boxLo", "boxSize", "eye", "forward", "right", "up", "tanHalf", "aspect",
    "cutOn", "cutNormal", "cutOffset", "stepMm", "texel", "tdepTex", "growthOn", "cutoff",
  ];
  const uniforms = Object.fromEntries(names.map((n) => [n, gl.getUniformLocation(program, n)]));
  return { gl, program, texture, tdep, uniforms };
}

const FOV = 0.6; // vertical field of view, radians

export interface Volume3DProps {
  volume: VoxelVolume | null;
  plane: CutPlane | null;
  busy: boolean;
  /** Shown over the view while it builds (a progress bar), in place of a plain note. */
  progress?: ReactNode;
  /** Share of formation time shown (1 = all), for the growth animation. */
  growth: number;
  /** Filled with a handle that renders frames for exporting the animation. */
  exportRef?: { current: Volume3DHandle | null };
}

export interface Volume3DHandle {
  /** Draw the view at growth t and return its canvas (read it at once). */
  renderAt: (t: number) => HTMLCanvasElement | null;
}

/** A rotatable view of the volume: drag to turn, scroll to zoom. */
export function Volume3D({ volume, plane, busy, progress, growth, exportRef }: Volume3DProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const glRef = useRef<Gl | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Set up WebGL as soon as the canvas exists.
  const attach = useCallback((canvas: HTMLCanvasElement | null) => {
    canvasRef.current = canvas;
    if (!canvas) {
      // Leaving the screen: give the context back now. Browsers keep only about
      // 16 and otherwise drop the oldest with a warning, after a while.
      glRef.current?.gl.getExtension("WEBGL_lose_context")?.loseContext();
      glRef.current = null;
      return;
    }
    if (glRef.current) return;
    try {
      glRef.current = setup(canvas);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);
  const [cutOn, setCutOn] = useState(true);
  const [orbit, setOrbit] = useState<Orbit | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);

  const box = volume
    ? {
        lo: volume.origin_mm,
        size: [volume.nx * volume.dx_mm, volume.ny * volume.dx_mm, volume.nz * volume.dx_mm] as Vec3,
      }
    : null;
  const extent = box ? Math.hypot(...box.size) : 1;
  const target: Vec3 = box
    ? [box.lo[0] + box.size[0] / 2, box.lo[1] + box.size[1] / 2, box.lo[2] + box.size[2] / 2]
    : [0, 0, 0];

  // Start facing the cut; keep the user's view once they turn or zoom it.
  const normal = plane?.normal;
  const view: Orbit | null = orbit ?? (normal ? facing(normal, 1.9 * extent) : null);
  const viewRef = useRef(view);
  const extentRef = useRef(extent);
  useEffect(() => {
    viewRef.current = view;
    extentRef.current = extent;
  });

  // Upload the colours when the volume changes.
  useEffect(() => {
    const g = glRef.current;
    if (!g || !volume) return;
    const { gl, texture } = g;
    gl.bindTexture(gl.TEXTURE_3D, texture);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGBA8, volume.nx, volume.ny, volume.nz, 0, gl.RGBA, gl.UNSIGNED_BYTE, volume.rgba);
    for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_3D, p, gl.LINEAR);
    for (const p of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R]) {
      gl.texParameteri(gl.TEXTURE_3D, p, gl.CLAMP_TO_EDGE);
    }
    // Deposition times, for the growth animation: exact per voxel, not blended.
    gl.bindTexture(gl.TEXTURE_3D, g.tdep);
    const times = volume.tdep ?? new Uint8Array(volume.nx * volume.ny * volume.nz);
    gl.texImage3D(gl.TEXTURE_3D, 0, gl.R8, volume.nx, volume.ny, volume.nz, 0, gl.RED, gl.UNSIGNED_BYTE, times);
    for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_3D, p, gl.NEAREST);
    for (const p of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R]) {
      gl.texParameteri(gl.TEXTURE_3D, p, gl.CLAMP_TO_EDGE);
    }
  }, [volume]);


  // Draws the current view (at growth `shown`); scheduled below.
  function draw(shown: number = growth) {
    const g = glRef.current;
    const canvas = canvasRef.current;
    if (!g || !canvas || !volume || !box || !view) return;
    const { gl, program, uniforms: u } = g;
    const width = Math.round(canvas.clientWidth * window.devicePixelRatio);
    const height = Math.round(canvas.clientHeight * window.devicePixelRatio);
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    const cam = camera(view, target);
    gl.viewport(0, 0, width, height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(program);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_3D, g.texture);
    gl.uniform1i(u.volume ?? null, 0);
    gl.uniform3fv(u.boxLo ?? null, box.lo);
    gl.uniform3fv(u.boxSize ?? null, box.size);
    gl.uniform3fv(u.eye ?? null, cam.eye);
    gl.uniform3fv(u.forward ?? null, cam.forward);
    gl.uniform3fv(u.right ?? null, cam.right);
    gl.uniform3fv(u.up ?? null, cam.up);
    gl.uniform1f(u.tanHalf ?? null, Math.tan(FOV / 2));
    gl.uniform1f(u.aspect ?? null, width / Math.max(height, 1));
    const on = cutOn && plane !== null;
    gl.uniform1i(u.cutOn ?? null, on ? 1 : 0);
    gl.uniform3fv(u.cutNormal ?? null, plane?.normal ?? [0, 0, 1]);
    gl.uniform1f(u.cutOffset ?? null, plane ? dot(plane.normal, plane.origin) : 0);
    gl.uniform1f(u.stepMm ?? null, 0.5 * volume.dx_mm);
    gl.uniform3fv(u.texel ?? null, [1 / volume.nx, 1 / volume.ny, 1 / volume.nz]);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_3D, g.tdep);
    gl.uniform1i(u.tdepTex ?? null, 1);
    gl.uniform1i(u.growthOn ?? null, volume.tdep && shown < 1 ? 1 : 0);
    gl.uniform1f(u.cutoff ?? null, Math.round(Math.min(Math.max(shown, 0), 1) * 254));
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  // Draw whenever anything changes, at most once per frame (a fast drag changes
  // the view many times between frames).
  useEffect(() => {
    const frame = requestAnimationFrame(() => draw());
    return () => cancelAnimationFrame(frame);
  });

  useEffect(() => {
    if (!exportRef) return;
    exportRef.current = {
      renderAt: (t) => {
        draw(t);
        return canvasRef.current;
      },
    };
  });

  const onPointerDown = (e: React.PointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY };
    (e.target as Element).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const start = drag.current;
    if (!start || !view) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    drag.current = { x: e.clientX, y: e.clientY };
    setOrbit({ ...view, yaw: view.yaw - dx * 0.01, pitch: clampPitch(view.pitch + dy * 0.01) });
  };
  // Zoom with the wheel; a native listener, so the page doesn't scroll as well.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const ext = extentRef.current;
      const o = viewRef.current;
      if (o) {
        setOrbit({ ...o, distance: Math.min(6 * ext, Math.max(0.6 * ext, o.distance * Math.exp(e.deltaY * 0.001))) });
      }
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, []);

  return (
    <figure className="volume-view">
      <div className="volume-stage">
        <canvas
          ref={attach}
          aria-label="3D view of the volume: drag to turn, scroll to zoom"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={() => (drag.current = null)}
        />
        {(busy || !volume) && !error && (
          <div className={`volume-note small${progress ? " with-progress" : " muted"}`}>
            {progress ?? "Building the 3D view…"}
          </div>
        )}
        {error && <div className="volume-note error small">{error}</div>}
      </div>
      <figcaption className="volume-caption small">
        <label className="inline">
          <input type="checkbox" checked={cutOn} onChange={(e) => setCutOn(e.target.checked)} /> Open at the cut
        </label>
        <button type="button" onClick={() => normal && setOrbit(facing(normal, 1.9 * extent))}>
          Face the cut
        </button>
        <span className="muted">
          {volume ? `${volume.nx}×${volume.ny}×${volume.nz} voxels · ${volume.elapsed_ms} ms` : ""} · drag to turn, scroll to zoom
        </span>
      </figcaption>
    </figure>
  );
}
