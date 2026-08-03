import sys
import time
import math
import json
import os
import cv2
import numpy as np
import pygame
import mediapipe as mp

from camera import CameraStream, HandTracker
from game_objects import ParticleSystem, PuzzleBoard, Button, FloatingText
from utils import SoundManager, compute_score, compute_stars

SCREEN_WIDTH, SCREEN_HEIGHT = 1280, 720
FPS = 60
DARK_BG = (15, 18, 28)
GLASS_PANEL = (30, 35, 55, 200)
NEON_CYAN = (0, 240, 255)
NEON_PINK = (255, 0, 128)
TEXT_WHITE = (240, 240, 245)

class GesturePuzzleApp:
    def __init__(self):
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Neon Gesture Jigsaw Pro")
        self.clock = pygame.time.Clock()

        # Modules
        self.camera = CameraStream(0, SCREEN_WIDTH, SCREEN_HEIGHT)
        self.tracker = HandTracker()
        self.particles = ParticleSystem()
        self.audio = SoundManager()

        # State
        self.state = "CAMERA_CAPTURE"
        self.grid_size = 3
        self.countdown_start = 0
        self.captured_frame = None
        self.puzzle = None
        self.was_pinched = False
        self.was_pinched_button = False
        self._is_dragging_tile = False
        self.pinch_hold_start = None
        self.start_time = 0
        self.elapsed_time = 0
        self.pause_start = 0
        self.total_paused_time = 0

        # Combo & score presentation state
        self.floating_texts = []
        self.final_score = 0
        self.beat_high_score = False
        self.victory_reveal_start = None
        self.VICTORY_REVEAL_DELAY = 1.0

        # Persistence
        self.scores_file = "high_scores.json"
        self.high_scores = self._load_high_scores()

        # Fonts
        self.font_title = pygame.font.SysFont("Segoe UI", 42, bold=True)
        self.font_modal = pygame.font.SysFont("Segoe UI", 32, bold=True)
        self.font_ui = pygame.font.SysFont("Segoe UI", 18, bold=True)
        self.font_sm = pygame.font.SysFont("Segoe UI", 14)
        self._init_buttons()

    def _init_buttons(self):
        self.btn_grid_3 = Button(pygame.Rect(60, 480, 90, 40), "3x3", self.font_ui)
        self.btn_grid_4 = Button(pygame.Rect(165, 480, 90, 40), "4x4", self.font_ui)
        self.btn_grid_5 = Button(pygame.Rect(270, 480, 90, 40), "5x5", self.font_ui)       
        self.btn_hint = Button(pygame.Rect(60, 535, 140, 40), "Toggle Hint", self.font_ui)
        self.btn_pause = Button(pygame.Rect(210, 535, 150, 40), "Pause Game", self.font_ui)
        self.btn_retake = Button(pygame.Rect(60, 590, 140, 40), "Retake Photo", self.font_ui)
        self.btn_restart = Button(pygame.Rect(210, 590, 150, 40), "Restart", self.font_ui)       
        self.btn_close = Button(pygame.Rect(SCREEN_WIDTH // 2 - 80, SCREEN_HEIGHT // 2 + 50, 160, 45), "CLOSE", self.font_ui, color=NEON_PINK)

    def _load_high_scores(self):
        if os.path.exists(self.scores_file):
            try:
                with open(self.scores_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"3": {"moves": 999, "time": 9999}, "4": {"moves": 999, "time": 9999}, "5": {"moves": 999, "time": 9999}}

    def _save_high_score(self, grid_size: int, moves: int, time_sec: int, score: int = 0):
        key = str(grid_size)
        curr = self.high_scores.get(key, {"moves": 999, "time": 9999})
        if moves < curr["moves"] or (moves == curr["moves"] and time_sec < curr["time"]):
            self.high_scores[key] = {"moves": moves, "time": time_sec}
            try:
                with open(self.scores_file, 'w') as f:
                    json.dump(self.high_scores, f)
            except Exception as e:
                print(f"Failed to save scores: {e}")

        if score > curr.get("score", 0):
            self.high_scores[key]["score"] = score
            try:
                with open(self.scores_file, 'w') as f:
                    json.dump(self.high_scores, f)
            except Exception as e:
                print(f"Failed to save scores: {e}")

    def _draw_overlay_text(self, text: str, pos: tuple, size: int = 24, color: tuple = TEXT_WHITE):
        font = pygame.font.SysFont("Segoe UI", size, bold=True)
        txt_surf = font.render(text, True, color)
        txt_rect = txt_surf.get_rect(center=pos)
        bg_rect = txt_rect.inflate(20, 10)
        s = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(s, (15, 18, 28, 200), s.get_rect(), border_radius=8)
        self.screen.blit(s, bg_rect.topleft)
        self.screen.blit(txt_surf, txt_rect)

    def run(self):
        running = True
        board_rect = pygame.Rect(480, 80, 560, 560)

        while running:
            dt = self.clock.tick(FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE and self.state == "CAMERA_CAPTURE":
                        ret, frame = self.camera.read()
                        if ret and frame is not None:
                            self.captured_frame = frame.copy()
                            self.state = "COUNTDOWN"
                            self.countdown_start = time.time()
                            self.audio.play_click()

            ret, frame = self.camera.read()
            if ret and frame is not None:
                self.tracker.process_frame(frame, SCREEN_WIDTH, SCREEN_HEIGHT)

            tracker_pos, tracker_pinched, hand_detected, landmarks = self.tracker.get_state()

            if hand_detected:
                cursor_pos = tracker_pos
                is_pinched = tracker_pinched
            else:
                cursor_pos = pygame.mouse.get_pos()
                is_pinched = pygame.mouse.get_pressed()[0]

            self.screen.fill(DARK_BG)

            # CAMERA CAPTURE STATE
            if self.state == "CAMERA_CAPTURE":
                if frame is not None:
                    self._draw_camera_preview(frame, landmarks)   
                else:
                    self._draw_overlay_text("Initializing Camera...", (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2), size=32, color=NEON_CYAN)

                if is_pinched and frame is not None:
                    if self.pinch_hold_start is None:
                        self.pinch_hold_start = time.time()                
                    hold_duration = time.time() - self.pinch_hold_start
                    progress = min(1.0, hold_duration / 1.0)                   
                    
                    pygame.draw.circle(self.screen, NEON_PINK, cursor_pos, 30, width=4)
                    pygame.draw.arc(self.screen, NEON_CYAN, 
                                     (cursor_pos[0]-30, cursor_pos[1]-30, 60, 60), 
                                     0, progress * math.pi * 2, width=6)

                    if progress >= 1.0:
                        self.captured_frame = frame.copy()
                        self.state = "COUNTDOWN"
                        self.countdown_start = time.time()
                        self.audio.play_click()
                        self.pinch_hold_start = None
                else:
                    self.pinch_hold_start = None
                    if frame is not None:
                        self._draw_overlay_text("Pinch & HOLD for 1s (or press SPACE) to Take Photo", (SCREEN_WIDTH // 2, 650))

            # COUNTDOWN STATE
            elif self.state == "COUNTDOWN":
                display_frame = self.captured_frame if self.captured_frame is not None else frame
                if display_frame is not None:
                    self._draw_camera_preview(display_frame, [])
                elapsed = time.time() - self.countdown_start
                remaining = 3 - int(elapsed)
                if remaining > 0:
                    self._draw_overlay_text(str(remaining), (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2), size=120, color=NEON_CYAN)
                else:
                    rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                    pygame_img = pygame.image.frombuffer(rgb_frame.tobytes(), rgb_frame.shape[1::-1], "RGB")
                    min_dim = min(pygame_img.get_width(), pygame_img.get_height())
                    crop_rect = pygame.Rect(
                        (pygame_img.get_width() - min_dim) // 2,
                        (pygame_img.get_height() - min_dim) // 2,
                        min_dim, min_dim
                    )
                    cropped = pygame_img.subsurface(crop_rect).copy()
                    self.puzzle = PuzzleBoard(cropped, grid_size=self.grid_size, board_rect=board_rect, audio_mgr=self.audio)
                    self.start_time = time.time()
                    self.total_paused_time = 0
                    self.state = "PLAYING"

            # GAMEPLAY STATES
            elif self.state in ["PLAYING", "PAUSED", "VICTORY"]:
                if self.state == "PLAYING":
                    self.elapsed_time = int(time.time() - self.start_time - self.total_paused_time)
                    self._handle_puzzle_gestures(cursor_pos, is_pinched)
                    self.puzzle.update(dt)
                    if self.puzzle.is_solved():
                        self.state = "VICTORY"
                        self.audio.play_victory()
                        self.particles.emit_confetti(board_rect.centerx, board_rect.centery)
                        self.final_score = compute_score(self.puzzle.moves, self.elapsed_time,
                                                           self.puzzle.max_combo, self.grid_size)
                        prev_best_score = self.high_scores.get(str(self.grid_size), {}).get("score", 0)
                        self.beat_high_score = self.final_score > prev_best_score
                        self._save_high_score(self.grid_size, self.puzzle.moves, self.elapsed_time, self.final_score)
                        self.victory_reveal_start = time.time()

                if self.state == "VICTORY":
                    self.puzzle.update(dt)

                self._draw_glass_panel(pygame.Rect(450, 50, 620, 620))
                self._draw_puzzle()
                self._draw_hud(cursor_pos, is_pinched)

                if self.state == "PAUSED":
                    self._draw_overlay_text("PAUSED", (board_rect.centerx, board_rect.centery), size=80, color=NEON_CYAN)
                elif self.state == "VICTORY":
                    reveal_elapsed = time.time() - self.victory_reveal_start if self.victory_reveal_start else 999
                    if reveal_elapsed >= self.VICTORY_REVEAL_DELAY:
                        if self._draw_victory_modal(cursor_pos, is_pinched):
                            running = False

            # Particles & Floating Text
            self.particles.emit_trail(cursor_pos[0], cursor_pos[1], NEON_PINK if is_pinched else NEON_CYAN)
            self.particles.update_and_draw(self.screen, dt)

            self.floating_texts = [t for t in self.floating_texts if t.life > 0]
            for t in self.floating_texts:
                t.update(dt)
                t.draw(self.screen)

            self._draw_cursor(cursor_pos, is_pinched, hand_detected)
            pygame.display.flip()

        self.camera.release()
        pygame.quit()
        sys.exit()

    def _handle_puzzle_gestures(self, cursor_pos: tuple, is_pinched: bool):
        if self.puzzle is None or self.state != "PLAYING":
            return

        if is_pinched:
            if not self.was_pinched and not self._is_dragging_tile:
                if cursor_pos[0] >= 440:
                    if self.puzzle.pickup_tile_at(cursor_pos):
                        self._is_dragging_tile = True
            elif self._is_dragging_tile:
                self.puzzle.drag_tile(cursor_pos)
        else:
            if self._is_dragging_tile or self.was_pinched:
                self.puzzle.release_tile()
                self._is_dragging_tile = False
                self._handle_move_feedback(cursor_pos)

        self.was_pinched = is_pinched

    def _handle_move_feedback(self, pos: tuple):
        if self.puzzle is None or not self.puzzle.last_move_correct:
            return
        self.audio.play_correct()
        combo = self.puzzle.combo
        color = (255, 220, 50) if combo >= 3 else (0, 255, 180)
        self.particles.emit_burst(pos[0], pos[1], color, count=14 + combo * 4)
        label = f"COMBO x{combo}!" if combo > 1 else "NICE!"
        self.floating_texts.append(FloatingText(pos[0] - 30, pos[1] - 20, label, color, self.font_ui))

    def _draw_camera_preview(self, frame_bgr: np.ndarray, landmarks: list):
        if frame_bgr is None or frame_bgr.size == 0:
            return
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb = np.ascontiguousarray(rgb)
        h, w, _ = rgb.shape
        surf = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
        surf = pygame.transform.smoothscale(surf, (SCREEN_WIDTH, SCREEN_HEIGHT))
        self.screen.blit(surf, (0, 0))

        if landmarks:
            connections = mp.solutions.hands.HAND_CONNECTIONS
            for conn in connections:
                pt1, pt2 = landmarks[conn[0]], landmarks[conn[1]]
                pygame.draw.line(self.screen, (0, 255, 180), pt1, pt2, 2)
            for pt in landmarks:
                pygame.draw.circle(self.screen, NEON_PINK, pt, 4)

    def _draw_glass_panel(self, rect: pygame.Rect):
        panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(panel, GLASS_PANEL, panel.get_rect(), border_radius=16)
        pygame.draw.rect(panel, (255, 255, 255, 30), panel.get_rect(), width=2, border_radius=16)
        self.screen.blit(panel, rect.topleft)

    def _draw_puzzle(self):
        for tile in self.puzzle.tiles:
            self.screen.blit(tile.surface, tile.rect.topleft)
            color = NEON_PINK if tile.is_held else (255, 255, 255, 60)
            width = 3 if tile.is_held else 1
            pygame.draw.rect(self.screen, color, tile.rect, width=width)
            if self.puzzle.show_hints:
                idx_str = str(tile.id + 1)
                num_surf = self.font_ui.render(idx_str, True, (255, 255, 0))
                bg_rect = num_surf.get_rect(topleft=(tile.rect.x + 5, tile.rect.y + 5))
                pygame.draw.rect(self.screen, (0, 0, 0, 180), bg_rect.inflate(6, 4))
                self.screen.blit(num_surf, bg_rect)

    def _draw_hud(self, cursor_pos: tuple, is_pinched: bool):
        self._draw_glass_panel(pygame.Rect(40, 50, 380, 620))

        t_text = self.font_title.render("GESTURE", True, NEON_CYAN)
        self.screen.blit(t_text, (60, 70))

        m_text = self.font_ui.render(f"Moves: {self.puzzle.moves}", True, TEXT_WHITE)
        self.screen.blit(m_text, (60, 130))

        timer_str = f"Time: {self.elapsed_time // 60:02d}:{self.elapsed_time % 60:02d}"
        tm_text = self.font_ui.render(timer_str, True, TEXT_WHITE)
        self.screen.blit(tm_text, (60, 160))

        if self.puzzle.combo > 0:
            combo_text = self.font_ui.render(f"Combo: x{self.puzzle.combo}", True, (255, 220, 50))
            self.screen.blit(combo_text, (200, 160))

        best = self.high_scores.get(str(self.grid_size), {"moves": "-", "time": "-"})
        best_str = f"Best ({self.grid_size}x{self.grid_size}): {best['moves']} moves"
        b_text = self.font_sm.render(best_str, True, (0, 255, 180))
        self.screen.blit(b_text, (60, 195))

        preview_surf = pygame.transform.smoothscale(self.puzzle.raw_image, (120, 120))
        self.screen.blit(preview_surf, (60, 225))
        pygame.draw.rect(self.screen, NEON_CYAN, (60, 225, 120, 120), width=2)    

        lbl_surf = self.font_sm.render("Target Image", True, TEXT_WHITE)
        self.screen.blit(lbl_surf, (60, 350))

        diff_lbl = self.font_sm.render("Difficulty Grid Size:", True, TEXT_WHITE)
        self.screen.blit(diff_lbl, (60, 455))

        buttons = [self.btn_grid_3, self.btn_grid_4, self.btn_grid_5, 
                   self.btn_hint, self.btn_pause, self.btn_retake, self.btn_restart]

        for btn in buttons:
            btn.check_hover(cursor_pos)
            btn.draw(self.screen)
            if btn.is_hovered and self.state in ["PLAYING", "PAUSED"]:
                if not is_pinched and self.was_pinched_button:
                    self._handle_button_click(btn)

        if self.state in ["PLAYING", "PAUSED"]:
            self.was_pinched_button = is_pinched

    def _handle_button_click(self, btn: Button):
        self.audio.play_click()
        if btn == self.btn_grid_3 and self.grid_size != 3:
            self.grid_size = 3
            self.puzzle = PuzzleBoard(self.puzzle.raw_image, 3, self.puzzle.board_rect, self.audio)
        elif btn == self.btn_grid_4 and self.grid_size != 4:
            self.grid_size = 4
            self.puzzle = PuzzleBoard(self.puzzle.raw_image, 4, self.puzzle.board_rect, self.audio)
        elif btn == self.btn_grid_5 and self.grid_size != 5:
            self.grid_size = 5
            self.puzzle = PuzzleBoard(self.puzzle.raw_image, 5, self.puzzle.board_rect, self.audio)
        elif btn == self.btn_hint:
            self.puzzle.show_hints = not self.puzzle.show_hints
        elif btn == self.btn_pause:
            if self.state == "PLAYING":
                self.state = "PAUSED"
                self.pause_start = time.time()
                btn.text = "Resume"
            elif self.state == "PAUSED":
                self.state = "PLAYING"
                self.total_paused_time += (time.time() - self.pause_start)
                btn.text = "Pause Game"
        elif btn == self.btn_retake:
            self.state = "CAMERA_CAPTURE"
            self.captured_frame = None
            self.pinch_hold_start = None
            self.puzzle = None
        elif btn == self.btn_restart:
            self.puzzle = PuzzleBoard(self.puzzle.raw_image, self.grid_size, self.puzzle.board_rect, self.audio)
            self.start_time = time.time()
            self.total_paused_time = 0
            if self.state == "PAUSED":
                self.state = "PLAYING"
                self.btn_pause.text = "Pause Game"

    def _draw_victory_modal(self, cursor_pos: tuple, is_pinched: bool) -> bool:
        rect = pygame.Rect(SCREEN_WIDTH // 2 - 250, SCREEN_HEIGHT // 2 - 150, 500, 300)
        self._draw_glass_panel(rect)

        v_text = self.font_modal.render("PUZZLE FINISHED!", True, NEON_PINK)
        v_rect = v_text.get_rect(center=(rect.centerx, rect.y + 45))
        self.screen.blit(v_text, v_rect)

        s_text = self.font_ui.render(f"Moves: {self.puzzle.moves}   |   Time: {self.elapsed_time}s", True, TEXT_WHITE)
        s_rect = s_text.get_rect(center=(rect.centerx, rect.y + 95))
        self.screen.blit(s_text, s_rect)

        stars = compute_stars(self.puzzle.moves, self.elapsed_time, self.grid_size)
        star_str = "★" * stars + "☆" * (3 - stars)
        star_surf = self.font_modal.render(star_str, True, (255, 220, 50))
        star_rect = star_surf.get_rect(center=(rect.centerx, rect.y + 140))
        self.screen.blit(star_surf, star_rect)

        score_text = self.font_ui.render(
            f"Score: {self.final_score}   |   Best Combo: x{self.puzzle.max_combo}", True, (0, 255, 180)
        )
        score_rect = score_text.get_rect(center=(rect.centerx, rect.y + 175))
        self.screen.blit(score_text, score_rect)

        if self.beat_high_score:
            hs_text = self.font_sm.render("NEW HIGH SCORE!", True, (255, 220, 50))
            hs_rect = hs_text.get_rect(center=(rect.centerx, rect.y + 198))
            self.screen.blit(hs_text, hs_rect)

        self.btn_close.check_hover(cursor_pos)
        self.btn_close.draw(self.screen)

        close_triggered = False
        if self.btn_close.is_hovered:
            if not is_pinched and self.was_pinched_button:
                self.audio.play_click()
                close_triggered = True

        self.was_pinched_button = is_pinched
        return close_triggered

    def _draw_cursor(self, pos: tuple, is_pinched: bool, hand_detected: bool):
        color = NEON_PINK if is_pinched else (NEON_CYAN if hand_detected else (180, 180, 180))
        radius = 12 if is_pinched else 18
        s = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color[:3], 80), (radius * 2, radius * 2), radius * 2)
        pygame.draw.circle(s, color, (radius * 2, radius * 2), radius, width=2)
        pygame.draw.circle(s, (255, 255, 255), (radius * 2, radius * 2), 3)
        self.screen.blit(s, (pos[0] - radius * 2, pos[1] - radius * 2))