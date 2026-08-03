import cv2
import threading
import time
import numpy as np
import mediapipe as mp

class CameraStream:
    """Threaded camera stream to keep Pygame running at 60 FPS without freezing."""
    def __init__(self, src=0, width=1280, height=720):
        # Try DirectShow first on Windows, fallback to default if needed
        self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(src)

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        self.ret = False
        self.frame = None
        self.running = True
        self.lock = threading.Lock()

        # Start background thread for non-blocking camera capture
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        while self.running:
            if not self.cap.isOpened():
                time.sleep(0.05)
                continue
            ret, frame = self.cap.read()
            if ret and frame is not None and frame.size > 0:
                frame = cv2.flip(frame, 1)  # Natural mirror flip
                with self.lock:
                    self.ret = ret
                    self.frame = frame
            time.sleep(0.01)

    def read(self):
        with self.lock:
            if self.ret and self.frame is not None:
                return True, self.frame.copy()
            return False, None

    def release(self):
        self.running = False
        if self.cap.isOpened():
            self.cap.release()

class HandTracker:
    """Mediapipe Hand Tracking with safety locks."""
    def __init__(self, max_hands=1, detection_confidence=0.7, tracking_confidence=0.7):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence
        )
        self.lock = threading.Lock()
        self.smooth_x, self.smooth_y = 640.0, 360.0
        self.alpha = 0.45
        self.is_pinched = False
        self.hand_detected = False
        self.pinch_threshold_low = 42.0
        self.pinch_threshold_high = 60.0
        self.landmarks_px = []

    def process_frame(self, frame_bgr: np.ndarray, screen_w: int, screen_h: int):
        if frame_bgr is None or frame_bgr.size == 0:
            return
        try:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb)
            landmarks_pixel_coords = []
            raw_pinched = self.is_pinched

            if results and results.multi_hand_landmarks:
                landmarks = results.multi_hand_landmarks[0].landmark
                for lm in landmarks:
                    landmarks_pixel_coords.append((int(lm.x * screen_w), int(lm.y * screen_h)))

                idx_px = np.array([landmarks[8].x * screen_w, landmarks[8].y * screen_h])
                thumb_px = np.array([landmarks[4].x * screen_w, landmarks[4].y * screen_h])

                dist = np.linalg.norm(idx_px - thumb_px)

                if not self.is_pinched and dist < self.pinch_threshold_low:
                    raw_pinched = True
                elif self.is_pinched and dist > self.pinch_threshold_high:
                    raw_pinched = False

                with self.lock:
                    self.smooth_x = (1 - self.alpha) * self.smooth_x + self.alpha * idx_px[0]
                    self.smooth_y = (1 - self.alpha) * self.smooth_y + self.alpha * idx_px[1]
                    self.is_pinched = raw_pinched
                    self.hand_detected = True
                    self.landmarks_px = landmarks_pixel_coords
            else:
                with self.lock:
                    self.hand_detected = False
                    self.landmarks_px = []
        except Exception as e:
            print(f"[HandTracker] Warning: {e}")

    def get_state(self):
        with self.lock:
            return (int(self.smooth_x), int(self.smooth_y)), self.is_pinched, self.hand_detected, list(self.landmarks_px)