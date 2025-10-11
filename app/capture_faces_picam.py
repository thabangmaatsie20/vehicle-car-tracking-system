#!/usr/bin/env python3
"""
Picamera2 face capture utility for building the authorized dataset.

- Saves images in data/authorized/<name>/
- GUI: SPACE/C to capture if a face is detected, ESC to exit
- Headless: auto-captures every --interval seconds (requires --interval)
- Optional: only save when a face is detected (default True)

This is tailored for the overall project pipeline:
1) Capture your images here
2) Run app/encode_faces.py to generate models/face_encodings.pkl
3) Run app/recognize_faces.py for real-time authorization
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

import cv2
from picamera2 import Picamera2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture face images using Picamera2")
    parser.add_argument("--name", help="Person name (folder under data/authorized)")
    parser.add_argument("--num", type=int, default=10, help="Number of images to capture")
    parser.add_argument("--width", type=int, default=640, help="Camera width")
    parser.add_argument("--height", type=int, default=480, help="Camera height")
    parser.add_argument("--fps", type=int, default=30, help="Camera frame rate")
    parser.add_argument("--mirror", action="store_true", help="Mirror (selfie) view")
    parser.add_argument(
        "--detect-only",
        action="store_true",
        help="Only save when a face is detected (recommended)",
    )
    parser.add_argument(
        "--no-detect",
        action="store_true",
        help="Disable face detection gating (always save on capture)",
    )
    parser.add_argument("--headless", action="store_true", help="Run without GUI window")
    parser.add_argument(
        "--interval",
        type=float,
        default=0.0,
        help="Auto-capture interval in seconds (required for headless)",
    )
    parser.add_argument("--prefix", default="image", help="Saved filename prefix")
    parser.add_argument(
        "--dest",
        default="data/authorized",
        help="Base dataset directory (default: data/authorized)",
    )
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


_face_lib_warned = False


def detect_face_rgb(rgb_image, min_size: int = 60) -> bool:
    """Return True if at least one face is detected.

    Uses face_recognition if available. Falls back to naive size check if not.
    """
    global _face_lib_warned
    try:
        import face_recognition  # local import to avoid hard dependency for capture
    except Exception:
        if not _face_lib_warned:
            print("Warning: face_recognition not available; saving without detection gating.")
            _face_lib_warned = True
        return True  # allow capture without gating

    # Optionally downscale for speed
    scale = 0.5 if max(rgb_image.shape[:2]) > 720 else 1.0
    small = rgb_image
    if scale != 1.0:
        small = cv2.resize(rgb_image, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)

    locations = face_recognition.face_locations(small, model="hog")
    if not locations:
        return False

    # Basic size gating to avoid saving tiny detections
    sh, sw = small.shape[:2]
    for top, right, bottom, left in locations:
        w = right - left
        h = bottom - top
        if max(w, h) >= max(min_size * scale, 1):
            return True
    return False


def main() -> None:
    args = parse_args()

    # Resolve name (CLI preferred, else prompt)
    name = (args.name or "").strip()
    if not name:
        try:
            name = input("Enter your name for the dataset: ").strip()
        except EOFError:
            name = ""
    if not name:
        print("Name cannot be empty!")
        sys.exit(1)

    save_dir = Path(args.dest) / name
    ensure_dir(save_dir)

    # Determine detection gating behavior
    detect_gate = not args.no_detect
    if args.detect_only:
        detect_gate = True

    if args.headless and args.interval <= 0:
        print("Headless mode requires --interval > 0 (e.g., --interval 0.7)")
        sys.exit(2)

    print(f"Capturing images for: {name}")
    print(f"Saving to: {save_dir}")
    print("Press SPACE/C to capture, ESC to exit" + (" (GUI only)" if not args.headless else ""))

    try:
        picam2 = Picamera2()
        config = picam2.create_preview_configuration(
            main={"size": (args.width, args.height), "format": "RGB888"},
            controls={"FrameRate": args.fps},
        )
        picam2.configure(config)
        picam2.start()
        print("Camera started successfully!")

        img_counter = 0
        max_images = max(args.num, 1)
        last_capture_ts = 0.0
        window_name = "Face Capture"

        while img_counter < max_images:
            # Picamera2 returns RGB
            frame_rgb = picam2.capture_array()
            if frame_rgb is None:
                print("Warning: received empty frame")
                continue

            # Convert to BGR for OpenCV display/save
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            if args.mirror:
                frame_bgr = cv2.flip(frame_bgr, 1)
                frame_rgb = cv2.flip(frame_rgb, 1)

            save_allowed = True
            if detect_gate:
                save_allowed = detect_face_rgb(frame_rgb)

            did_save = False
            now = time.time()

            # Auto-capture for headless/interval mode
            if args.interval > 0 and (now - last_capture_ts) >= args.interval and save_allowed:
                img_name = f"{args.prefix}_{img_counter:02d}.jpg"
                out_path = str(save_dir / img_name)
                cv2.imwrite(out_path, frame_bgr)
                print(f"Captured: {out_path}")
                img_counter += 1
                last_capture_ts = now
                did_save = True

            # GUI display and manual capture
            if not args.headless:
                try:
                    cv2.putText(
                        frame_bgr,
                        f"{name}: {img_counter}/{max_images}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 255, 0) if save_allowed else (0, 0, 255),
                        2,
                        cv2.LINE_AA,
                    )
                    cv2.putText(
                        frame_bgr,
                        "SPACE: Capture | ESC: Exit",
                        (10, 65),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )
                    if detect_gate:
                        cv2.putText(
                            frame_bgr,
                            "Face required to save",
                            (10, 95),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (200, 200, 0),
                            2,
                            cv2.LINE_AA,
                        )

                    cv2.imshow(window_name, frame_bgr)
                    key = cv2.waitKey(1) & 0xFF
                    if key == 27:  # ESC
                        break
                    if key in (32, ord("c")) and save_allowed and not did_save:
                        img_name = f"{args.prefix}_{img_counter:02d}.jpg"
                        out_path = str(save_dir / img_name)
                        cv2.imwrite(out_path, frame_bgr)
                        print(f"Captured: {out_path}")
                        img_counter += 1
                        did_save = True
                except cv2.error:
                    print("GUI not available; re-run with --headless and --interval.")
                    break

        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass

        picam2.stop()
        picam2.close()
        print(f"Captured {img_counter} images for {name}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(3)


if __name__ == "__main__":
    main()
