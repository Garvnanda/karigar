"""Hardware pack (roadmap slot): enclosures and brackets solved to fit + material grams.

Plan: CadQuery/build123d builder; spec = board footprint, ports, wall, bosses;
constraint = PLA grams or print time; DFM = min wall 1.2 mm, overhangs, screw boss
sizes; outputs = STEP + STL + bill of materials. Same engine, new builder.
"""
from karigar.core.registry import DomainPack, register


class HardwarePack(DomainPack):
    name = "hardware"
    title = "Hardware Lab"
    available = False
    agents = {"brief": "Sakhi", "design": "Naqqash", "build": "Mistri", "price": "Jauhari",
              "render": "Chitrakar"}


PACK = register(HardwarePack())
