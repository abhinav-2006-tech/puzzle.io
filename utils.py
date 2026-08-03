import pygame
import numpy as np
import threading
import time

class SoundManager:
    def __init__(self):
        self.enabled = False
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            self.enabled = True
        except: pass

    def _play_tone(self, f1, f2, dur, wave="sine", vol=0.3):
        if not self.enabled: return
        rate = 44100
        samples = int(rate * dur)
        t = np.linspace(0, dur, samples, False)
        freqs = np.linspace(f1, f2, samples)
        audio = np.sin(2 * np.pi * freqs * t) if wave == "sine" else np.sign(np.sin(2 * np.pi * freqs * t))
        env = np.ones(samples)
        env[:int(samples*0.1)] = np.linspace(0, 1, int(samples*0.1))
        env[-int(samples*0.4):] = np.linspace(1, 0, int(samples*0.4))
        sound = pygame.sndarray.make_sound((audio * env * vol * 32767).astype(np.int16))
        sound.play()

    def play_pickup(self): threading.Thread(target=self._play_tone, args=(300, 600, 0.08, "sine", 0.2), daemon=True).start()
    def play_drop(self): threading.Thread(target=self._play_tone, args=(500, 250, 0.10, "sine", 0.25), daemon=True).start()
    def play_click(self): threading.Thread(target=self._play_tone, args=(800, 800, 0.03, "square", 0.1), daemon=True).start()
    def play_correct(self): threading.Thread(target=self._play_tone, args=(700, 1000, 0.09, "sine", 0.25), daemon=True).start()
    def play_victory(self):
        def _f():
            for n in [440, 554.37, 659.25, 880]:
                self._play_tone(n, n, 0.12, "sine", 0.3)
                time.sleep(0.10)
        threading.Thread(target=_f, daemon=True).start()

def compute_score(moves, elapsed, max_combo, grid_size):
    return max(0, 1000 * (grid_size - 1) - (moves * 8 + elapsed * 4) + (max_combo * 25))

def compute_stars(moves, elapsed, grid_size):
    if moves <= grid_size**2 and elapsed <= grid_size**2 * 6: return 3
    return 2 if moves <= grid_size**2 * 2 else 1