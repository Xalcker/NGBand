"""Instrucciones por función de build/smoke/tr.txt (ver trace.lua), con los símbolos de build/ngband.sym."""
import bisect, collections, re
syms = sorted((int(p[0], 16), p[2]) for p in (l.split() for l in open("build/ngband.sym")) if len(p) == 3 and p[1] in "tT")
addrs = [a for a, _ in syms]
c, n = collections.Counter(), 0
for l in open("build/smoke/tr.txt"):
    m = re.match(r"([0-9A-F]{6}): ", l)
    if not m:
        continue
    pc = int(m.group(1), 16); n += 1
    i = bisect.bisect_right(addrs, pc) - 1
    c["BIOS" if pc >= 0xC00000 else (syms[i][1] if i >= 0 else "?")] += 1
print("instrucciones por cuadro:", n // 3)
for k, v in c.most_common(20):
    print(f"{v // 3:7d} {100 * v / n:5.1f}% {k}")
