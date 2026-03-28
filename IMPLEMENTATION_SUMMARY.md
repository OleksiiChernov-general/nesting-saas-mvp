# Nesting SaaS MVP - Developer Notes

## What is fully implemented now

- Multi-file DXF upload is the primary frontend workflow.
- Cleanup runs per uploaded file and produces the nesting polygon used for that part.
- Users configure a multi-part job through a single request contract:
  - `mode`
  - `parts`
  - `sheet`
  - `params`
- The backend preserves the selected mode and per-part requested quantity.
- The result contract is centered on:
  - `mode`
  - `summary`
  - `parts`
- The result panel shows:
  - nesting mode used
  - explicit multi-part summary
  - requested / placed / remaining per part
- Job status and polling are aligned with the same multi-part model.
- Fill Sheet now continues placing copies until no enabled part fits anymore.
- Batch Quantity now continues placing requested parts until all requested parts are placed or no more fit.
- Multiple part types can be mixed on one sheet by the active heuristic.

## Root cause of the old under-placement behavior

- The old loop was effectively `first-fit`.
- It stopped on the first feasible candidate for the first feasible part.
- Candidate search was anchored to a narrow set of positions, so the engine could accept an early placement and miss better follow-up opportunities.
- This made Fill Sheet look like a single-placement workflow in cases where the sheet could clearly accept more copies.

## Current algorithm / heuristic

- Candidate parts are filtered by mode and remaining demand.
- For each candidate part and rotation, the engine searches multiple anchor positions across the sheet.
- Every feasible placement is scored instead of returning the first valid hit.
- The score now includes a small one-step lookahead bonus, so a candidate is preferred when it still leaves room for another productive placement afterward.
- Scoring prefers:
  - larger productive placements
  - compact placements near existing geometry / borders
  - preserving room for another feasible part type when possible
  - higher outstanding requested area in `batch_quantity`
- The engine then chooses the best next placement globally and repeats.

This is still greedy, not globally optimal, but it is now production-sensible for:

- repeated single-part fill
- mixed-part fill
- batch quantity partial-fit reporting

## Contract status

Primary request contract:

```json
{
  "mode": "batch_quantity",
  "parts": [
    {
      "part_id": "part-a",
      "filename": "part-a.dxf",
      "quantity": 10,
      "enabled": true,
      "fill_only": false
    }
  ],
  "sheet": {
    "sheet_id": "sheet-1",
    "width": 100,
    "height": 100,
    "quantity": 1,
    "units": "mm"
  }
}
```

Primary response contract:

```json
{
  "mode": "batch_quantity",
  "summary": {
    "total_parts": 3
  },
  "parts": [
    {
      "part_id": "part-a",
      "filename": "part-a.dxf",
      "requested_quantity": 10,
      "placed_quantity": 1,
      "remaining_quantity": 9
    }
  ],
  "total_parts_placed": 1
}
```

## Legacy ambiguity reduced

- Frontend submission uses the new `sheet` + `parts` contract as the main path.
- Result rendering uses the new `summary` + `parts` contract as the main path.
- Legacy `part_summaries` result normalization has been removed from the active frontend path.
- Older notes that described optional-mode or legacy response behavior should be treated as superseded by this file and `README.md`.

## What is intentionally deferred

Algorithm optimization is intentionally deferred to the next iteration. That includes:

- Maximize fill heuristics
- Batch packing optimality
- Complex placement strategy
- Smarter search and candidate ranking
- Better global yield optimization

## Temporary execution behavior

- The algorithm is greedy, not globally optimal.
- There are still cases where a more advanced solver could achieve better yield.
- The current requirement is correct production intent and correct metrics, not best-possible packing quality.

## Test coverage expected in this stage

Frontend:

- mode selector renders and switches
- part list renders multiple uploaded files
- quantity inputs appear in batch mode
- validation errors work
- result panel shows per-part counts
- fill-sheet submit flow uses the new request contract
- batch-quantity submit flow uses per-part quantities in the new request contract

Backend and integration:

- new multi-part request model is accepted
- mode field is preserved
- per-part requested quantity is preserved
- per-part summary fields are returned
- fill-sheet multi-part job succeeds
- batch-quantity multi-part job succeeds
- mixed Fill Sheet keeps placing until no enabled part fits anymore
- mixed Batch Quantity partial-fit reports remaining counts per part
- per-part area contribution is returned for mixed jobs
- single-part Fill Sheet places repeated copies
- single-part Batch Quantity exact-fit behaves correctly
- partial-fit Batch Quantity reports `remaining_quantity`

## Local URLs

- Backend URL: `http://localhost:8000`
- Frontend URL: `http://localhost:5173`
