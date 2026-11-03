"""Additional named SSF nodal fields, checked against TonyPlot 5.0.22.R.

Numeric identifiers are checked against the Atlas 5.30 SSF field header and
TonyPlot's named-quantity catalog. Metadata such as region indices and unknown
extension fields are deliberately omitted. Values are read without conversion.
"""

# Identifier: (Chinese interface name, English name, physical unit).
FIELDS = {
    69: ("组分 X", "Composition X", ""),
    70: ("组分 Y", "Composition Y", ""),
    71: ("施主浓度", "Donor concentration", "cm⁻³"),
    72: ("受主浓度", "Acceptor concentration", "cm⁻³"),
    100: ("电势", "Potential", "V"),
    101: ("电子迁移率", "Electron mobility", "cm²/(V·s)"),
    102: ("空穴迁移率", "Hole mobility", "cm²/(V·s)"),
    103: ("电场 · 幅值", "Electric field magnitude", "V/cm"),
    105: ("碰撞电离产生率", "Impact generation rate", "cm⁻³·s⁻¹"),
    106: ("电子浓度", "Electron concentration", "cm⁻³"),
    107: ("空穴浓度", "Hole concentration", "cm⁻³"),
    111: ("电子准费米能级（QFL）", "Electron quasi-Fermi level", "eV"),
    112: ("空穴准费米能级（QFL）", "Hole quasi-Fermi level", "eV"),
    118: ("复合率", "Recombination rate", "cm⁻³·s⁻¹"),
    120: ("电场 · X 分量", "Electric field X component", "V/cm"),
    121: ("电场 · Y 分量", "Electric field Y component", "V/cm"),
    127: ("电子速度", "Electron velocity", "cm/s"),
    128: ("空穴速度", "Hole velocity", "cm/s"),
    143: ("电子迁移率 · X 分量", "Electron mobility X component", "cm²/(V·s)"),
    144: ("电子迁移率 · Y 分量", "Electron mobility Y component", "cm²/(V·s)"),
    145: ("空穴迁移率 · X 分量", "Hole mobility X component", "cm²/(V·s)"),
    146: ("空穴迁移率 · Y 分量", "Hole mobility Y component", "cm²/(V·s)"),
    149: ("总掺杂浓度", "Total doping concentration", "cm⁻³"),
    419: ("电子 SRH 寿命参数 Tno", "Electron SRH Tno", "s"),
    420: ("空穴 SRH 寿命参数 Tno", "Hole SRH Tno", "s"),
    424: ("焦耳热功率密度", "Joule heat power density", "W/cm³"),
    425: ("总热功率密度", "Total heat power density", "W/cm³"),
    426: ("复合热功率密度", "Recombination heat power density", "W/cm³"),
    427: ("热导率", "Thermal conductivity", "W/(cm·K)"),
    428: ("比热容", "Specific heat capacity", "J/(g·K)"),
    429: ("珀尔帖–汤姆孙热功率密度", "Peltier-Thomson heat power density", "W/cm³"),
    616: ("SRH 复合率", "SRH recombination rate", "cm⁻³·s⁻¹"),
    617: ("俄歇复合率", "Auger recombination rate", "cm⁻³·s⁻¹"),
    806: ("已电离受主浓度", "Ionized acceptor concentration", "cm⁻³"),
    807: ("已电离施主浓度", "Ionized donor concentration", "cm⁻³"),
    822: ("电子电离系数", "Electron ionization coefficient", "cm⁻¹"),
    823: ("空穴电离系数", "Hole ionization coefficient", "cm⁻¹"),
}

DISPLAY_ORDER = (149, 71, 72, 807, 806, 100, 103, 120, 121, 106, 107,
                 111, 112, 127, 128, 101, 143, 144, 102, 145, 146,
                 424, 425, 426, 429, 427, 428, 118, 616, 617, 105,
                 822, 823, 419, 420, 69, 70)
