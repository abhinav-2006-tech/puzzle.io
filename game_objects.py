import pygame
import random
import math


class Particle:
    def __init__(self, x, y, color, size, vel):
        self.x, self.y = x, y
        self.color = color
        self.size = size
        self.vx, self.vy = vel
        self.life = 1.0

    def update(self, dt):
        self.x += self.vx * dt * 60.0
        self.y += self.vy * dt * 60.0
        self.life -= 1.5 * dt

    def draw(self, surface):
        if self.life <= 0: return
        radius = max(1, int(self.size * self.life))
        alpha = int(255 * self.life)
        s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        c = (*self.color[:3], alpha)
        pygame.draw.circle(s, c, (radius, radius), radius)
        surface.blit(s, (self.x - radius, self.y - radius))

class ParticleSystem:
    def __init__(self):
        self.particles = []

    def emit_trail(self, x, y, color=(0, 240, 255)):
        for _ in range(2):
            vx, vy = random.uniform(-1.5, 1.5), random.uniform(-1.5, 1.5)
            self.particles.append(Particle(x, y, color, random.uniform(4, 8), (vx, vy)))

    def emit_confetti(self, cx, cy):
        colors = [(255, 50, 50), (50, 255, 100), (50, 150, 255), (255, 220, 50), (255, 100, 255)]
        for _ in range(120):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(3, 12)
            self.particles.append(Particle(cx, cy, random.choice(colors), random.uniform(6, 12), (math.cos(angle)*speed, math.sin(angle)*speed)))

    def emit_burst(self, x, y, color=(0, 240, 255), count=20):
        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(2, 8)
            self.particles.append(Particle(x, y, color, random.uniform(4, 9), (math.cos(angle)*speed, math.sin(angle)*speed)))

    def update_and_draw(self, surface, dt):
        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles:
            p.update(dt)
            p.draw(surface)

class FloatingText:
    def __init__(self, x, y, text, color, font):
        self.x, self.y, self.text, self.color, self.font = x, y, text, color, font
        self.life = 1.0

    def update(self, dt):
        self.y -= 40 * dt
        self.life -= 0.9 * dt

    def draw(self, surface):
        if self.life <= 0: return
        txt_surf = self.font.render(self.text, True, self.color)
        txt_surf.set_alpha(max(0, int(255 * self.life)))
        surface.blit(txt_surf, (self.x, self.y))

class PuzzleTile:
    def __init__(self, tile_id, surface, correct_pos):
        self.id, self.surface = tile_id, surface
        self.correct_pos, self.current_pos = list(correct_pos), list(correct_pos)
        self.rect = pygame.Rect(0, 0, surface.get_width(), surface.get_height())
        self.target_rect = self.rect.copy()
        self.is_held = False

class PuzzleBoard:
    def __init__(self, image, grid_size, board_rect, audio_mgr):
        self.grid_size, self.board_rect, self.audio = grid_size, board_rect, audio_mgr
        self.tile_w, self.tile_h = board_rect.width // grid_size, board_rect.height // grid_size
        self.tiles, self.held_tile, self.moves, self.show_hints = [], None, 0, False
        self.raw_image, self.combo, self.max_combo, self.last_move_correct = image, 0, 0, False
        self._generate_tiles(image)
        self._shuffle_tiles()

    def _generate_tiles(self, raw_img):
        scaled_img = pygame.transform.smoothscale(raw_img, (self.board_rect.width, self.board_rect.height))
        for row in range(self.grid_size):
            for col in range(self.grid_size):
                sub = scaled_img.subsurface(pygame.Rect(col*self.tile_w, row*self.tile_h, self.tile_w, self.tile_h)).copy()
                tile = PuzzleTile(row * self.grid_size + col, sub, (col, row))
                tile.rect.topleft = (self.board_rect.x + col*self.tile_w, self.board_rect.y + row*self.tile_h)
                tile.target_rect.topleft = tile.rect.topleft
                self.tiles.append(tile)

    def _shuffle_tiles(self):
        grid = {tuple(t.current_pos): t for t in self.tiles}
        positions = list(grid.keys())
        for _ in range(self.grid_size**2 * 15):
            p1, p2 = random.sample(positions, 2)
            grid[p1], grid[p2] = grid[p2], grid[p1]
            grid[p1].current_pos, grid[p2].current_pos = list(p1), list(p2)
        for t in self.tiles:
            t.rect.topleft = (self.board_rect.x + t.current_pos[0]*self.tile_w, self.board_rect.y + t.current_pos[1]*self.tile_h)
            t.target_rect.topleft = t.rect.topleft

    def pickup_tile_at(self, pos):
        for tile in reversed(self.tiles):
            if tile.rect.collidepoint(pos):
                self.held_tile = tile
                tile.is_held = True
                self.drag_offset = (tile.rect.x - pos[0], tile.rect.y - pos[1])
                self.tiles.remove(tile)
                self.tiles.append(tile)
                self.audio.play_pickup()
                return True
        return False

    def drag_tile(self, pos):
        if self.held_tile:
            self.held_tile.rect.x = pos[0] + self.drag_offset[0]
            self.held_tile.rect.y = pos[1] + self.drag_offset[1]

    def release_tile(self):
        if not self.held_tile: return
        tile = self.held_tile
        tile.is_held = False
        self.held_tile = None
        self.moves += 1
        self.audio.play_drop()
        gx = max(0, min(self.grid_size - 1, round((tile.rect.x - self.board_rect.x) / self.tile_w)))
        gy = max(0, min(self.grid_size - 1, round((tile.rect.y - self.board_rect.y) / self.tile_h)))
        
        was_corr = tile.current_pos == tile.correct_pos
        occ = next((t for t in self.tiles if t != tile and t.current_pos == [gx, gy]), None)
        occ_was_corr = occ.current_pos == occ.correct_pos if occ else False
        if occ:
            occ.current_pos = list(tile.current_pos)
            occ.target_rect.topleft = (self.board_rect.x + occ.current_pos[0]*self.tile_w, self.board_rect.y + occ.current_pos[1]*self.tile_h)
        tile.current_pos = [gx, gy]
        tile.target_rect.topleft = (self.board_rect.x + gx*self.tile_w, self.board_rect.y + gy*self.tile_h)
        
        newly_corr = (tile.current_pos == tile.correct_pos and not was_corr) or \
                     (occ and occ.current_pos == occ.correct_pos and not occ_was_corr)
        if newly_corr:
            self.combo += 1
            self.max_combo = max(self.max_combo, self.combo)
        else: self.combo = 0
        self.last_move_correct = newly_corr

    def update(self, dt):
        for t in self.tiles:
            if not t.is_held:
                t.rect.x += int((t.target_rect.x - t.rect.x) * 14.0 * dt)
                t.rect.y += int((t.target_rect.y - t.rect.y) * 14.0 * dt)

    def is_solved(self): return all(t.current_pos == t.correct_pos for t in self.tiles)

class Button:
    def __init__(self, rect, text, font, color=(0, 240, 255)):
        self.rect, self.text, self.font, self.color, self.is_hovered = rect, text, font, color, False

    def check_hover(self, pos):
        self.is_hovered = self.rect.collidepoint(pos)
        return self.is_hovered

    def draw(self, surface):
        col = (255, 0, 128) if self.is_hovered else self.color
        s = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
        pygame.draw.rect(s, (30, 35, 55, 140 if self.is_hovered else 60), s.get_rect(), border_radius=8)
        pygame.draw.rect(s, col, s.get_rect(), width=2, border_radius=8)
        surface.blit(s, self.rect.topleft)
        txt = self.font.render(self.text, True, (240, 240, 245))
        surface.blit(txt, txt.get_rect(center=self.rect.center))