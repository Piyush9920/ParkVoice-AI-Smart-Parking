"""
ParkVoice AI - A* Search Algorithm & Smart Slot Recommendation Engine
====================================================================
Implements real A* pathfinding using Manhattan distance heuristic:
    f(n) = g(n) + h(n)
where:
    g(n) = exact cost from start node to n (steps taken)
    h(n) = Manhattan distance |x1 - x2| + |y1 - y2|
"""

import heapq
from typing import List, Tuple, Dict, Any, Optional, Set

# Entrance Gate position (Row 4, Col 1) - Separate from parking slots P01-P12
ENTRANCE_COORDINATES = (4, 1)

# 4x3 Slot coordinate mapping:
# Row 0: P01 (0,0), P02 (0,1), P03 (0,2)
# Row 1: P04 (1,0), P05 (1,1), P06 (1,2)
# Row 2: P07 (2,0), P08 (2,1), P09 (2,2)
# Row 3: P10 (3,0), P11 (3,1), P12 (3,2)
SLOT_COORDINATES = {
    "P01": (0, 0), "P02": (0, 1), "P03": (0, 2),
    "P04": (1, 0), "P05": (1, 1), "P06": (1, 2),
    "P07": (2, 0), "P08": (2, 1), "P09": (2, 2),
    "P10": (3, 0), "P11": (3, 1), "P12": (3, 2),
}

COORDINATES_TO_SLOT = {v: k for k, v in SLOT_COORDINATES.items()}


def manhattan_distance(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
    """Calculate Manhattan distance heuristic h(n) between two grid points."""
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def get_neighbors(
    node: Tuple[int, int],
    min_row: int = -1,
    max_row: int = 4,
    min_col: int = -1,
    max_col: int = 3
) -> List[Tuple[int, int]]:
    """
    Generate valid orthogonal neighbors (Up, Down, Left, Right).
    The navigable space includes aisles (-1 to 4 row, -1 to 3 col)
    so vehicles can always navigate around blocked bays via perimeter lanes.
    """
    r, c = node
    candidates = [
        (r - 1, c),  # Up
        (r + 1, c),  # Down
        (r, c - 1),  # Left
        (r, c + 1),  # Right
    ]
    valid = []
    for nr, nc in candidates:
        if min_row <= nr <= max_row and min_col <= nc <= max_col:
            valid.append((nr, nc))
    return valid


def find_path(
    start: Tuple[int, int],
    goal: Tuple[int, int],
    blocked_cells: Set[Tuple[int, int]],
    min_row: int = -1,
    max_row: int = 4,
    min_col: int = -1,
    max_col: int = 3
) -> Dict[str, Any]:
    """
    Execute real A* pathfinding from start to goal avoiding blocked cells.
    
    Args:
        start: (row, col) of entrance
        goal: (row, col) of target parking bay
        blocked_cells: Set of (row, col) tuples that are impassable (occupied/reserved slots)
                       Note: goal is exempt from blocked cells so vehicle can enter it.
        min_row, max_row, min_col, max_col: Grid bounding limits
        
    Returns:
        Dict containing:
            - 'success': bool
            - 'path': List of (row, col) tuples from start to goal
            - 'distance': Number of steps (cost g)
            - 'explored_nodes': List of visited nodes in search order
            - 'status': "SUCCESS" | "NO_PATH"
    """
    if start == goal:
        return {
            "success": True,
            "path": [start],
            "distance": 0,
            "explored_nodes": [start],
            "status": "SUCCESS"
        }

    # Ensure goal is passable even if marked in blocked_cells
    effective_blocked = set(blocked_cells) - {goal}

    # Priority queue stores: (f_score, tie_breaker_counter, current_node)
    counter = 0
    open_heap: List[Tuple[int, int, Tuple[int, int]]] = []
    
    h_start = manhattan_distance(start, goal)
    heapq.heappush(open_heap, (h_start, counter, start))
    
    g_score: Dict[Tuple[int, int], int] = {start: 0}
    came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
    explored_nodes: List[Tuple[int, int]] = []
    visited_set: Set[Tuple[int, int]] = set()

    while open_heap:
        current_f, _, current = heapq.heappop(open_heap)

        if current in visited_set:
            continue
        visited_set.add(current)
        explored_nodes.append(current)

        # Check goal reached
        if current == goal:
            # Reconstruct path backwards from goal
            path = [goal]
            curr = goal
            while curr in came_from:
                curr = came_from[curr]
                path.append(curr)
            path.reverse()
            
            return {
                "success": True,
                "path": path,
                "distance": len(path) - 1,
                "explored_nodes": explored_nodes,
                "status": "SUCCESS"
            }

        current_g = g_score[current]

        # Explore orthogonal neighbors
        for neighbor in get_neighbors(current, min_row, max_row, min_col, max_col):
            if neighbor in visited_set:
                continue
            if neighbor in effective_blocked:
                continue

            tentative_g = current_g + 1

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                g_score[neighbor] = tentative_g
                f = tentative_g + manhattan_distance(neighbor, goal)
                came_from[neighbor] = current
                counter += 1
                heapq.heappush(open_heap, (f, counter, neighbor))

    # Open set exhausted without reaching goal
    return {
        "success": False,
        "path": [],
        "distance": -1,
        "explored_nodes": explored_nodes,
        "status": "NO_PATH"
    }


def recommend_best_slot(
    slots: List[Dict[str, Any]],
    vehicle_type: str = "Car",
    entrance: Tuple[int, int] = ENTRANCE_COORDINATES
) -> Dict[str, Any]:
    """
    Intelligent slot recommendation:
    1. Filter available slots.
    2. Check vehicle type compatibility (EV charger priority, bike compact priority, etc.).
    3. Run A* pathfinding from entrance to each candidate to determine true navigable distance.
    4. Rank candidates by distance and compatibility score.
    5. Generate a human-friendly AI reasoning string.
    
    Returns dict with:
        - 'recommended_slot': slot dict or None
        - 'path': list of path coordinates
        - 'distance': int
        - 'est_time_seconds': int
        - 'est_time_str': str
        - 'reason': str
        - 'all_candidates': list of scored candidates
    """
    available_slots = [s for s in slots if s.get("status") == "AVAILABLE"]
    
    if not available_slots:
        return {
            "recommended_slot": None,
            "path": [],
            "distance": 0,
            "est_time_seconds": 0,
            "est_time_str": "0s",
            "reason": "All parking slots are currently occupied or reserved. Please try again shortly.",
            "all_candidates": []
        }

    # Identify blocked coordinates (slots that are OCCUPIED or RESERVED)
    blocked_coords: Set[Tuple[int, int]] = set()
    for s in slots:
        if s.get("status") in ("OCCUPIED", "RESERVED"):
            r = int(s["row_index"])
            c = int(s["col_index"])
            blocked_coords.add((r, c))

    v_type_lower = vehicle_type.lower() if vehicle_type else "car"

    candidates = []
    for slot in available_slots:
        target_coords = (int(slot["row_index"]), int(slot["col_index"]))
        
        # Run real A*
        astar_res = find_path(
            start=entrance,
            goal=target_coords,
            blocked_cells=blocked_coords
        )

        if not astar_res["success"]:
            continue

        distance = astar_res["distance"]
        has_ev = bool(slot.get("has_ev_charger", 0))
        slot_type = slot.get("slot_type", "Standard")

        # Compatibility score calculation
        # Lower score = better recommendation
        compatibility_score = distance * 10

        if v_type_lower == "ev":
            if has_ev:
                compatibility_score -= 50  # Heavy preference for EV charger
            else:
                compatibility_score += 30
        elif v_type_lower == "bike":
            if slot_type == "Compact":
                compatibility_score -= 20
        elif v_type_lower == "suv":
            if slot_type == "Compact":
                compatibility_score += 100  # Strongly discourage compact for SUV

        candidates.append({
            "slot": slot,
            "path": astar_res["path"],
            "distance": distance,
            "explored_nodes": astar_res["explored_nodes"],
            "score": compatibility_score,
            "has_ev": has_ev
        })

    if not candidates:
        return {
            "recommended_slot": None,
            "path": [],
            "distance": 0,
            "est_time_seconds": 0,
            "est_time_str": "0s",
            "reason": "No accessible path found to available slots. Aisle routes may be obstructed.",
            "all_candidates": []
        }

    # Sort by compatibility score, then by distance, then by slot number
    candidates.sort(key=lambda x: (x["score"], x["distance"], x["slot"]["slot_number"]))
    best = candidates[0]
    best_slot = best["slot"]
    dist = best["distance"]
    est_seconds = max(15, dist * 12)
    
    if est_seconds < 60:
        time_str = f"{est_seconds} sec"
    else:
        mins = round(est_seconds / 60, 1)
        time_str = f"{mins} min"

    # Dynamic natural language reasoning based on live parameters
    slot_num = best_slot["slot_number"]
    has_ev = bool(best_slot.get("has_ev_charger", 0))
    stype = best_slot.get("slot_type", "Standard")

    if v_type_lower == "ev":
        if has_ev:
            reason = f"Slot {slot_num} is the closest available EV charging bay ({dist} units from entrance, ~{time_str} drive)."
        else:
            reason = f"Slot {slot_num} is recommended ({dist} units away). Note: All EV-dedicated chargers are currently occupied."
    elif v_type_lower == "bike":
        if stype == "Compact":
            reason = f"Slot {slot_num} is a compact bay designated for two-wheelers ({dist} units away, ~{time_str} drive)."
        else:
            reason = f"Slot {slot_num} is the nearest available spot to the entrance ({dist} units away, ~{time_str} drive)."
    elif v_type_lower == "suv":
        reason = f"Slot {slot_num} offers a spacious {stype} bay with direct lane clearance ({dist} units away, ~{time_str} drive)."
    else:
        reason = f"Slot {slot_num} is the optimal spot nearest to the entrance gate ({dist} units away, ~{time_str} drive)."

    return {
        "recommended_slot": best_slot,
        "path": best["path"],
        "distance": dist,
        "est_time_seconds": est_seconds,
        "est_time_str": time_str,
        "reason": reason,
        "all_candidates": [
            {
                "slot_number": c["slot"]["slot_number"],
                "distance": c["distance"],
                "score": c["score"]
            }
            for c in candidates
        ]
    }
