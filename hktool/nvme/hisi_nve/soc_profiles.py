"""
Hardware range and SoC profiles for HiSilicon Kirin processors.
Contains metadata, key hashing requirements, and known NV items.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict

@dataclass
class SocProfile:
    soc_name: str
    display_name: str
    nve_entry_count: int
    nve_hashed_key: bool   # Whether USRKEY expects a SHA-256 hash
    known_entries: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.display_name

# Known profiles from hisi-nve mapping tables & Huawei kernel trees
SOC_PROFILES: Dict[str, SocProfile] = {
    "hi6210sft": SocProfile(
        soc_name="hi6210sft",
        display_name="Kirin 620 (Hi6210)",
        nve_entry_count=330,
        nve_hashed_key=False,
    ),
    "hi6250": SocProfile(
        soc_name="hi6250",
        display_name="Kirin 650 / 655 / 658 / 659 (Hi6250)",
        nve_entry_count=379,
        nve_hashed_key=True,
    ),
    "hi3650": SocProfile(
        soc_name="hi3650",
        display_name="Kirin 950 / 955 (Hi3650)",
        nve_entry_count=352,
        nve_hashed_key=True,
    ),
    "hi3660": SocProfile(
        soc_name="hi3660",
        display_name="Kirin 960 (Hi3660)",
        nve_entry_count=376,
        nve_hashed_key=True,
    ),
    "kirin710": SocProfile(
        soc_name="kirin710",
        display_name="Kirin 710 / 710F / 710A (Hi6260 / Hi6230)",
        nve_entry_count=416,
        nve_hashed_key=True,
    ),
    "kirin970": SocProfile(
        soc_name="kirin970",
        display_name="Kirin 970 (Hi3670)",
        nve_entry_count=393,
        nve_hashed_key=True,
    ),
    "kirin980": SocProfile(
        soc_name="kirin980",
        display_name="Kirin 980 (Hi3680)",
        nve_entry_count=415,
        nve_hashed_key=True,
    ),
    "kirin990": SocProfile(
        soc_name="kirin990",
        display_name="Kirin 990 4G / 5G / Kirin 990E (Hi3690)",
        nve_entry_count=701,
        nve_hashed_key=True,
    ),
    "kirin810": SocProfile(
        soc_name="kirin810",
        display_name="Kirin 810 / 820",
        nve_entry_count=450,
        nve_hashed_key=True,
    ),
    "kirin9000": SocProfile(
        soc_name="kirin9000",
        display_name="Kirin 9000 / 9000E / 9000S",
        nve_entry_count=800,
        nve_hashed_key=True,
    )
}

def detect_soc_from_entries(entries_by_name: dict[str, str], total_items: int) -> Optional[SocProfile]:
    """
    Intelligently detect SoC profile from image contents, item count, and flags.
    """
    # Check WVLOCK for hashed key flag
    wvlock_val = entries_by_name.get("WVLOCK", "")
    is_hashed = "UUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUU" in wvlock_val or "USRKEY" in entries_by_name
    
    # Check SWVERSI or other hints
    swversi = entries_by_name.get("SWVERSI", "")
    
    # Try exact count match
    for profile in SOC_PROFILES.values():
        if abs(profile.nve_entry_count - total_items) <= 15:
            return profile
            
    # Default fallback
    if is_hashed:
        return SOC_PROFILES["kirin710"]
    return SOC_PROFILES["hi6210sft"]
