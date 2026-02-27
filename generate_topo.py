import math
import matplotlib.pyplot as plt
import random
from .base_topology import *
try:
    import networkx as nx
    has_nx = True
except ImportError:
    has_nx = False


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def read_NSFnet24():                                         
    nodes = {
    1: ("San Diego",       32.7157, -117.1611),
    2: ("Los Angeles",     34.0522, -118.2437),
    3: ("Oakland",         37.8044, -122.2711),
    4: ("San Francisco",   37.7749, -122.4194),
    5: ("Reno",            39.5296, -119.8138),
    6: ("Salt Lake City",  40.7608, -111.8910),
    7: ("Phoenix",         33.4484, -112.0740),
    8: ("Denver",          39.7392, -104.9903),
    9: ("El Paso",         31.7619, -106.4850),
    10: ("Dallas",         32.7767, -96.7970),
    11: ("Houston",        29.7604, -95.3698),
    12: ("Kansas City",    39.0997, -94.5786),
    13: ("Minneapolis",    44.9778, -93.2650),
    14: ("Chicago",        41.8781, -87.6298),
    15: ("St. Louis",      38.6270, -90.1994),
    16: ("Memphis",        35.1495, -90.0490),
    17: ("New Orleans",    29.9511, -90.0715),
    18: ("Atlanta",        33.7490, -84.3880),
    19: ("Miami",          25.7617, -80.1918),
    20: ("Washington DC",  38.9072, -77.0369),
    21: ("Pittsburgh",     40.4406, -79.9959),
    22: ("New York",       40.7128, -74.0060),
    23: ("Boston",         42.3601, -71.0589),
    24: ("Seattle",        47.6062, -122.3321)}

    edges = [
    (1,2), (1,6), (2,3), (2,6), (3,4), (3,5), (3,7), (4,5), (4,7), (5,8), (6,7), (6,9), (6,11), (7,8), (7,9), (8,10), (9,10), (9,11),
    (9,12), (10,13), (10, 14), (11,12), (11, 15), (11, 19), (12, 13), (12, 16), (13, 14), (13, 17), (14, 18), (15,20), (16, 17), (16,21), (16,22), (17,18),
    (17,22), (17,23), (18,24), (19,20), (20,21), (21,22), (22,23), (23,24)]

    G = nx.Graph()    # instead of G = sample.get_topology_object()  
    for nid, (name, lat, lon) in nodes.items():
        G.add_node(nid, name=name, latitude=lat, longitude=lon)
    
    for u, v in edges:
        lat1, lon1 = nodes[u][1], nodes[u][2]
        lat2, lon2 = nodes[v][1], nodes[v][2]
        d = haversine(lat1, lon1, lat2, lon2)
        G.add_edge(u, v, length=d)

    topology = BaseTopology()

    candidate_nodes = {2, 10, 14, 18, 22}

    all_nodes = []
    for i in G.nodes():
        lat, lon = G.nodes[i]['latitude'], G.nodes[i]['longitude']
        if i in candidate_nodes:
            min_p = random.randint(80, 200)
            max_p = min_p + random.randint(100, 200)
            topology.add_node(i, node_type='data_center',
                              min_power_budget=min_p,
                              max_power_budget=max_p,
                              is_new=True, lat=lat, lon=lon)
        else:
            demand = random.randint(200, 800)
            topology.add_node(i, node_type='data_center',
                              demand=demand, lat=lat, lon=lon)
        all_nodes.append(i)


    fiber_names, cand_fibers = [], []
    k = 1
    for u, v in G.edges():
        length = G[u][v]["length"]
        if (u not in candidate_nodes) and (v not in candidate_nodes):
            fname = f"fiber{k}"
            cost_light = random.randint(50,150)
            cost_deploy = random.randint(200,600)
            topology.add_fiber(fname, u, v, length,
                               lit=4, dark=4,
                               cost2light=cost_light,
                               cost2deploy=cost_deploy,
                               is_new=False)
            fiber_names.append(fname)
        else:
            fname = f"cand_fiber{k}"
            cost_deploy = random.randint(200,600)
            topology.add_fiber(fname, u, v, length,
                               cost2deploy=cost_deploy,
                               is_new=True)
            cand_fibers.append(fname)
        k += 1


    for f_id in range(5):
        fail = topology.create_failure(f"Failure_{f_id+1}")
        pool = [('fiber', f) for f in (fiber_names + cand_fibers)] + \
               [('node', n) for n in all_nodes]
        kind, name = random.choice(pool)
        if kind == 'fiber':
            fail.add_failed_fiber(topology.fibers[name])
        else:
            fail.add_failed_node(topology.nodes[name])

    topology.graph = G
    return topology       


topo = read_NSFnet24()
print(topo)
topo.save("NSF24")
topo.print_failures()
topo.show_graph()