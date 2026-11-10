"""Tiny crossword generator: interlocks a handful of words on a grid.

Words come from the AI, but the grid is built here in plain code, because
language models are unreliable at laying out a valid crossword.
"""
import random
import re

MAX_SIZE = 15          # grid never grows past MAX_SIZE x MAX_SIZE
_WORD_RE = re.compile(r"[A-Z]{2,%d}" % MAX_SIZE)
_DIRS = {"A": (0, 1), "D": (1, 0)}   # across moves right, down moves down


def _crossings_if_placed(cells, used, word, r, c, d):
    """Return how many letters the word would share with the grid,
    or None if placing it here would break a crossword rule."""
    dr, dc = _DIRS[d]
    pr, pc = dc, dr  # perpendicular step
    # The squares just before and after the word must be empty.
    if (r - dr, c - dc) in cells or (r + dr * len(word), c + dc * len(word)) in cells:
        return None
    crossings = 0
    for i, ch in enumerate(word):
        pos = (r + dr * i, c + dc * i)
        if pos in cells:
            # Must share the same letter and cross (not overlap) an existing word.
            if cells[pos] != ch or d in used[pos]:
                return None
            crossings += 1
        else:
            # A brand-new letter may not touch a parallel word.
            if (pos[0] - pr, pos[1] - pc) in cells or (pos[0] + pr, pos[1] + pc) in cells:
                return None
    return crossings


def _bbox(cells):
    rows = [p[0] for p in cells]
    cols = [p[1] for p in cells]
    return min(rows), max(rows), min(cols), max(cols)


def _attempt(words, rng):
    cells, used, placed = {}, {}, []

    def put(word, r, c, d):
        dr, dc = _DIRS[d]
        for i, ch in enumerate(word):
            pos = (r + dr * i, c + dc * i)
            cells[pos] = ch
            used.setdefault(pos, set()).add(d)
        placed.append((word, r, c, d))

    first = words[0]
    put(first, 0, 0, "A")
    pending = words[1:]

    progress = True
    while pending and progress:
        progress = False
        for word in list(pending):
            best = None
            for (r0, c0), letter in list(cells.items()):
                for i, ch in enumerate(word):
                    if ch != letter:
                        continue
                    for d, (dr, dc) in _DIRS.items():
                        if d in used[(r0, c0)]:
                            continue
                        r, c = r0 - dr * i, c0 - dc * i
                        n = _crossings_if_placed(cells, used, word, r, c, d)
                        if not n:
                            continue
                        # Keep the grid compact.
                        end = (r + dr * (len(word) - 1), c + dc * (len(word) - 1))
                        probe = dict(cells)
                        probe[(r, c)] = probe[end] = "?"
                        r1, r2, c1, c2 = _bbox(probe)
                        h, w = r2 - r1 + 1, c2 - c1 + 1
                        if h > MAX_SIZE or w > MAX_SIZE:
                            continue
                        score = (n, -(h * w), rng.random())
                        if best is None or score > best[0]:
                            best = (score, r, c, d)
            if best:
                put(word, best[1], best[2], best[3])
                pending.remove(word)
                progress = True
    return cells, placed, pending


def build_crossword(words, seed=None, attempts=40):
    """Return {"grid", "entries", "unplaced"}.

    grid:    list of rows; each cell is an uppercase letter or "" (empty)
    entries: [{"num", "dir" ("A"/"D"), "word", "row", "col"}], numbered like a
             real crossword (left-to-right, top-to-bottom)
    unplaced: words that could not be interlocked
    """
    rng = random.Random(seed)
    clean = []
    for w in words:
        w = str(w).strip().upper()
        if _WORD_RE.fullmatch(w) and w not in clean:
            clean.append(w)
    if not clean:
        return {"grid": [], "entries": [], "unplaced": []}

    best = None
    for _ in range(attempts):
        order = sorted(clean, key=lambda w: (-len(w), rng.random()))
        cells, placed, pending = _attempt(order, rng)
        r1, r2, c1, c2 = _bbox(cells)
        score = (len(placed), -((r2 - r1 + 1) * (c2 - c1 + 1)))
        if best is None or score > best[0]:
            best = (score, cells, placed, pending)
        if not pending and len(clean) <= 2:
            break
    _, cells, placed, pending = best

    r1, r2, c1, c2 = _bbox(cells)
    grid = [[cells.get((r, c), "") for c in range(c1, c2 + 1)] for r in range(r1, r2 + 1)]

    starts = sorted({(r - r1, c - c1) for _, r, c, _ in placed})
    number = {pos: i + 1 for i, pos in enumerate(starts)}
    entries = sorted(
        (
            {"num": number[(r - r1, c - c1)], "dir": d, "word": w, "row": r - r1, "col": c - c1}
            for w, r, c, d in placed
        ),
        key=lambda e: (e["num"], e["dir"]),
    )
    return {"grid": grid, "entries": entries, "unplaced": pending}
