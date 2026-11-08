"""Club shirt colours for the pitch view (body, sleeves, collar trim), keyed by FPL short name.

Clubs not listed (e.g. after promotion) fall back to a neutral kit, so a new season never breaks
the page; add them here when they arrive.
"""

from app.api.schemas import Kit

KITS: dict[str, tuple[str, str, str]] = {
    "ARS": ("#DB0007", "#FFFFFF", "#FFFFFF"),
    "AVL": ("#670E36", "#95BFE5", "#95BFE5"),
    "BOU": ("#DA291C", "#111111", "#111111"),
    "BRE": ("#E30613", "#FFFFFF", "#FFFFFF"),
    "BHA": ("#0057B8", "#FFFFFF", "#FFFFFF"),
    "BUR": ("#6C1D45", "#99D6EA", "#99D6EA"),
    "CHE": ("#034694", "#034694", "#FFFFFF"),
    "COV": ("#77B5E3", "#77B5E3", "#FFFFFF"),
    "CRY": ("#1B458F", "#C4122E", "#C4122E"),
    "EVE": ("#003399", "#003399", "#FFFFFF"),
    "FUL": ("#FFFFFF", "#FFFFFF", "#111111"),
    "HUL": ("#F18A01", "#111111", "#111111"),
    "IPS": ("#3A64A3", "#3A64A3", "#FFFFFF"),
    "LEE": ("#FFFFFF", "#FFFFFF", "#1D428A"),
    "LEI": ("#003090", "#003090", "#FDBE11"),
    "LIV": ("#C8102E", "#C8102E", "#FFFFFF"),
    "MCI": ("#6CABDD", "#6CABDD", "#FFFFFF"),
    "MUN": ("#DA291C", "#DA291C", "#FFFFFF"),
    "NEW": ("#241F20", "#FFFFFF", "#FFFFFF"),
    "NFO": ("#DD0000", "#DD0000", "#FFFFFF"),
    "SOU": ("#D71920", "#FFFFFF", "#FFFFFF"),
    "SUN": ("#EB172B", "#FFFFFF", "#FFFFFF"),
    "TOT": ("#FFFFFF", "#FFFFFF", "#132257"),
    "WHU": ("#7A263A", "#1BB1E7", "#1BB1E7"),
    "WOL": ("#FDB913", "#FDB913", "#231F20"),
}
FALLBACK = ("#94A0AF", "#94A0AF", "#FFFFFF")
GOALKEEPER = Kit(body="#F5C518", sleeve="#F5C518", trim="#111111")


def kit_for(short_name: str) -> Kit:
    body, sleeve, trim = KITS.get(short_name, FALLBACK)
    return Kit(body=body, sleeve=sleeve, trim=trim)
