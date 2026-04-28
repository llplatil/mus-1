"""Arena U-Net inference utilities (EZM open/closed; NOR/NOF coming next).

Backend-agnostic. Loads a TinyUNet checkpoint, runs inference on a single
RGB/grayscale frame, and post-processes the predicted mask into the schema
expected by the existing marking panes (4 wedge points for EZM).

Usage:
    from mus1.compute.arena_unet import (
        load_ezm_unet, sample_video_frame, infer_ezm_mask, ezm_mask_to_wedge_points,
    )
    model = load_ezm_unet(path)
    frame = sample_video_frame(video_path, frame_idx)
    mask, meta = infer_ezm_mask(model, frame)
    wedges = ezm_mask_to_wedge_points(mask, meta)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np

# Lazy import torch/cv2 at function level — keeps the module importable
# in environments that don't have them (e.g. some agent tooling).


# ---------------------------------------------------------------------------
# Architecture (matches ml_workspace/ezm_arena_unet/runs/.../train_config.json:
#   base_ch=16, img_size=256, in_ch=1, n_classes=3)
# ---------------------------------------------------------------------------

def _build_tiny_unet(in_ch: int = 1, n_classes: int = 3, base: int = 16):
    """Construct the TinyUNet architecture used by EZM and NOR/NOF training."""
    import torch.nn as nn
    import torch

    class ConvBlock(nn.Module):
        def __init__(self, ic, oc):
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv2d(ic, oc, 3, padding=1), nn.BatchNorm2d(oc), nn.ReLU(inplace=True),
                nn.Conv2d(oc, oc, 3, padding=1), nn.BatchNorm2d(oc), nn.ReLU(inplace=True),
            )

        def forward(self, x):
            return self.net(x)

    class TinyUNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.enc1 = ConvBlock(in_ch, base)
            self.pool1 = nn.MaxPool2d(2)
            self.enc2 = ConvBlock(base, base * 2)
            self.pool2 = nn.MaxPool2d(2)
            self.enc3 = ConvBlock(base * 2, base * 4)
            self.up2 = nn.ConvTranspose2d(base * 4, base * 2, 2, stride=2)
            self.dec2 = ConvBlock(base * 4, base * 2)
            self.up1 = nn.ConvTranspose2d(base * 2, base, 2, stride=2)
            self.dec1 = ConvBlock(base * 2, base)
            self.head = nn.Conv2d(base, n_classes, 1)

        def forward(self, x):
            e1 = self.enc1(x)
            e2 = self.enc2(self.pool1(e1))
            e3 = self.enc3(self.pool2(e2))
            d2 = self.up2(e3)
            d2 = self.dec2(torch.cat([d2, e2], dim=1))
            d1 = self.up1(d2)
            d1 = self.dec1(torch.cat([d1, e1], dim=1))
            return self.head(d1)

    return TinyUNet()


def load_ezm_unet(checkpoint_path: str, device: str = "cpu"):
    """Load the EZM U-Net checkpoint. Returns the model in eval mode."""
    import torch
    model = _build_tiny_unet(in_ch=1, n_classes=3, base=16).to(device)
    state = torch.load(checkpoint_path, map_location=device, weights_only=False)
    if isinstance(state, dict) and "model" in state:
        state = state["model"]
    model.load_state_dict(state)
    model.eval()
    return model


# ---------------------------------------------------------------------------
# Frame I/O
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LetterboxMeta:
    """Records the letterbox transform applied to map src image -> 256x256 model input."""
    src_h: int
    src_w: int
    pad_top: int
    pad_left: int
    pad_size: int  # max(src_h, src_w) after letterboxing
    out_size: int = 256


def _resize_keep_aspect(img: np.ndarray, size: int) -> Tuple[np.ndarray, LetterboxMeta]:
    """Pad to square (keeping aspect), then resize to (size, size). Returns (img, meta)."""
    import cv2
    h, w = img.shape[:2]
    if h == w:
        out = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
        return out, LetterboxMeta(src_h=h, src_w=w, pad_top=0, pad_left=0,
                                   pad_size=h, out_size=size)
    s = max(h, w)
    pad_y = (s - h) // 2
    pad_x = (s - w) // 2
    padded = cv2.copyMakeBorder(img, pad_y, s - h - pad_y, pad_x, s - w - pad_x,
                                 cv2.BORDER_CONSTANT, value=0)
    out = cv2.resize(padded, (size, size), interpolation=cv2.INTER_AREA)
    return out, LetterboxMeta(src_h=h, src_w=w, pad_top=pad_y, pad_left=pad_x,
                               pad_size=s, out_size=size)


def model_xy_to_orig(x_m: float, y_m: float, meta: LetterboxMeta) -> Tuple[float, float]:
    """Invert letterbox+resize to map 256x256 coords back to original image coords."""
    scale = meta.pad_size / meta.out_size
    x_pad = x_m * scale
    y_pad = y_m * scale
    return x_pad - meta.pad_left, y_pad - meta.pad_top


def sample_video_frame(video_path: str, frame_idx: int) -> Optional[np.ndarray]:
    """Read one frame from video as grayscale uint8 (H, W). Returns None on failure."""
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n <= 0:
        cap.release()
        return None
    fi = max(0, min(int(frame_idx), n - 1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return None
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def infer_ezm_mask(model, gray_frame: np.ndarray, *, img_size: int = 256
                    ) -> Tuple[np.ndarray, LetterboxMeta]:
    """Run UNet, return (mask_256, letterbox_meta).

    mask_256 is uint8 with values {0=bg, 1=open, 2=closed} at img_size×img_size.
    """
    import torch
    resized, meta = _resize_keep_aspect(gray_frame, img_size)
    x = torch.from_numpy(resized.astype(np.float32) / 255.0).unsqueeze(0).unsqueeze(0)
    device = next(model.parameters()).device
    x = x.to(device)
    with torch.no_grad():
        logits = model(x)
        pred = logits.argmax(dim=1).squeeze(0).cpu().numpy().astype(np.uint8)
    return pred, meta


# ---------------------------------------------------------------------------
# Postprocessing: mask -> 4 wedge points
# ---------------------------------------------------------------------------


def _largest_cc_keep(binary: np.ndarray) -> np.ndarray:
    import cv2
    n, lab, stats, _ = cv2.connectedComponentsWithStats(binary.astype(np.uint8))
    if n < 2:
        return binary
    # stats[0] is background — pick largest of the rest
    sizes = stats[1:, cv2.CC_STAT_AREA]
    keep_id = 1 + int(np.argmax(sizes))
    return (lab == keep_id).astype(np.uint8)


def _fit_outer_ellipse(track_binary: np.ndarray):
    """Fit ellipse to the largest contour of a binary track mask.

    Returns ((cx, cy), (major_d, minor_d), angle_deg) or None.
    """
    import cv2
    track = _largest_cc_keep(track_binary)
    contours, _ = cv2.findContours(track, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if len(contour) < 5:
        return None
    return cv2.fitEllipse(contour)


def _polar_in_ellipse(xs: np.ndarray, ys: np.ndarray,
                       cx: float, cy: float, ax: float, ay: float, ang_deg: float):
    """Convert pixel coords to (r, theta) where ellipse becomes a unit circle.

    Returns (r, theta) with theta in [0, 2π).
    """
    a = ax / 2.0
    b = ay / 2.0
    ang_rad = math.radians(ang_deg)
    cosA, sinA = math.cos(-ang_rad), math.sin(-ang_rad)
    dx = xs - cx
    dy = ys - cy
    # Rotate into ellipse-aligned frame (de-rotate)
    x_loc = dx * cosA - dy * sinA
    y_loc = dx * sinA + dy * cosA
    # Normalize by axes
    xn = x_loc / max(a, 1e-6)
    yn = y_loc / max(b, 1e-6)
    r = np.sqrt(xn * xn + yn * yn)
    theta = np.arctan2(yn, xn) % (2 * math.pi)
    return r, theta


def _point_on_outer_ellipse_at_theta(theta: float, cx: float, cy: float,
                                      ax: float, ay: float, ang_deg: float) -> Tuple[float, float]:
    """Inverse of _polar_in_ellipse: at unit-circle angle theta, project onto outer ellipse."""
    a = ax / 2.0
    b = ay / 2.0
    x_loc = a * math.cos(theta)
    y_loc = b * math.sin(theta)
    ang_rad = math.radians(ang_deg)
    cosA, sinA = math.cos(ang_rad), math.sin(ang_rad)
    x = x_loc * cosA - y_loc * sinA + cx
    y = x_loc * sinA + y_loc * cosA + cy
    return x, y


def _circular_mean(angles: np.ndarray) -> float:
    """Mean of angles in [0, 2π) using vectors."""
    s = float(np.sin(angles).mean())
    c = float(np.cos(angles).mean())
    return math.atan2(s, c) % (2 * math.pi)


def _angular_extent(angles: np.ndarray) -> Tuple[float, float, float]:
    """Find min, max, and centroid angle of a set of angles, handling wrap-around.

    Returns (theta_min, theta_max, theta_center). theta_min..theta_max defines the
    angular extent of the cluster (the SHORTER arc that contains all points).
    """
    if len(angles) == 0:
        return 0.0, 0.0, 0.0
    center = _circular_mean(angles)
    # Angular displacement relative to center, wrapped to (-π, π]
    rel = ((angles - center + math.pi) % (2 * math.pi)) - math.pi
    rmin = float(rel.min())
    rmax = float(rel.max())
    theta_min = (center + rmin) % (2 * math.pi)
    theta_max = (center + rmax) % (2 * math.pi)
    return theta_min, theta_max, center


def ezm_mask_to_wedge_points(mask_256: np.ndarray, letterbox_meta: LetterboxMeta,
                              *, min_open_area_px: int = 20
                              ) -> Optional[dict]:
    """Convert a 256×256 EZM UNet mask to 4 wedge points in original image coords.

    mask_256: uint8 with values {0=bg, 1=open, 2=closed}.
    Returns:
        dict with keys:
            points: List[List[float]] of 4 (x, y) in ORIGINAL image coords —
                    [wedge1_left, wedge1_right, wedge2_left, wedge2_right]
            ellipse_orig: (cx, cy, major_d, minor_d, angle_deg) in ORIGINAL coords
            quality: dict with diagnostics
        or None if extraction fails.
    """
    import cv2
    track = ((mask_256 == 1) | (mask_256 == 2)).astype(np.uint8)
    track = _largest_cc_keep(track)
    if track.sum() == 0:
        return None
    ellipse_256 = _fit_outer_ellipse(track)
    if ellipse_256 is None:
        return None
    (cx256, cy256), (ax256, ay256), ang_deg = ellipse_256

    # Find open sectors as the 2 largest connected components of (mask==1) within the track.
    open_in_track = ((mask_256 == 1) & (track == 1)).astype(np.uint8)
    n_open, lab_open, stats_open, _ = cv2.connectedComponentsWithStats(open_in_track)
    if n_open < 3:
        return None
    sizes = stats_open[1:, cv2.CC_STAT_AREA]
    if (sizes >= min_open_area_px).sum() < 2:
        return None
    top2 = (1 + np.argsort(sizes)[-2:]).tolist()  # 1-indexed component labels

    # For each open sector, find angular endpoints
    wedge_pts_256 = []  # in 256x256 coords
    sector_diag = []
    for k in top2:
        ys, xs = np.where(lab_open == k)
        # Convert to polar coords w.r.t. fitted ellipse
        r, theta = _polar_in_ellipse(xs.astype(float), ys.astype(float),
                                       cx256, cy256, ax256, ay256, ang_deg)
        # Restrict to track radii (avoid boundary noise)
        m = (r > 0.4) & (r < 1.05)
        if m.sum() < 5:
            theta_use = theta
        else:
            theta_use = theta[m]
        t_min, t_max, t_ctr = _angular_extent(theta_use)
        # Project onto outer ellipse at the angular endpoints
        for t in (t_min, t_max):
            x, y = _point_on_outer_ellipse_at_theta(t, cx256, cy256, ax256, ay256, ang_deg)
            wedge_pts_256.append((x, y, t))  # keep theta for sorting
        sector_diag.append({"label": int(k),
                             "n_pixels": int(stats_open[k, cv2.CC_STAT_AREA]),
                             "theta_center": float(t_ctr),
                             "theta_extent_rad": float(((t_max - t_min) % (2 * math.pi)))})

    if len(wedge_pts_256) != 4:
        return None

    # Sort the 4 points by sector centroid angle so they land in the
    # marking pane's expected order (wedge1 then wedge2).
    # `sector_diag` matches top2 order, which matches groups [0,1] and [2,3] in wedge_pts_256.
    # If sector_diag[0].theta_center > sector_diag[1].theta_center, swap groups so the
    # wedge with the smaller centroid is wedge1.
    if sector_diag[0]["theta_center"] > sector_diag[1]["theta_center"]:
        wedge_pts_256 = wedge_pts_256[2:] + wedge_pts_256[:2]
        sector_diag = [sector_diag[1], sector_diag[0]]

    # Within each pair, order by ascending theta (left-edge then right-edge).
    pairs = [wedge_pts_256[0:2], wedge_pts_256[2:4]]
    ordered_256 = []
    for pair in pairs:
        a, b = pair
        if a[2] > b[2]:
            a, b = b, a
        ordered_256.extend([a, b])

    # Convert 256x256 coords to original image coords
    orig_pts = []
    for x, y, _ in ordered_256:
        x0, y0 = model_xy_to_orig(float(x), float(y), letterbox_meta)
        orig_pts.append([float(x0), float(y0)])

    # Convert ellipse to original coords too (for QC overlay)
    cx_orig, cy_orig = model_xy_to_orig(cx256, cy256, letterbox_meta)
    scale = letterbox_meta.pad_size / letterbox_meta.out_size
    ellipse_orig = {
        "center_xy": [float(cx_orig), float(cy_orig)],
        "axes_xy": [float(ax256 * scale), float(ay256 * scale)],
        "angle_deg": float(ang_deg),
    }

    # Quality diagnostics
    open_frac = float((mask_256 == 1).mean())
    closed_frac = float((mask_256 == 2).mean())
    track_frac = float((track == 1).mean())
    quality = {
        "open_pixel_fraction": open_frac,
        "closed_pixel_fraction": closed_frac,
        "track_pixel_fraction": track_frac,
        "n_open_components": int(n_open - 1),
        "sector_diagnostics": sector_diag,
    }

    return {
        "points": orig_pts,
        "ellipse_orig": ellipse_orig,
        "quality": quality,
    }


def model_version_string(checkpoint_path: str) -> str:
    """Compute a stable model version tag including a sha256 prefix of the checkpoint."""
    import hashlib
    p = Path(checkpoint_path)
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"{p.parent.parent.name}@{p.parent.name}@sha256:{h.hexdigest()[:16]}"
