import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from crossword import build_crossword


def grid_problems(cw):
    """Every run of 2+ letters in the grid must be a placed entry, and the grid must be connected."""
    g = cw["grid"]
    H, W = len(g), len(g[0])
    expected = {(e["row"], e["col"], e["dir"], e["word"]) for e in cw["entries"]}
    found = set()
    for r in range(H):
        c = 0
        while c < W:
            if g[r][c]:
                s = c
                while c < W and g[r][c]:
                    c += 1
                if c - s >= 2:
                    found.add((r, s, "A", "".join(g[r][s:c])))
            else:
                c += 1
    for c in range(W):
        r = 0
        while r < H:
            if g[r][c]:
                s = r
                while r < H and g[r][c]:
                    r += 1
                if r - s >= 2:
                    found.add((s, c, "D", "".join(g[i][c] for i in range(s, r))))
            else:
                r += 1
    problems = list(found ^ expected)
    cells = {(r, c) for r in range(H) for c in range(W) if g[r][c]}
    seen, stack = set(), [next(iter(cells))]
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        stack += [(p[0] + a, p[1] + b) for a, b in ((0, 1), (1, 0), (0, -1), (-1, 0)) if (p[0] + a, p[1] + b) in cells]
    if seen != cells:
        problems.append("not connected")
    return problems, H, W


class CrosswordTests(unittest.TestCase):
    def test_real_words_all_placed(self):
        cw = build_crossword(["ARBITRAGE", "FIDUCIARY", "LIQUIDITY", "AMORTIZE", "SOLVENT"], seed=1)
        self.assertEqual(cw["unplaced"], [])
        self.assertEqual(len(cw["entries"]), 5)
        self.assertEqual(grid_problems(cw)[0], [])

    def test_random_sets_are_always_valid(self):
        rng = random.Random(7)
        for t in range(200):
            words = list({"".join(rng.choice("ABCDEEIIOULNRST") for _ in range(rng.randint(4, 12)))
                          for _ in range(rng.choice([3, 4, 5, 6]))})
            cw = build_crossword(words, seed=t)
            problems, h, w = grid_problems(cw)
            self.assertEqual(problems, [], words)
            self.assertLessEqual(max(h, w), 15)
            self.assertEqual({e["word"] for e in cw["entries"]} | set(cw["unplaced"]), set(words))

    def test_numbering_follows_reading_order(self):
        cw = build_crossword(["ARBITRAGE", "FIDUCIARY", "LIQUIDITY"], seed=3)
        starts = sorted({(e["row"], e["col"], e["num"]) for e in cw["entries"]})
        self.assertEqual([s[2] for s in starts], list(range(1, len(starts) + 1)))

    def test_ignores_junk(self):
        self.assertEqual(build_crossword(["", "a-b", "x"])["entries"], [])


if __name__ == "__main__":
    unittest.main()
