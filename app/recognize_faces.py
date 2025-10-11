#!/usr/bin/env python3
"""
Real-time face recognition script

- Loads known face encodings from models/face_encodings.pkl
- Opens webcam (default) or video file/stream
- Detects faces and compares against known encodings
- Overlays bounding boxes and labels (Authorized/Unknown)
- Provides CLI flags for tuning and input selection
"""

from __future__ import annotations

import argparse
import os
import pickle
import sys
import time
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import face_recognition

ENCODINGS_DEFAULT_PATH = "models/face_encodings.pkl"


@dataclass
class RecognitionConfig:
    encodings_path: str = ENCODINGS_DEFAULT_PATH
    source: str | int = 0  # 0 for default webcam; otherwise path/URL
    tolerance: float = 0.5  # lower is stricter (default 0.6 in face_recognition)
    model: str = "hog"  # "hog" (CPU) or "cnn" (GPU if dlib compiled with CUDA)
    upsample_times: int = 1
    frame_scale: float = 0.25  # downscale to speed up processing (0.25 => 1/4 size)
    display_scale: float = 1.0  # scale for display window
    skip_frames: int = 0  # number of frames to skip between recognitions
    show_fps: bool = True
    # Headless / output & logging options
    headless: bool = False
    output_video: str | None = None
    output_frames_dir: str | None = None
    frame_save_interval: float = 1.0
    max_frames: int = 0  # 0 = unlimited
    debug: bool = False
    log_interval: float = 2.0


@dataclass
class KnownEncodings:
    encodings: List
    names: List[str]


def load_encodings(path: str) -> KnownEncodings:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Encodings file not found at '{path}'. Run app/encode_faces.py first."
        )
    with open(path, "rb") as f:
        data = pickle.load(f)
    encodings = data.get("encodings", [])
    names = data.get("names", [])
    if not encodings or not names or len(encodings) != len(names):
        raise ValueError("Encodings file is empty or malformed.")
    return KnownEncodings(encodings=encodings, names=names)


def open_video_source(source: str | int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video source: {source}")
    return cap


def draw_labelled_box(
    frame,
    top_left: Tuple[int, int],
    bottom_right: Tuple[int, int],
    label: str,
    color: Tuple[int, int, int],
):
    x1, y1 = top_left
    x2, y2 = bottom_right
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    # Label box
    font = cv2.FONT_HERSHEY_SIMPLEX
    label_scale = 0.6
    label_thickness = 2

    (text_w, text_h), baseline = cv2.getTextSize(label, font, label_scale, label_thickness)
    cv2.rectangle(frame, (x1, y2 - text_h - baseline - 8), (x1 + text_w + 8, y2), color, -1)
    cv2.putText(
        frame,
        label,
        (x1 + 4, y2 - 6),
        font,
        label_scale,
        (255, 255, 255),
        label_thickness,
        lineType=cv2.LINE_AA,
    )


def maybe_put_fps(frame, fps: float, show: bool):
    if not show:
        return
    text = f"FPS: {fps:.1f}"
    cv2.putText(
        frame,
        text,
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
        lineType=cv2.LINE_AA,
    )


def recognize_stream(cfg: RecognitionConfig):
    print(f"Loading encodings from: {cfg.encodings_path}")
    known = load_encodings(cfg.encodings_path)
    print(
        f"Loaded {len(known.encodings)} encodings for {len(set(known.names))} identities"
    )

    print(f"Opening video source: {cfg.source}")
    cap = open_video_source(cfg.source)

    # Source metadata (may be 0 for webcams)
    src_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    src_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if src_width and src_height:
        print(f"Source size: {src_width}x{src_height} @ {src_fps or 'unknown'} FPS")

    process_frame_index = 0
    fps_smoother = 0.0
    t_last = time.time()
    last_save_ts = t_last
    last_log_ts = t_last
    frame_count = 0
    gui_error_warned = False
    headless_mode = bool(cfg.headless)
    writer = None

    authorized_color = (0, 200, 0)
    unknown_color = (0, 0, 200)

    # Prepare frame output directory if requested
    if cfg.output_frames_dir:
        os.makedirs(cfg.output_frames_dir, exist_ok=True)

    while True:
        ok, frame = cap.read()
        if not ok:
            print("End of stream or cannot read from source.")
            break
        frame_count += 1

        # Optionally downscale for faster processing
        small_frame = frame
        if cfg.frame_scale and cfg.frame_scale != 1.0:
            small_frame = cv2.resize(
                frame,
                (0, 0),
                fx=cfg.frame_scale,
                fy=cfg.frame_scale,
                interpolation=cv2.INTER_LINEAR,
            )

        rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        # Skip frames if requested for speed
        should_process = (process_frame_index % (cfg.skip_frames + 1)) == 0
        process_frame_index += 1

        names_this_frame: List[str] = []
        locations_this_frame: List[Tuple[int, int, int, int]] = []

        if should_process:
            # Detect faces and compute encodings
            face_locations = face_recognition.face_locations(
                rgb_small, number_of_times_to_upsample=cfg.upsample_times, model=cfg.model
            )
            face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(known.encodings, face_encoding, tolerance=cfg.tolerance)
                name = "Unknown"

                if True in matches:
                    # Use the best match via distance
                    face_distances = face_recognition.face_distance(known.encodings, face_encoding)
                    best_match_index = int(face_distances.argmin()) if hasattr(face_distances, "argmin") else face_distances.tolist().index(min(face_distances))
                    if matches[best_match_index]:
                        name = known.names[best_match_index]

                names_this_frame.append(name)

            locations_this_frame = face_locations

        # Map locations back to original frame size
        scale_back = 1.0 / cfg.frame_scale if cfg.frame_scale else 1.0
        for (top, right, bottom, left), name in zip(locations_this_frame, names_this_frame):
            top = int(top * scale_back)
            right = int(right * scale_back)
            bottom = int(bottom * scale_back)
            left = int(left * scale_back)

            label = f"Authorized: {name}" if name != "Unknown" else "Unauthorized"
            color = authorized_color if name != "Unknown" else unknown_color
            draw_labelled_box(frame, (left, top), (right, bottom), label, color)

        # FPS calculation
        t_now = time.time()
        dt = max(t_now - t_last, 1e-6)
        inst_fps = 1.0 / dt
        t_last = t_now
        # Simple EMA smoother
        fps_smoother = 0.9 * fps_smoother + 0.1 * inst_fps if fps_smoother else inst_fps

        maybe_put_fps(frame, fps_smoother, cfg.show_fps)

        # Initialize video writer lazily when first frame is available
        if cfg.output_video and writer is None:
            out_path = cfg.output_video
            out_dir = os.path.dirname(out_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            h, w = frame.shape[:2]
            fps_out = src_fps if src_fps and src_fps > 0 else 20.0
            fourcc = (
                cv2.VideoWriter_fourcc(*"mp4v")
                if out_path.lower().endswith(".mp4")
                else cv2.VideoWriter_fourcc(*"XVID")
            )
            writer = cv2.VideoWriter(out_path, fourcc, fps_out, (w, h))
            if writer is None or not writer.isOpened():
                print(f"Warning: failed to open video writer at '{out_path}'.")
                writer = None

        if writer is not None:
            writer.write(frame)

        # Optionally save frames periodically
        if cfg.output_frames_dir:
            now_ts = time.time()
            if now_ts - last_save_ts >= max(cfg.frame_save_interval, 0.01):
                ts = time.strftime("%Y%m%d-%H%M%S")
                out_name = f"frame_{ts}_{frame_count:06d}.jpg"
                out_file = os.path.join(cfg.output_frames_dir, out_name)
                cv2.imwrite(out_file, frame)
                last_save_ts = now_ts

        # Periodic logging in debug mode
        if cfg.debug:
            now_ts = time.time()
            if now_ts - last_log_ts >= max(cfg.log_interval, 0.1):
                names_str = ", ".join(n for n in names_this_frame if n != "Unknown") or "none"
                print(
                    f"Frame {frame_count}: faces={len(locations_this_frame)}; known={names_str}; fps={fps_smoother:.1f}"
                )
                last_log_ts = now_ts

        # Optionally scale for display
        display_frame = frame
        if cfg.display_scale and cfg.display_scale != 1.0:
            display_frame = cv2.resize(
                frame,
                (0, 0),
                fx=cfg.display_scale,
                fy=cfg.display_scale,
                interpolation=cv2.INTER_LINEAR,
            )

        if not headless_mode:
            try:
                cv2.imshow("Face Recognition", display_frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):  # ESC or 'q'
                    break
            except cv2.error:
                if not gui_error_warned:
                    print(
                        "GUI not available; continuing in headless mode. Use --headless to hide this message."
                    )
                    gui_error_warned = True
                headless_mode = True

        if cfg.max_frames > 0 and frame_count >= cfg.max_frames:
            break

    cap.release()
    cv2.destroyAllWindows()
    if writer is not None:
        writer.release()


def parse_args(argv: List[str]) -> RecognitionConfig:
    parser = argparse.ArgumentParser(description="Real-time face recognition")

    parser.add_argument(
        "--encodings",
        default=ENCODINGS_DEFAULT_PATH,
        help="Path to pickle file with encodings (default: models/face_encodings.pkl)",
    )
    parser.add_argument(
        "--source",
        default="0",
        help="Video source: webcam index (e.g. 0) or path/URL",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.5,
        help="Recognition tolerance (lower = stricter, default 0.5)",
    )
    parser.add_argument(
        "--model",
        choices=["hog", "cnn"],
        default="hog",
        help='Face detection model: "hog" (CPU) or "cnn" (GPU if available)',
    )
    parser.add_argument(
        "--upsample-times",
        type=int,
        default=1,
        help="Number of times to upsample for detection (default 1)",
    )
    parser.add_argument(
        "--frame-scale",
        type=float,
        default=0.25,
        help="Downscale factor for processing (e.g., 0.25 = quarter size)",
    )
    parser.add_argument(
        "--display-scale",
        type=float,
        default=1.0,
        help="Scale factor for display window (default 1.0)",
    )
    parser.add_argument(
        "--skip-frames",
        type=int,
        default=0,
        help="Skip N frames between recognition passes for speed",
    )
    parser.add_argument(
        "--no-fps",
        action="store_true",
        help="Disable FPS overlay",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without GUI window (use logging/output options)",
    )
    parser.add_argument(
        "--output-video",
        default=None,
        help="Path to save annotated video (e.g., out.mp4)",
    )
    parser.add_argument(
        "--output-frames",
        dest="output_frames_dir",
        default=None,
        help="Directory to periodically save annotated frames as JPGs",
    )
    parser.add_argument(
        "--frame-save-interval",
        type=float,
        default=1.0,
        help="Seconds between saved frames when --output-frames is set",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Process at most N frames (0 = unlimited)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable per-interval logging of detections and FPS",
    )
    parser.add_argument(
        "--log-interval",
        type=float,
        default=2.0,
        help="Seconds between log prints when --debug is enabled",
    )

    args = parser.parse_args(argv)

    # Convert source
    source: str | int
    if args.source.isdigit():
        source = int(args.source)
    else:
        source = args.source

    return RecognitionConfig(
        encodings_path=args.encodings,
        source=source,
        tolerance=args.tolerance,
        model=args.model,
        upsample_times=args.upsample_times,
        frame_scale=args.frame_scale,
        display_scale=args.display_scale,
        skip_frames=args.skip_frames,
        show_fps=not args.no_fps,
        headless=args.headless,
        output_video=args.output_video,
        output_frames_dir=args.output_frames_dir,
        frame_save_interval=args.frame_save_interval,
        max_frames=args.max_frames,
        debug=args.debug,
        log_interval=args.log_interval,
    )


def main(argv: List[str] | None = None):
    cfg = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        recognize_stream(cfg)
    except FileNotFoundError as e:
        print(str(e))
        sys.exit(1)
    except RuntimeError as e:
        print(str(e))
        sys.exit(2)


if __name__ == "__main__":
    main()
