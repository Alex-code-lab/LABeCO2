# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Utilitaires communs pour les graphiques de transport des consommables.

import warnings

from ui.charts.history_utils import iter_history_data
from ui.display_utils import clean_text


ORIGIN_COLORS = {
    "Inconnue (défaut)": "#64748b",
    "France": "#16a34a",
    "Europe": "#2563eb",
    "USA": "#f97316",
    "Asie": "#dc2626",
    "Afrique": "#9333ea",
}

COLOR_MATERIAL = "#73c2fb"
COLOR_TRANSPORT = "#f59e0b"
COLOR_ERR = "#374151"
SUMMARY_MAX_LINE_CHARS = 92


def origin_color(origin):
    origin = clean_text(origin)
    origin_lower = origin.casefold()
    if "express avion" in origin_lower:
        return "#b91c1c"
    for key, color in ORIGIN_COLORS.items():
        if origin == key or origin.startswith(f"{key} "):
            return color
    return "#0f766e"


def short_origin_label(origin):
    return clean_text(origin).replace(" (", "\n(")


def is_europe_baseline(origin):
    origin = clean_text(origin)
    return origin in {"France", "Europe"}


def item_label(data, max_len=36):
    code = clean_text(data.get("code_nacres"))
    consommable = clean_text(data.get("consommable"))
    name = clean_text(data.get("name"))
    label = consommable if consommable and consommable != "NA" else name
    if not label:
        label = clean_text(data.get("subcategory")) or code or "Calcul"

    prefix = code[:4] if code and code != "NA" else ""
    if prefix and not label.startswith(prefix):
        label = f"{prefix} - {label}"
    if len(label) > max_len:
        label = f"{label[:max_len - 1]}..."
    return label


def iter_transport_records(history_widget, data_manager):
    for data in iter_history_data(history_widget):
        emission_mass = float(data.get("emission_mass", 0.0) or 0.0)
        total_mass = float(data.get("total_mass", 0.0) or 0.0)
        emission_error = float(data.get("emission_mass_error", 0.0) or 0.0)

        if emission_mass <= 0 or total_mass <= 0:
            continue

        origin = data.get("origine", data_manager.TRANSPORT_DEFAULT) or data_manager.TRANSPORT_DEFAULT
        transport_factor, transport_uncertainty = data_manager.get_transport_factor(origin)
        transport_emissions = total_mass * transport_factor
        transport_error = transport_emissions * transport_uncertainty
        material_emissions = max(emission_mass - transport_emissions, 0.0)

        yield {
            "data": data,
            "label": item_label(data),
            "origin": origin,
            "code_nacres": clean_text(data.get("code_nacres"))[:4],
            "mass_kg": total_mass,
            "material_emissions": material_emissions,
            "transport_emissions": transport_emissions,
            "total_emissions": material_emissions + transport_emissions,
            "emission_error": emission_error,
            "transport_error": transport_error,
            "transport_factor": transport_factor,
            "transport_uncertainty": transport_uncertainty,
        }


def summarize_transport(records):
    transport_total = sum(r["transport_emissions"] for r in records)
    mass_total = sum(r["total_emissions"] for r in records)
    by_origin = {}
    for record in records:
        by_origin[record["origin"]] = by_origin.get(record["origin"], 0.0) + record["transport_emissions"]
    main_origin = max(by_origin, key=by_origin.get) if by_origin else "NA"
    return {
        "transport_total": transport_total,
        "mass_total": mass_total,
        "main_origin": main_origin,
        "item_count": len(records),
    }


def add_transport_summary(figure, summary, gain=None):
    transport_total = summary["transport_total"]
    mass_total = summary["mass_total"]
    pct = (transport_total / mass_total * 100.0) if mass_total > 0 else 0.0
    parts = [
        f"Transport total : {transport_total:.2f} kg CO₂e",
        f"Part du transport : {pct:.1f} %",
        f"Provenance principale : {summary['main_origin']}",
        f"{summary['item_count']} ligne(s) massiques",
    ]
    if gain is not None:
        label = "Économie scénario" if gain >= 0 else "Hausse scénario"
        parts.append(f"{label} : {abs(gain):.2f} kg CO₂e")

    lines = []
    current_line = ""
    for part in parts:
        candidate = part if not current_line else f"{current_line} | {part}"
        if current_line and len(candidate) > SUMMARY_MAX_LINE_CHARS:
            lines.append(current_line)
            current_line = part
        else:
            current_line = candidate
    if current_line:
        lines.append(current_line)

    figure.text(
        0.5,
        0.965,
        "\n".join(lines),
        ha="center",
        va="top",
        fontsize=8.5 if len(lines) > 1 else 9,
        color="#0f172a",
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "#f8fafc",
            "edgecolor": "#cbd5e1",
            "linewidth": 0.8,
        },
    )


def set_vertical_text_room(ax, heights, errors=None, room_ratio=0.42):
    """
    Réserve de l'espace vertical pour les annotations placées au-dessus
    des barres. Matplotlib n'étend pas les axes pour les textes.
    """
    peak = 1.0
    if errors is None:
        for height in heights:
            peak = max(peak, float(height))
    else:
        for height, error in zip(heights, errors):
            peak = max(peak, float(height) + float(error))
    ax.set_ylim(0, peak * (1.0 + room_ratio))
    return peak


def apply_transport_tight_layout(figure, *args, **kwargs):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="The figure layout has changed to tight")
        warnings.filterwarnings("ignore", message="Tight layout not applied.*")
        figure.tight_layout(*args, **kwargs)


def scenario_europe(records, data_manager):
    europe_factor, _ = data_manager.get_transport_factor("Europe")
    current_total = sum(r["transport_emissions"] for r in records)
    scenario_total = 0.0
    gains_by_origin = {}

    for record in records:
        if is_europe_baseline(record["origin"]):
            scenario_transport = record["transport_emissions"]
        else:
            scenario_transport = record["mass_kg"] * europe_factor
        gain = record["transport_emissions"] - scenario_transport
        scenario_total += scenario_transport
        gains_by_origin[record["origin"]] = gains_by_origin.get(record["origin"], 0.0) + gain

    return {
        "current_total": current_total,
        "scenario_total": scenario_total,
        "gain": current_total - scenario_total,
        "gains_by_origin": gains_by_origin,
    }
