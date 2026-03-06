import networkx as nx
import random
import math
from collections import Counter

random.seed(42)

G = nx.Graph()
G.add_edge(1, 2, weight=2800)
G.add_edge(2, 3, weight=1200)
G.add_edge(2, 4, weight=1200)
G.add_edge(3, 4, weight=1400)
nodes = [1, 2, 3, 4]

modulation_formats = [
    {"name": "BPSK",  "reach": 8000, "spectral_eff": 1},
    {"name": "QPSK",  "reach": 4000, "spectral_eff": 2},
    {"name": "8QAM",  "reach": 2000, "spectral_eff": 3},
    {"name": "16QAM", "reach": 1000, "spectral_eff": 4},
]
SLOT_WIDTH = 12.5
F = 320   # 320 x 12.5 GHz = 4 THz (realistic C-band)
# NOTE: 1000 requests with F=720 saturates the bottleneck link at 53% blocking.
# Defrag cannot recover a physically full link. Use N=300 for a meaningful demo.
N_REQUESTS = 300

def choose_modulation(distance):
    for mod in sorted(modulation_formats, key=lambda m: m["spectral_eff"], reverse=True):
        if distance <= mod["reach"]:
            return mod
    return modulation_formats[0]

requests = []
for i in range(N_REQUESTS):
    src, dst = random.sample(nodes, 2)
    bw = random.choice([50, 100, 200])
    path = nx.shortest_path(G, src, dst, weight='weight')
    dist = nx.shortest_path_length(G, src, dst, weight='weight')
    mod = choose_modulation(dist)
    slots = math.ceil(bw / (mod["spectral_eff"] * SLOT_WIDTH))
    requests.append({"id": i, "source": src, "destination": dst,
                     "bandwidth": bw, "path": path, "distance": dist,
                     "modulation": mod["name"], "slots_required": slots})

for r in requests[:5]:
    print(r)

all_links = [frozenset(e) for e in G.edges()]
spectrum_map = {lnk: [-1] * F for lnk in all_links}

def free_blocks(path_links, sm, F):
    blks = []
    i = 0
    while i < F:
        if all(sm[lnk][i] == -1 for lnk in path_links):
            s = i
            while i < F and all(sm[lnk][i] == -1 for lnk in path_links):
                i += 1
            blks.append((s, i - s))
        else:
            i += 1
    return blks

def valid_starts(bstart, bsize, k, path_links, sm, F):
    out = []
    for st in range(bstart, bstart + bsize - k + 1):
        en = st + k
        if (st == 0 or all(sm[lnk][st-1] == -1 for lnk in path_links)) and \
           (en >= F  or all(sm[lnk][en]   == -1 for lnk in path_links)):
            out.append(st)
    return out

# Random allocation (creates fragmentation for defrag to fix)
blocked_count = 0
allocated_count = 0
blocked_requests = []

for req in requests:
    path = req["path"]
    k = req["slots_required"]
    plinks = [frozenset({path[i], path[i+1]}) for i in range(len(path)-1)]
    all_valid = []
    for bs, bsz in free_blocks(plinks, spectrum_map, F):
        if bsz >= k:
            all_valid.extend(valid_starts(bs, bsz, k, plinks, spectrum_map, F))
    if not all_valid:
        blocked_count += 1
        blocked_requests.append(req)
        continue
    st = random.choice(all_valid)
    for lnk in plinks:
        for s in range(st, st+k):
            spectrum_map[lnk][s] = req["id"]
    allocated_count += 1

print(f"\n=== After Random Allocation ===")
print(f"Allocated: {allocated_count}  Blocked: {blocked_count}  BP: {blocked_count/len(requests):.3f}")

slot_counts = Counter(r["slots_required"] for r in requests)
print("\nSlot distribution:", {sz: cnt for sz, cnt in sorted(slot_counts.items())})

def build_requests_dict(sm, F):
    rd = {}
    for lnk, slots in sm.items():
        i = 0
        while i < F:
            rid = slots[i]
            if rid != -1:
                s = i
                while i < F and slots[i] == rid:
                    i += 1
                en = i
                if rid not in rd:
                    rd[rid] = {"slots": (s, en), "path": [lnk]}
                else:
                    assert rd[rid]["slots"] == (s, en), \
                        f"Req {rid} inconsistent slots: {rd[rid]['slots']} vs ({s},{en})"
                    rd[rid]["path"].append(lnk)
            else:
                i += 1
    return rd

requests_dict = build_requests_dict(spectrum_map, F)

def frag_report(label, sm, F):
    print(f"\n=== Fragmentation: {label} ===")
    for lnk, slots in sm.items():
        free = slots.count(-1)
        nb, mb, cb, inb = 0, 0, 0, False
        for s in slots:
            if s == -1:
                cb += 1
                if not inb: nb += 1; inb = True
                mb = max(mb, cb)
            else:
                inb = False; cb = 0
        print(f"  {set(lnk)}: free={free} blocks={nb} max_block={mb} frag={nb/free if free else 0:.4f}")

frag_report("After Random Allocation", spectrum_map, F)

def reallocate_exact(rid, sm, rd, F):
    plinks = rd[rid]["path"]
    os, oe = rd[rid]["slots"]
    k = oe - os
    for lnk in plinks:
        for s in range(os, oe): sm[lnk][s] = -1
    cands = []
    for bs, bsz in free_blocks(plinks, sm, F):
        if bsz >= k:
            for st in valid_starts(bs, bsz, k, plinks, sm, F):
                cands.append((bsz, st))
    if not cands:
        for lnk in plinks:
            for s in range(os, oe): sm[lnk][s] = rid
        return False
    exact = [(sz, st) for sz, st in cands if sz == k]
    ns = (min(exact, key=lambda x: x[1])[1] if exact
          else min(cands, key=lambda x: (x[0], x[1]))[1])
    if ns == os:
        for lnk in plinks:
            for s in range(os, oe): sm[lnk][s] = rid
        return False
    for lnk in plinks:
        for s in range(ns, ns+k): sm[lnk][s] = rid
    rd[rid]["slots"] = (ns, ns+k)
    return True

def defragment(sm, rd, F):
    moved = 0
    for rid in sorted(rd, key=lambda r: rd[r]["slots"][1] - rd[r]["slots"][0], reverse=True):
        if reallocate_exact(rid, sm, rd, F):
            moved += 1
    print(f"  Lightpaths moved: {moved}")
    return moved

def alloc_blocked(req, sm, rd, F):
    path = req["path"]
    k = req["slots_required"]
    rid = req["id"]
    plinks = [frozenset({path[i], path[i+1]}) for i in range(len(path)-1)]
    cands = []
    for bs, bsz in free_blocks(plinks, sm, F):
        if bsz >= k:
            for st in valid_starts(bs, bsz, k, plinks, sm, F):
                cands.append((bsz, st))
    if not cands:
        return False
    exact = [(sz, st) for sz, st in cands if sz == k]
    st = (min(exact, key=lambda x: x[1])[1] if exact
          else min(cands, key=lambda x: (x[0], x[1]))[1])
    for lnk in plinks:
        for s in range(st, st+k): sm[lnk][s] = rid
    rd[rid] = {"source": req["source"], "destination": req["destination"],
               "slots": (st, st+k), "path": plinks}
    return True

initial_blocked = len(blocked_requests)
print(f"\n=== Defrag Loop (recovering {initial_blocked} blocked requests) ===")

iteration = 0
while True:
    iteration += 1
    print(f"\n-- Iteration {iteration} --")
    defragment(spectrum_map, requests_dict, F)
    newly, new_blocked = 0, []
    for req in blocked_requests:
        if alloc_blocked(req, spectrum_map, requests_dict, F):
            newly += 1
        else:
            new_blocked.append(req)
    if newly > 0:
        requests_dict = build_requests_dict(spectrum_map, F)
    print(f"  New allocations: {newly}")
    blocked_requests = new_blocked
    if newly == 0:
        print("  No further improvement. Stopping.")
        break

frag_report("After Defragmentation", spectrum_map, F)
print(f"\n=== Final Results ===")
print(f"Total requests:       {len(requests)}")
print(f"Initially blocked:    {initial_blocked}  (BP={initial_blocked/len(requests):.3f})")
print(f"Recovered by defrag:  {initial_blocked - len(blocked_requests)}")
print(f"Final blocked:        {len(blocked_requests)}  (BP={len(blocked_requests)/len(requests):.3f})")