import { describe, expect, it } from "vitest";

import { camera, dot, facing, keptSegment, rayBox, type Vec3 } from "./orbit";

const close = (a: Vec3, b: Vec3) => a.forEach((x, i) => expect(x).toBeCloseTo(b[i] ?? NaN, 9));

describe("camera", () => {
  it("is an orthonormal right-handed frame looking at the target", () => {
    const c = camera({ yaw: 0.7, pitch: 0.4, distance: 10 }, [1, 2, 3]);
    expect(dot(c.forward, c.right)).toBeCloseTo(0, 12);
    expect(dot(c.forward, c.up)).toBeCloseTo(0, 12);
    expect(dot(c.right, c.up)).toBeCloseTo(0, 12);
    expect(c.up[2]).toBeGreaterThan(0);
    const toTarget: Vec3 = [1 - c.eye[0], 2 - c.eye[1], 3 - c.eye[2]];
    close(toTarget, [c.forward[0] * 10, c.forward[1] * 10, c.forward[2] * 10]);
  });

  it("faces a cut from the side its normal points to", () => {
    const c = camera(facing([0, -1, 0], 50, 0), [0, 0, 0]);
    close(c.eye, [0, -50, 0]);
    close(c.right, [1, 0, 0]); // the cut's u axis, as in the 2D image
    close(c.up, [0, 0, 1]);
  });
});

describe("rays", () => {
  it("finds where a ray crosses a box", () => {
    expect(rayBox([-5, 0.5, 0.5], [1, 0, 0], [0, 0, 0], [1, 1, 1])).toEqual([5, 6]);
    expect(rayBox([-5, 2, 0.5], [1, 0, 0], [0, 0, 0], [1, 1, 1])).toBeNull();
  });

  it("keeps the part of a segment behind the cut", () => {
    // Cut at y = 0 with normal -y: keep y >= 0. Ray from y = -5 heading +y.
    const kept = keptSegment([0, -5, 0], [0, 1, 0], 2, 9, [0, -1, 0], 0);
    expect(kept).toEqual({ near: 5, far: 9, atCut: true });
    // Heading away from the kept side: nothing left after the cut.
    expect(keptSegment([0, -5, 0], [0, -1, 0], 0, 9, [0, -1, 0], 0)).toBeNull();
  });
});
