"""Per-frame detection of blue-dyed water in the tabletop tray."""
import threading
import time

import cv2
import numpy as np


def detect_water(frame_rgb):
    """Return contours of cyan/blue dye. Colour alone cannot determine depth."""
    hsv = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array([75, 65, 35]), np.array([135, 255, 255]))
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    minimum = max(80, mask.size * 0.0005)
    polygons = []
    area = 0.0
    if hierarchy is not None:
        for index, contour in enumerate(contours):
            if hierarchy[0, index, 3] != -1 or cv2.contourArea(contour) < minimum:
                continue
            # Include holes so undyed terrain inside the water stays unshaded.
            rings = [contour]
            child = hierarchy[0, index, 2]
            while child != -1:
                rings.append(contours[child])
                child = hierarchy[0, child, 0]
            for ring in rings:
                poly = cv2.approxPolyDP(ring, 1.5, True)
                polygons.append(poly.reshape(-1, 2).tolist())
            area += cv2.contourArea(contour)
    return {"polygons": polygons, "coverage_pct": round(100 * area / mask.size, 1),
            "width": frame_rgb.shape[1], "height": frame_rgb.shape[0],
            "method": "blue-dye colour segmentation", "ts": time.time()}


class LiveAnalysis:
    def __init__(self, frame_source, record):
        self.frames = frame_source
        self.record = record
        self.lock = threading.Lock()
        self.last_frame = None
        self.result = None

    def status(self):
        with self.lock:
            frame = self.frames()
            if frame is None:
                return {"polygons": [], "reason": "Waiting for live video", "age_s": None}
            if frame is not self.last_frame:
                self.result = detect_water(frame)
                self.last_frame = frame
                self.record("live_water_analysis", frame=cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
                            analysis=self.result)
            return {**self.result, "age_s": round(time.time() - self.result["ts"], 2)}
class FrameOverlay:
    """Render segmentation and user-aligned tracked regions onto the same video frame."""
    def __init__(self):
        self.lock = threading.Lock()
        self.settings = {"enabled": True, "water": True, "car": True, "tray": True, "labels": True,
                         "demo_depth": None, "demo_stddev": 0.02}
        self.regions = {}
        self.manual_regions = set()
        self.scene_visible = False
        self.frame_at = 0.0
        self.previous = None
        self.points = None
        self.ms = 0.0
        self.noise = 0.0
        self.noise_at = time.monotonic()
        self.rng = np.random.default_rng()

    def configure(self, body):
        with self.lock:
            if "demo_depth" in body or "demo_stddev" in body:
                self.noise = 0.0
                self.noise_at = time.monotonic()
            for key in self.settings:
                if key in body:
                    self.settings[key] = body[key]
            for key in ("tray", "car"):
                if key + "_points" in body:
                    self.regions[key] = np.float32(body[key + "_points"])
                    self.manual_regions.add(key)
                    self.previous = None
                    self.points = None

    def seed_geometry(self, frame_bgr, geometry):
        """Use a validated gauge pose to acquire boxes before local frame tracking."""
        with self.lock:
            updated = False
            for kind in ("car", "tray"):
                polygon = geometry.get(kind + "_polygon", [])
                if kind not in self.manual_regions and polygon:
                    self.regions[kind] = np.float32(polygon)
                    updated = True
            if updated:
                self.previous = cv2.cvtColor(cv2.resize(frame_bgr, (480, 360)), cv2.COLOR_BGR2GRAY)
                mask = np.zeros_like(self.previous)
                scale = np.array([480 / frame_bgr.shape[1], 360 / frame_bgr.shape[0]])
                for polygon in self.regions.values():
                    cv2.fillConvexPoly(mask, (polygon * scale).astype(np.int32), 255)
                self.points = cv2.goodFeaturesToTrack(self.previous, 160, 0.01, 5, mask=mask)

    def gauge_value(self):
        with self.lock:
            visible = self.scene_visible and time.time() - self.frame_at < 1.5
            value = self.settings["demo_depth"]
            return visible, None if value is None else max(0, value + self.noise)

    def render(self, frame_rgb):
        start = time.perf_counter()
        out = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        small = cv2.resize(out, (480, 360))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        scale = np.array([480 / out.shape[1], 360 / out.shape[0]], np.float32)
        detected = detect_water(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        with self.lock:
            settings = self.settings.copy()
            now = time.monotonic()
            decay = np.exp(-min(5.0, now - self.noise_at) / 1.5)
            self.noise = decay * self.noise + settings["demo_stddev"] * np.sqrt(1 - decay**2) * self.rng.normal()
            self.noise_at = now
            depth_noise = self.noise
            if self.previous is not None and self.points is not None:
                moved, valid, _ = cv2.calcOpticalFlowPyrLK(self.previous, gray, self.points, None)
                if moved is not None:
                    good = valid.ravel() == 1
                    transform, inliers = (None, None)
                    if good.sum() >= 8:
                        transform, inliers = cv2.estimateAffinePartial2D(
                            self.points[good], moved[good], method=cv2.RANSAC, ransacReprojThreshold=2)
                    if transform is not None and inliers.sum() >= 8:
                        for key, region in self.regions.items():
                            self.regions[key] = (cv2.transform((region * scale)[None], transform)[0] / scale)
                    else:
                        self.regions.clear()
                        self.manual_regions.clear()
            if gray.std() < 3:
                self.regions.clear()
                self.manual_regions.clear()
            mask = np.zeros_like(gray)
            for region in self.regions.values():
                cv2.fillConvexPoly(mask, (region * scale).astype(np.int32), 255)
            mask = cv2.dilate(mask, np.ones((21,21), np.uint8))
            self.points = cv2.goodFeaturesToTrack(gray, 160, 0.01, 5, mask=mask) if mask.any() else None
            self.previous = gray
            regions = {key: value.copy() for key, value in self.regions.items()}
            self.scene_visible = bool(detected["polygons"] or regions)
            self.frame_at = time.time()
        if not settings["enabled"]:
            return out
        if settings["water"]:
            for ring in detected["polygons"]:
                cv2.polylines(out, [(np.float32(ring) / scale).astype(np.int32)], True, (255, 240, 0), 2)
        for kind, polygon in regions.items():
            if settings[kind]:
                color = (0, 50, 255) if kind == "car" else (255, 240, 0)
                cv2.polylines(out, [polygon.astype(np.int32)], True, color, 2)
                if settings["labels"]:
                    x, y = polygon.min(axis=0).astype(int)
                    cv2.putText(out, "VEHICLE" if kind == "car" else "TRAY", (max(0,x), max(20,y-8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        self.ms = (time.perf_counter() - start) * 1000
        return out
