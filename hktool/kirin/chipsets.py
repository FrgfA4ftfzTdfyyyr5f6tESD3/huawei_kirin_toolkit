"""
Comprehensive database of HiSilicon Kirin SoCs, memory addresses, and stage loader configs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class LoaderStage:
    name: str
    address: int
    send_tail_frame: bool = False
    is_required: bool = True


@dataclass
class KirinChipsetProfile:
    id: str
    display_name: str
    stages: List[LoaderStage]
    description: str


# Complete Kirin SoC Profiles with hardware injection addresses
KIRIN_PROFILES: Dict[str, KirinChipsetProfile] = {
    "hisi620": KirinChipsetProfile(
        id="hisi620",
        display_name="Kirin 620 (Hi6220)",
        stages=[
            LoaderStage("xloader", 0xF9800800, False),
            LoaderStage("fastboot", 0x06800000, False),
        ],
        description="Honor 4X, Honor 4C, P8 Lite (2015)"
    ),
    "hisi620c": KirinChipsetProfile(
        id="hisi620c",
        display_name="Kirin 620C (Hi6220 Rev C)",
        stages=[
            LoaderStage("xloader", 0xF9800800, False),
            LoaderStage("fastboot", 0x06800000, False),
        ],
        description="Honor 4X/4C variant"
    ),
    "hisi65x_a": KirinChipsetProfile(
        id="hisi65x_a",
        display_name="Kirin 650/655/658/659 Rev A",
        stages=[
            LoaderStage("xloader", 0x00020000, False),
            LoaderStage("fastboot", 0x10000000, False),
        ],
        description="Honor 7X, Honor 9 Lite, P20 Lite, P10 Lite, Mate 10 Lite, Y9 2019"
    ),
    "hisi65x_b": KirinChipsetProfile(
        id="hisi65x_b",
        display_name="Kirin 650/655/658/659 Rev B",
        stages=[
            LoaderStage("xloader", 0x00020000, False),
            LoaderStage("fastboot", 0x10000000, False),
        ],
        description="Honor 8X Max, Honor 9N, Nova 3e"
    ),
    "hisi710": KirinChipsetProfile(
        id="hisi710",
        display_name="Kirin 710 / 710F (Hi6260)",
        stages=[
            LoaderStage("null", 0x00022000, False),
            LoaderStage("xloader", 0x00022000, True),
            LoaderStage("uce", 0x6000D000, False),
            LoaderStage("fastboot", 0x1C000000, False),
        ],
        description="Honor 8X, Honor 10 Lite, P30 Lite, Y9 Prime 2019, Mate 20 Lite, Nova 4e"
    ),
    "hisi710a": KirinChipsetProfile(
        id="hisi710a",
        display_name="Kirin 710A (SMIC 14nm)",
        stages=[
            LoaderStage("null", 0x00022000, False),
            LoaderStage("xloader", 0x00022000, True),
            LoaderStage("uce", 0x6000D000, False),
            LoaderStage("fastboot", 0x1C000000, False),
        ],
        description="Honor Play 4T, P smart 2021, Nova Y70, MatePad T10s"
    ),
    "hisi810": KirinChipsetProfile(
        id="hisi810",
        display_name="Kirin 810 (Hi6280)",
        stages=[
            LoaderStage("null", 0x00022000, False),
            LoaderStage("xloader", 0x00022000, True),
            LoaderStage("uce", 0x60000000, False),
            LoaderStage("fastboot", 0x1C000000, False),
        ],
        description="Honor 9X (Global/China), Honor 20S, Nova 5, Nova 5i Pro, P40 Lite"
    ),
    "hisi820": KirinChipsetProfile(
        id="hisi820",
        display_name="Kirin 820 5G",
        stages=[
            LoaderStage("null", 0x00022000, False),
            LoaderStage("xloader", 0x00022000, True),
            LoaderStage("uce", 0x60000000, False),
            LoaderStage("fastboot", 0x1A400000, False),
            LoaderStage("bl2", 0x1E400000, False),
        ],
        description="Honor 30S, Honor X10, Nova 7 SE"
    ),
    "hisi925": KirinChipsetProfile(
        id="hisi925",
        display_name="Kirin 920 / 925 / 928",
        stages=[
            LoaderStage("xloader", 0x00020000, False),
            LoaderStage("fastboot", 0x10000000, False),
        ],
        description="Honor 6, Honor 6 Plus, Mate 7"
    ),
    "hisi935": KirinChipsetProfile(
        id="hisi935",
        display_name="Kirin 930 / 935",
        stages=[
            LoaderStage("xloader", 0x00020000, False),
            LoaderStage("fastboot", 0x10000000, False),
        ],
        description="P8, P8 Max, Honor 7, Mate S"
    ),
    "hisi950": KirinChipsetProfile(
        id="hisi950",
        display_name="Kirin 950 (Hi3650)",
        stages=[
            LoaderStage("xloader", 0x00020000, False),
            LoaderStage("fastboot", 0x10000000, False),
        ],
        description="Mate 8, Honor 8, Honor Note 8"
    ),
    "hisi955": KirinChipsetProfile(
        id="hisi955",
        display_name="Kirin 955 (Hi3650+)",
        stages=[
            LoaderStage("xloader", 0x00020000, False),
            LoaderStage("fastboot", 0x10000000, False),
        ],
        description="P9, P9 Plus, Honor V8"
    ),
    "hisi960": KirinChipsetProfile(
        id="hisi960",
        display_name="Kirin 960 (Hi3660)",
        stages=[
            LoaderStage("xloader", 0x00020000, False),
            LoaderStage("uce", 0x6A908000, False),
            LoaderStage("fastboot", 0x1AC00000, False),
        ],
        description="Mate 9, Mate 9 Pro, P10, P10 Plus, Honor 9, Honor 8 Pro, Nova 2s"
    ),
    "hisi970": KirinChipsetProfile(
        id="hisi970",
        display_name="Kirin 970 (Hi3670 NPU)",
        stages=[
            LoaderStage("null", 0x00022000, False),
            LoaderStage("xloader", 0x00022000, True),
            LoaderStage("uce", 0x60049000, False),
            LoaderStage("fastboot", 0x16800000, False),
        ],
        description="Mate 10, Mate 10 Pro, P20, P20 Pro, Honor 10, Honor View 10, Honor Play, Nova 3"
    ),
    "hisi980": KirinChipsetProfile(
        id="hisi980",
        display_name="Kirin 980 (Hi3680 7nm)",
        stages=[
            LoaderStage("null", 0x00022000, False),
            LoaderStage("xloader", 0x00022000, True),
            LoaderStage("uce", 0x60049000, False),
            LoaderStage("fastboot", 0x1A400000, False),
        ],
        description="Mate 20, Mate 20 Pro, Mate 20 X, P30, P30 Pro, Honor 20, Honor 20 Pro, Honor View 20, Nova 5T"
    ),
    "hisi985": KirinChipsetProfile(
        id="hisi985",
        display_name="Kirin 985 5G",
        stages=[
            LoaderStage("null", 0x00022000, False),
            LoaderStage("xloader", 0x00022000, True),
            LoaderStage("uce", 0x60000000, False),
            LoaderStage("fastboot", 0x1A400000, False),
            LoaderStage("bl2", 0x1E400000, False),
        ],
        description="Honor 30, Nova 7, Nova 7 Pro"
    ),
    "hisi990": KirinChipsetProfile(
        id="hisi990",
        display_name="Kirin 990 4G / 5G (Hi3690)",
        stages=[
            LoaderStage("null", 0x00022000, False),
            LoaderStage("xloader", 0x00022000, True),
            LoaderStage("uce", 0x60000000, False),
            LoaderStage("fastboot", 0x1A400000, False),
            LoaderStage("bl2", 0x1E400000, False),
        ],
        description="Mate 30, Mate 30 Pro, P40, P40 Pro, P40 Pro+, Honor 30 Pro+, Nova 6 5G, MatePad Pro"
    ),
    "hisik3v2": KirinChipsetProfile(
        id="hisik3v2",
        display_name="K3V2 (Hi3620)",
        stages=[
            LoaderStage("usbloader", 0xF8000000, False),
        ],
        description="Ascend P6, Ascend Mate 1, Ascend D2"
    )
}
