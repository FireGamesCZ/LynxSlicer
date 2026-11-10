"""OrcaSlicer statistics JSON -> inventory plan: {"slots": {key: {"total_g", "by_layer_g"}}}."""


def plan_from_statistics(stats):
    filaments = stats["summary"]["filaments"]
    layers = stats.get("layers", [])
    ids = [str(f["id"]) for f in filaments]
    used = []  # per layer: {filament id: grams}
    for i, layer in enumerate(layers):
        if "filaments" in layer:
            used.append({str(f["id"]): f["weight"] for f in layer["filaments"]})
        elif len(ids) == 1:  # older file: the layer total is that one filament's
            used.append({ids[0]: layer["weight"]})
        else:
            raise ValueError(f"layer {i + 1} has no per-filament weights and the plate uses {len(ids)} "
                             "filaments; slice again with a newer OrcaSlicer")
    slots = {}
    for f, key in zip(filaments, ids):
        total = float(f["weight"])
        cumulative, running = [], 0.0
        for u in used:
            running += u.get(key, 0.0)
            cumulative.append(running)
        # The flush has no layer in the data: spread what the layers miss in proportion to the
        # cumulative extrusion, so the flush grows where the filament is used.
        gap = total - running
        if gap > 0 and cumulative:
            cumulative = [c + gap * c / running if running else c for c in cumulative]
            if not running:
                cumulative[-1] += gap
        if cumulative:
            cumulative[-1] = total
        slots[key] = {"total_g": total, "by_layer_g": [round(c, 4) for c in cumulative]}
    return {"slots": slots}


def remap_plan(plan, mapping):
    """Rename filament-id slot keys to printer slot names; an unmapped filament that is used is an error."""
    slots = {}
    for key, info in plan["slots"].items():
        if key not in mapping:
            if info["total_g"] > 0:
                raise ValueError(f"filament {key} is used but not assigned to a printer slot")
            continue
        if mapping[key] in slots:
            raise ValueError(f"more than one filament is assigned to slot {mapping[key]!r}")
        slots[mapping[key]] = info
    return {**plan, "slots": slots}


def default_mapping(plan):
    """The single-filament case: the only filament is on the external spool."""
    if len(plan["slots"]) != 1:
        raise ValueError(f"no default slot mapping for {len(plan['slots'])} filaments; assign each one")
    return {next(iter(plan["slots"])): "ext"}
