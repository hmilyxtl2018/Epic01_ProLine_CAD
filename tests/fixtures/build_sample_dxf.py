"""Generate a tiny synthetic DXF for end-to-end ParseAgent demo / tests.

Writes to `tests/fixtures/cad/sample_factory.dxf`.

Layers/blocks intentionally include both **gold** taxonomy hits ("conveyor")
and unknown terms ("roller belt assembly") so the worker exercises the
matched_terms + quarantine_terms split.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "cad" / "sample_factory.dxf"


def build() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4  # mm
    msp = doc.modelspace()

    # Layers: one gold-taxonomy hit ("conveyor"), one quarantine candidate.
    doc.layers.add("CONVEYOR", color=1)
    doc.layers.add("Roller Belt Assembly", color=2)
    doc.layers.add("WALL", color=7)

    # Geometry on each layer so bounding box has data.
    msp.add_lwpolyline(
        [(0, 0), (10000, 0), (10000, 5000), (0, 5000), (0, 0)],
        dxfattribs={"layer": "WALL"},
    )
    msp.add_line((500, 500), (9500, 500), dxfattribs={"layer": "CONVEYOR"})
    msp.add_line((500, 1500), (9500, 1500), dxfattribs={"layer": "CONVEYOR"})
    msp.add_circle((2000, 3000), 200, dxfattribs={"layer": "Roller Belt Assembly"})
    msp.add_circle((4000, 3000), 200, dxfattribs={"layer": "Roller Belt Assembly"})
    msp.add_circle((6000, 3000), 200, dxfattribs={"layer": "Roller Belt Assembly"})
    msp.add_text(
        "Machining Workshop",
        dxfattribs={"layer": "WALL", "height": 200, "insert": (200, 4500)},
    )

    # A custom block definition (counted in block_definition_count).
    blk = doc.blocks.new(name="LiftingPoint")
    blk.add_circle((0, 0), 100)
    blk.add_line((-150, 0), (150, 0))

    # Insert the block twice so the modelspace references it.
    msp.add_blockref("LiftingPoint", (1500, 4000))
    msp.add_blockref("LiftingPoint", (8500, 4000))

    doc.saveas(str(OUT))
    return OUT


if __name__ == "__main__":
    p = build()
    print(f"wrote {p} ({p.stat().st_size} bytes)")
