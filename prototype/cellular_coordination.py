"""Stage-A SCCE cellular coordination kernel.

This module tests local-neighbour economic matching. It is deliberately not a
complete macroeconomy: production recipes, credit, ownership, wages, capital
accumulation and ecological stocks remain in the existing prototypes.
Only the standard library is used.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


EPS = 1e-10


class CoordinationError(ValueError):
    pass


@dataclass(frozen=True)
class Cell:
    cell_id: str
    supply: Mapping[str, float]
    demand: Mapping[str, float]
    priority: Mapping[str, float]
    bid: Mapping[str, float]
    trade_consent: bool = True
    allowed_counterparties: frozenset[str] | None = None


@dataclass(frozen=True)
class Allocation:
    product: str
    seller: str
    buyer: str
    quantity: float
    distance: int
    communication_hops: int = 0


@dataclass(frozen=True)
class World:
    cells: Tuple[Cell, ...]
    edges: Tuple[Tuple[str, str], ...]
    prices: Mapping[str, float]
    transport_cost_per_hop: float = 0.04
    transaction_cost: float = 0.15
    communication_edges: Tuple[Tuple[str, str], ...] | None = None

    def __post_init__(self):
        ids = [c.cell_id for c in self.cells]
        if len(ids) != len(set(ids)) or not ids:
            raise CoordinationError("cell ids must be unique and non-empty")
        known = set(ids)
        for a, b in self.edges:
            if a not in known or b not in known or a == b:
                raise CoordinationError("invalid network edge")
        if self.transport_cost_per_hop < 0 or self.transaction_cost < 0:
            raise CoordinationError("coordination costs cannot be negative")
        for a, b in (self.communication_edges or ()):
            if a not in known or b not in known or a == b:
                raise CoordinationError("invalid communication edge")
        products = set(self.prices)
        if not products:
            raise CoordinationError("at least one product is required")
        for c in self.cells:
            if c.allowed_counterparties is not None and not c.allowed_counterparties.issubset(known):
                raise CoordinationError("unknown allowed counterparty")
            if any(v < 0 for v in c.supply.values()):
                raise CoordinationError("negative supply")
            if any(v < 0 for v in c.demand.values()):
                raise CoordinationError("negative demand")
            if any(v <= 0 for v in c.priority.values()):
                raise CoordinationError("priority must be positive")
            if any(v < 0 for v in c.bid.values()):
                raise CoordinationError("bid cannot be negative")
            if not set(c.supply).issubset(products) or not set(c.demand).issubset(products):
                raise CoordinationError("unknown product in cell")


def shortest_paths(world: World) -> Dict[str, Dict[str, int]]:
    graph = {c.cell_id: set() for c in world.cells}
    for a, b in world.edges:
        graph[a].add(b)
        graph[b].add(a)
    distances = {}
    for origin in graph:
        dist = {origin: 0}
        queue = deque([origin])
        while queue:
            node = queue.popleft()
            for nxt in sorted(graph[node]):
                if nxt not in dist:
                    dist[nxt] = dist[node] + 1
                    queue.append(nxt)
        distances[origin] = dist
    return distances



def communication_paths(world: World) -> Dict[str, Dict[str, int]]:
    """Shortest hop counts on the message-relay graph, not the delivery graph."""
    graph = {c.cell_id: set() for c in world.cells}
    for a, b in (world.communication_edges or world.edges):
        graph[a].add(b)
        graph[b].add(a)
    distances = {}
    for origin in graph:
        dist = {origin: 0}
        queue = deque([origin])
        while queue:
            node = queue.popleft()
            for nxt in sorted(graph[node]):
                if nxt not in dist:
                    dist[nxt] = dist[node] + 1
                    queue.append(nxt)
        distances[origin] = dist
    return distances

def _weighted_waterfill(needs: Mapping[str, float],
                        weights: Mapping[str, float],
                        capacity: float) -> Dict[str, float]:
    """Priority-weighted max-min allocation, never exceeding any request."""
    remaining = {k: max(0.0, float(v)) for k, v in needs.items()}
    result = {k: 0.0 for k in remaining}
    left = max(0.0, float(capacity))
    active = set(k for k, v in remaining.items() if v > EPS)
    while left > EPS and active:
        total_weight = sum(max(EPS, float(weights[k])) for k in active)
        saturated = []
        proposed = {}
        for k in active:
            share = left * max(EPS, float(weights[k])) / total_weight
            proposed[k] = share
            if share >= remaining[k] - EPS:
                saturated.append(k)
        if not saturated:
            for k, share in proposed.items():
                result[k] += share
                remaining[k] -= share
            left = 0.0
        else:
            for k in saturated:
                take = remaining[k]
                result[k] += take
                left -= take
                remaining[k] = 0.0
                active.remove(k)
    return result


def _products(world: World) -> List[str]:
    return sorted(world.prices)


def _pair_consented(cells: Mapping[str, Cell], seller: str, buyer: str) -> bool:
    """Both counterparties must opt in; optional allowlists are bilateral."""
    s = cells[seller]
    b = cells[buyer]
    return (
        s.trade_consent and b.trade_consent
        and (s.allowed_counterparties is None or buyer in s.allowed_counterparties)
        and (b.allowed_counterparties is None or seller in b.allowed_counterparties)
    )


def _state(world: World):
    """Net each cell's own stock against its own need before inter-cell trade.

    Self-consumption is an internal physical use, not a market transaction.
    Netting also prevents a seller from shipping stock that it needs locally.
    """
    supply = {p: {c.cell_id: float(c.supply.get(p, 0.0)) for c in world.cells}
              for p in _products(world)}
    demand = {p: {c.cell_id: float(c.demand.get(p, 0.0)) for c in world.cells}
              for p in _products(world)}
    for product in _products(world):
        for cell in world.cells:
            cid = cell.cell_id
            local_use = min(supply[product][cid], demand[product][cid])
            supply[product][cid] -= local_use
            demand[product][cid] -= local_use
    return supply, demand


def _route_allocations(world: World, product: str,
                       buyer_targets: Mapping[str, float],
                       supply: Dict[str, float],
                       distances: Mapping[str, Mapping[str, int]]) -> List[Allocation]:
    """Assign already determined buyer quantities to nearest available sellers."""
    result = []
    for buyer in sorted(buyer_targets):
        left = buyer_targets[buyer]
        sellers = sorted(
            (s for s, q in supply.items() if q > EPS and buyer in distances[s]
             and _pair_consented({c.cell_id: c for c in world.cells}, s, buyer)),
            key=lambda s: (distances[buyer][s], s))
        for seller in sellers:
            if left <= EPS:
                break
            qty = min(left, supply[seller])
            if qty > EPS:
                result.append(Allocation(product, seller, buyer, qty,
                                         distances[buyer][seller]))
                supply[seller] -= qty
                left -= qty
    return result


def allocate_central(world: World) -> List[Allocation]:
    """Global min-cost-flow benchmark for the linear service-value objective.

    The planner has full verified supply, demand, priority and route information.
    It maximizes weighted served quantity minus logistics cost, subject to seller
    stock and buyer-need constraints. It is an allocation benchmark, not a full
    social-welfare optimizer and not a model of real-world central administration.
    """
    supply, demand = _state(world)
    dist = shortest_paths(world)
    cells = {c.cell_id: c for c in world.cells}
    allocations: List[Allocation] = []

    for product in _products(world):
        sellers = sorted(s for s, q in supply[product].items()
                         if q > EPS and cells[s].trade_consent)
        buyers = sorted(b for b, q in demand[product].items()
                        if q > EPS and cells[b].trade_consent)
        if not sellers or not buyers:
            continue

        # Residual graph: source -> sellers -> buyers -> sink.
        source = 0
        seller_node = {s: i + 1 for i, s in enumerate(sellers)}
        buyer_offset = 1 + len(sellers)
        buyer_node = {b: buyer_offset + i for i, b in enumerate(buyers)}
        sink = buyer_offset + len(buyers)
        graph = [[] for _ in range(sink + 1)]

        def add_edge(u, v, capacity, cost, metadata=None):
            forward = [v, len(graph[v]), float(capacity), float(cost),
                       float(capacity), metadata]
            reverse = [u, len(graph[u]), 0.0, -float(cost), 0.0, None]
            graph[u].append(forward)
            graph[v].append(reverse)
            return len(graph[u]) - 1

        for seller in sellers:
            add_edge(source, seller_node[seller], supply[product][seller], 0.0)
        for buyer in buyers:
            add_edge(buyer_node[buyer], sink, demand[product][buyer], 0.0)

        route_edges = []
        for seller in sellers:
            for buyer in buyers:
                if (seller == buyer or buyer not in dist[seller]
                        or not _pair_consented(cells, seller, buyer)):
                    continue
                distance = dist[seller][buyer]
                priority = cells[buyer].priority.get(product, 1.0)
                # Objective matches evaluate(): priority-weighted service
                # benefit less per-unit transport cost.
                unit_cost = (distance * world.transport_cost_per_hop) - priority
                capacity = min(supply[product][seller], demand[product][buyer])
                if capacity <= EPS:
                    continue
                edge_index = add_edge(
                    seller_node[seller], buyer_node[buyer], capacity,
                    unit_cost, (seller, buyer, distance))
                route_edges.append((seller, buyer, distance,
                                    seller_node[seller], edge_index, capacity))

        # Successive shortest augmenting paths. Bellman-Ford handles negative
        # service-benefit edges; deterministic node/edge order makes replay stable.
        node_count = len(graph)
        while True:
            best = [float("inf")] * node_count
            parent = [None] * node_count
            best[source] = 0.0
            for _ in range(node_count - 1):
                changed = False
                for u in range(node_count):
                    if best[u] == float("inf"):
                        continue
                    for edge_index, edge in enumerate(graph[u]):
                        v, _, capacity, cost, _, _ = edge
                        candidate = best[u] + cost
                        if capacity > EPS and candidate < best[v] - 1e-12:
                            best[v] = candidate
                            parent[v] = (u, edge_index)
                            changed = True
                if not changed:
                    break
            if parent[sink] is None or best[sink] >= -EPS:
                break

            amount = float("inf")
            node = sink
            while node != source:
                u, edge_index = parent[node]
                amount = min(amount, graph[u][edge_index][2])
                node = u
            if amount <= EPS or amount == float("inf"):
                break

            node = sink
            while node != source:
                u, edge_index = parent[node]
                edge = graph[u][edge_index]
                edge[2] -= amount
                graph[node][edge[1]][2] += amount
                node = u

        for seller, buyer, distance, u, edge_index, initial_capacity in route_edges:
            residual = graph[u][edge_index][2]
            quantity = initial_capacity - residual
            if quantity > EPS:
                allocations.append(Allocation(product, seller, buyer,
                                               quantity, distance))

    return allocations

def allocate_market(world: World) -> List[Allocation]:
    """Global bilateral market: bids rank buyers; delivered asks rank sellers."""
    supply, demand = _state(world)
    dist = shortest_paths(world)
    cells = {c.cell_id: c for c in world.cells}
    allocations = []
    for p in _products(world):
        price = float(world.prices[p])
        buyers = sorted(
            (b for b, q in demand[p].items() if q > EPS and cells[b].trade_consent),
            key=lambda b: (-cells[b].bid.get(p, price), b))
        for buyer in buyers:
            left = demand[p][buyer]
            sellers = sorted(
                (s for s, q in supply[p].items() if q > EPS and buyer in dist[s]
             and _pair_consented(cells, s, buyer)),
                key=lambda s: (price + dist[buyer][s] * world.transport_cost_per_hop, s))
            for seller in sellers:
                delivered_ask = price + dist[buyer][seller] * world.transport_cost_per_hop
                if cells[buyer].bid.get(p, price) + EPS < delivered_ask:
                    continue
                qty = min(left, supply[p][seller])
                if qty > EPS:
                    allocations.append(Allocation(p, seller, buyer, qty,
                                                   dist[buyer][seller]))
                    supply[p][seller] -= qty
                    left -= qty
                if left <= EPS:
                    break
    return allocations


def allocate_cooperative(world: World) -> List[Allocation]:
    """Common pool: priority-weighted max-min rationing, then nearest delivery."""
    supply, demand = _state(world)
    dist = shortest_paths(world)
    cells = {c.cell_id: c for c in world.cells}
    allocations = []
    for p in _products(world):
        total_supply = sum(supply[p].values())
        eligible_demand = {b: q for b, q in demand[p].items()
                           if cells[b].trade_consent}
        eligible_supply = {s: q for s, q in supply[p].items()
                           if cells[s].trade_consent}
        weights = {b: cells[b].priority.get(p, 1.0) for b in eligible_demand}
        targets = _weighted_waterfill(eligible_demand, weights,
                                      sum(eligible_supply.values()))
        route_supply = dict(supply[p])
        for seller in route_supply:
            if not cells[seller].trade_consent:
                route_supply[seller] = 0.0
        allocations.extend(_route_allocations(world, p, targets, route_supply, dist))
    return allocations


def allocate_cellular(world: World, max_hops: int = 1,
                      max_rounds: int = 8) -> List[Allocation]:
    """Local protocol: buyers signal needs; reachable suppliers answer in rounds.

    A buyer only contacts suppliers within max_hops. Each supplier allocates its
    available stock among received requests by weighted max-min priority.
    Unfilled buyers may contact their next-nearest supplier in a later round.
    No global optimizer chooses the final matching.
    """
    if max_hops < 1 or max_rounds < 1:
        raise CoordinationError("max_hops and max_rounds must be positive")
    supply, demand = _state(world)
    dist = shortest_paths(world)
    cells = {c.cell_id: c for c in world.cells}
    allocations = []
    for p in _products(world):
        remaining = dict(demand[p])
        available = dict(supply[p])
        tried = {b: set() for b in remaining}
        for _ in range(max_rounds):
            requests = defaultdict(dict)
            for buyer in sorted(remaining):
                if remaining[buyer] <= EPS:
                    continue
                candidates = [
                    s for s, q in available.items()
                    if q > EPS and s not in tried[buyer]
                    and buyer in dist[s] and dist[buyer][s] <= max_hops
                    and _pair_consented(cells, s, buyer)
                ]
                if not candidates:
                    continue
                seller = min(candidates, key=lambda s: (dist[buyer][s], s))
                tried[buyer].add(seller)
                requests[seller][buyer] = remaining[buyer]
            if not requests:
                break
            moved = 0.0
            for seller in sorted(requests):
                weights = {b: cells[b].priority.get(p, 1.0)
                           for b in requests[seller]}
                granted = _weighted_waterfill(requests[seller], weights,
                                               available[seller])
                for buyer, qty in granted.items():
                    if qty <= EPS:
                        continue
                    allocations.append(Allocation(p, seller, buyer, qty,
                                                   dist[buyer][seller]))
                    available[seller] -= qty
                    remaining[buyer] -= qty
                    moved += qty
            if moved <= EPS:
                break
    return allocations



def allocate_relay_cellular(world: World, max_hops: int = 1,
                            max_rounds: int = 8,
                            trace: List[dict] | None = None) -> List[Allocation]:
    """Local request propagation with explicit neighbour-by-neighbour relaying.

    Buyers do not inspect a global supplier list. Requests travel one edge at a
    time with a TTL; offers, reservations and acceptances travel back along the
    discovered relay path. Unfilled buyers can retry another supplier in later
    rounds. The trace counts actual hop messages, including failed searches.
    """
    if max_hops < 1 or max_rounds < 1:
        raise CoordinationError("max_hops and max_rounds must be positive")
    supply, demand = _state(world)
    graph = {c.cell_id: set() for c in world.cells}
    communication_edges = world.communication_edges or world.edges
    for a, b in communication_edges:
        graph[a].add(b)
        graph[b].add(a)
    delivery_distances = shortest_paths(world)
    cells = {c.cell_id: c for c in world.cells}
    allocations: List[Allocation] = []
    message_trace = trace if trace is not None else []

    def relay_message(message_type, product, round_index, path, quantity):
        # path is origin -> ... -> destination. Return messages reverse it.
        if message_type in ("offer_forward", "reservation_forward"):
            hops = zip(reversed(path[1:]), reversed(path[:-1]))
        else:
            hops = zip(path[:-1], path[1:])
        for sender, receiver in hops:
            message_trace.append({
                "type": message_type, "product": product,
                "round": round_index, "sender": sender,
                "receiver": receiver, "quantity": quantity,
                "hops": len(path) - 1,
            })

    for product in _products(world):
        remaining = dict(demand[product])
        available = dict(supply[product])
        tried = {buyer: set() for buyer in remaining}

        for round_index in range(max_rounds):
            requests = defaultdict(dict)
            request_paths = {}
            for buyer in sorted(remaining):
                if remaining[buyer] <= EPS:
                    continue
                visited = {buyer}
                frontier = [(buyer, [buyer])]
                offers = []
                for depth in range(1, max_hops + 1):
                    next_frontier = []
                    for node, path in sorted(frontier, key=lambda item: item[0]):
                        for neighbour in sorted(graph[node]):
                            if neighbour in visited:
                                continue
                            visited.add(neighbour)
                            next_path = path + [neighbour]
                            next_frontier.append((neighbour, next_path))
                            message_trace.append({
                                "type": "request_forward", "product": product,
                                "round": round_index, "origin": buyer,
                                "sender": node, "receiver": neighbour,
                                "quantity": remaining[buyer], "ttl": max_hops - depth,
                            })
                            if (neighbour != buyer
                                    and available[neighbour] > EPS
                                    and neighbour not in tried[buyer]
                                    and _pair_consented(cells, neighbour, buyer)):
                                if neighbour in delivery_distances[buyer]:
                                    offers.append((depth, delivery_distances[buyer][neighbour],
                                                   neighbour, next_path))
                    if offers:
                        break
                    frontier = next_frontier
                    if not frontier:
                        break

                if not offers:
                    continue
                communication_hops, delivery_distance, seller, path = min(
                    offers, key=lambda item: (item[0], item[1], item[2], tuple(item[3])))
                tried[buyer].add(seller)
                requests[seller][buyer] = remaining[buyer]
                request_paths[(seller, buyer)] = (communication_hops, delivery_distance, path)
                relay_message("offer_forward", product, round_index,
                              path, available[seller])

            if not requests:
                break

            moved = 0.0
            for seller in sorted(requests):
                weights = {
                    buyer: cells[buyer].priority.get(product, 1.0)
                    for buyer in requests[seller]
                }
                granted = _weighted_waterfill(
                    requests[seller], weights, available[seller])
                for buyer in sorted(granted):
                    quantity = granted[buyer]
                    if quantity <= EPS:
                        continue
                    communication_hops, delivery_distance, path = request_paths[(seller, buyer)]
                    allocations.append(Allocation(
                        product, seller, buyer, quantity, delivery_distance,
                        communication_hops))
                    available[seller] -= quantity
                    remaining[buyer] -= quantity
                    moved += quantity
                    relay_message("reservation_forward", product, round_index,
                                  path, quantity)
                    relay_message("acceptance_forward", product, round_index,
                                  path, quantity)
            if moved <= EPS:
                break
    return allocations

POLICIES = {
    "market": allocate_market,
    "central": allocate_central,
    "cooperative": allocate_cooperative,
}


def evaluate(world: World, allocations: Sequence[Allocation]) -> Dict[str, float]:
    cells = {c.cell_id: c for c in world.cells}
    demand_total = 0.0
    weighted_demand = 0.0
    weighted_served = 0.0
    served_by_cell = {c.cell_id: 0.0 for c in world.cells}
    demand_by_cell = {c.cell_id: 0.0 for c in world.cells}
    logistics = 0.0
    coordination = 0.0
    traded = 0.0
    for c in world.cells:
        for p, q in c.demand.items():
            demand_total += q
            weighted_demand += q * c.priority.get(p, 1.0)
            demand_by_cell[c.cell_id] += q
    for a in allocations:
        priority = cells[a.buyer].priority.get(a.product, 1.0)
        weighted_served += a.quantity * priority
        served_by_cell[a.buyer] += a.quantity
        logistics += a.quantity * a.distance * world.transport_cost_per_hop
        coordination += world.transaction_cost
        traded += a.quantity
    fulfilment = (sum(served_by_cell.values()) / demand_total) if demand_total else 1.0
    weighted_fulfilment = weighted_served / weighted_demand if weighted_demand else 1.0
    cell_rates = [
        served_by_cell[k] / demand_by_cell[k] if demand_by_cell[k] else 1.0
        for k in sorted(demand_by_cell)
    ]
    mean_rate = sum(cell_rates) / len(cell_rates) if cell_rates else 1.0
    gini = 0.0
    if mean_rate > EPS:
        diffs = sum(abs(a - b) for a in cell_rates for b in cell_rates)
        gini = diffs / (2.0 * len(cell_rates) ** 2 * mean_rate)
    return {
        "demand_units": demand_total,
        "served_units": traded,
        "unmet_units": max(0.0, demand_total - traded),
        "fulfilment_rate": fulfilment,
        "weighted_fulfilment_rate": weighted_fulfilment,
        "lower_cell_fulfilment": min(cell_rates) if cell_rates else 1.0,
        "cell_fulfilment_gini": gini,
        "logistics_cost": logistics,
        "coordination_cost": coordination,
        "weighted_service_value": weighted_served,
        "net_service_value": weighted_served - logistics - coordination,
        "transactions": float(len(allocations)),
        "mean_route_hops": (sum(a.distance for a in allocations) / len(allocations)
                            if allocations else 0.0),
    }


def default_world(seed: int = 1, shock: str = "none") -> World:
    """Seven-cell synthetic world with three products and heterogeneous needs."""
    rng = random.Random(seed)
    products = ("food", "materials", "energy")
    producers = {
        "cell-1": {"food": 22.0},
        "cell-2": {"materials": 19.0},
        "cell-3": {"energy": 24.0},
        "cell-4": {"food": 17.0},
        "cell-5": {"materials": 21.0},
        "cell-6": {"energy": 18.0},
        "cell-7": {"food": 16.0},
    }
    edges = (
        ("cell-1", "cell-2"), ("cell-2", "cell-3"),
        ("cell-3", "cell-4"), ("cell-4", "cell-5"),
        ("cell-5", "cell-6"), ("cell-6", "cell-7"),
        ("cell-7", "cell-1"), ("cell-1", "cell-4"),
        ("cell-3", "cell-6"),
    )
    cells = []
    for i in range(1, 8):
        cid = f"cell-{i}"
        demand = {p: rng.uniform(3.0, 7.0) for p in products}
        priority = {
            "food": rng.uniform(1.6, 2.2),
            "materials": rng.uniform(0.8, 1.2),
            "energy": rng.uniform(1.2, 1.8),
        }
        bid = {p: 1.0 + 0.12 * priority[p] for p in products}
        supply = dict(producers[cid])
        cells.append(Cell(cid, supply, demand, priority, bid))
    if shock == "supply_crisis":
        for c in cells:
            if c.cell_id in ("cell-3", "cell-6"):
                s = dict(c.supply)
                s["energy"] *= 0.45
                object.__setattr__(c, "supply", s)
    elif shock == "demand_surge":
        for c in cells:
            d = dict(c.demand)
            d["food"] *= 1.45
            object.__setattr__(c, "demand", d)
    elif shock not in ("none", "compound"):
        raise CoordinationError("unknown shock: " + shock)
    elif shock == "compound":
        for c in cells:
            d = dict(c.demand)
            d["food"] *= 1.25
            object.__setattr__(c, "demand", d)
            if c.cell_id in ("cell-3", "cell-6"):
                s = dict(c.supply)
                s["energy"] *= 0.60
                object.__setattr__(c, "supply", s)
    return World(tuple(cells), edges, {p: 1.0 for p in products})


def run_comparison(seed: int = 1, shock: str = "none",
                   cellular_hops: int = 1) -> Dict[str, Dict[str, float]]:
    world = default_world(seed, shock)
    results = {
        "market": evaluate(world, allocate_market(world)),
        "central": evaluate(world, allocate_central(world)),
        "cooperative": evaluate(world, allocate_cooperative(world)),
        "cellular": evaluate(world, allocate_relay_cellular(world, cellular_hops)),
    }
    return results


def _confidence_summary(values):
    values = [float(v) for v in values]
    n = len(values)
    avg = statistics.mean(values) if n else 0.0
    sd = statistics.stdev(values) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {
        "n": n, "mean": avg,
        "median": statistics.median(values) if n else 0.0,
        "sd": sd, "ci95_low": avg - half, "ci95_high": avg + half,
    }


def monte_carlo(seeds: Iterable[int] = range(1, 101),
                shock: str = "none", cellular_hops: int = 1):
    seeds = tuple(seeds)
    rows = []
    for seed in seeds:
        result = run_comparison(seed, shock, cellular_hops)
        for regime, metrics in result.items():
            rows.append({"seed": seed, "shock": shock, "regime": regime, **metrics})

    numeric_keys = [
        k for k, v in rows[0].items()
        if isinstance(v, (int, float)) and k not in ("seed",)
    ]
    by_regime = {}
    summary = {}
    for regime in ("market", "central", "cooperative", "cellular"):
        regime_rows = [r for r in rows if r["regime"] == regime]
        by_regime[regime] = {r["seed"]: r for r in regime_rows}
        summary[regime] = {
            metric: _confidence_summary([r[metric] for r in regime_rows])
            for metric in numeric_keys
        }

    baseline = by_regime["market"]
    paired_differences = {}
    for regime in ("central", "cooperative", "cellular"):
        paired_differences[regime] = {}
        for metric in numeric_keys:
            differences = [
                by_regime[regime][seed][metric] - baseline[seed][metric]
                for seed in sorted(baseline)
            ]
            paired_differences[regime][metric] = _confidence_summary(differences)

    return {
        "runs": len(seeds), "shock": shock,
        "cellular_hops": cellular_hops,
        "summary": summary,
        "paired_differences_vs_market": paired_differences,
        "rows": rows,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--shock", choices=("none", "supply_crisis", "demand_surge", "compound"),
                        default="none")
    parser.add_argument("--hops", type=int, default=1)
    parser.add_argument("--monte-carlo", type=int, default=0)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    if args.monte_carlo:
        result = monte_carlo(range(1, args.monte_carlo + 1), args.shock, args.hops)
        if args.summary_only:
            result.pop("rows", None)
    else:
        result = run_comparison(args.seed, args.shock, args.hops)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
