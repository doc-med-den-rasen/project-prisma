"""PRISMA – gezielter Leistungscheck."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from targeted_check import run_targeted_check


APP_DIR = Path(__file__).resolve().parent
RULES_PATH = APP_DIR / "data" / "lep_rules.json"
ALIASES_PATH = APP_DIR / "data" / "lep_aliases.json"


@st.cache_data(show_spinner=False)
def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_match_table(result) -> None:
    rows = [
        {
            "Eingabe": item.service.title,
            "Zyklus": item.service.cycle,
            "Status": item.service.status or "–",
            "Zuordnung": item.lep_title or "Nicht erkannt",
            "LEP-/Regel-ID": item.lep_id or "–",
            "Match": item.match_type,
        }
        for item in result.matches
    ]
    st.dataframe(rows, hide_index=True, width="stretch")


st.set_page_config(
    page_title="PRISMA – Leistungscheck",
    page_icon="🔎",
    layout="wide",
)

st.title("PRISMA – gezielter Leistungscheck")
st.write(
    "Füge nur die Leistungen ein, die du im aktuellen Audit miteinander "
    "abgleichen möchtest. PRISMA prüft ausschließlich bestätigte Beziehungen "
    "zwischen diesen Einträgen."
)
st.info(
    "Keine klinische Bewertung: PRISMA beurteilt weder die medizinische "
    "Notwendigkeit noch den vollständigen Pflegeplan und ergänzt keine "
    "fehlenden Leistungen automatisch."
)

with st.form("targeted-check"):
    raw_text = st.text_area(
        "Leistungen aus SAP einfügen",
        height=230,
        placeholder=(
            "In Rollstuhl mobilisieren PV_4XTGL4 Aktiv\n"
            "In das Bett mobilisieren PV_3XTGL5 Aktiv\n"
            "Beim Gehen begleiten P_EINMAL Aktiv\n"
            "An Bettrand mobilisieren PV_3XTGL2 Aktiv"
        ),
        help=(
            "Eine Leistung pro Zeile. Zyklus und Status dürfen mitkopiert "
            "werden; reine Leistungstitel funktionieren ebenfalls."
        ),
    )
    submitted = st.form_submit_button(
        "Leistungen prüfen",
        type="primary",
        use_container_width=True,
    )

if submitted:
    if not raw_text.strip():
        st.warning("Bitte füge mindestens eine Leistung ein.")
        st.stop()

    result = run_targeted_check(
        raw_text=raw_text,
        rule_data=load_json(RULES_PATH),
        alias_data=load_json(ALIASES_PATH),
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aktive Eingaben", result.active_count)
    c2.metric("Exakt erkannt", len(result.matched))
    c3.metric("Regelbeziehungen", len(result.included) + len(result.excluded))
    c4.metric("Nicht erkannt", len(result.unmatched))

    st.subheader("Erkannte Eingaben")
    render_match_table(result)

    if result.inactive:
        inactive_titles = ", ".join(item.title for item in result.inactive)
        st.caption(
            f"Nicht ausgewertet, da nicht aktiv: {inactive_titles}"
        )

    if result.included:
        st.subheader("Bereits eingeschlossene Leistungen")
        for finding in result.included:
            st.warning(
                f"**{finding.related_title}** ist laut bestätigter Regel bereits "
                f"in **{finding.parent_title}** eingeschlossen. Die separate "
                "Planung kann entfallen, sofern sie nicht aus einem anderen "
                "fachlichen Grund benötigt wird."
            )
            st.caption(
                f"Regel: {finding.parent_id} → enthält {finding.related_id}"
            )

    if result.excluded:
        st.subheader("Nicht eingeschlossen – separat prüfen")
        for finding in result.excluded:
            st.info(
                f"**{finding.related_title}** ist ausdrücklich nicht in "
                f"**{finding.parent_title}** enthalten. Beide eingefügten "
                "Leistungen müssen deshalb fachlich getrennt betrachtet werden."
            )
            st.caption(
                f"Regel: {finding.parent_id} → enthält nicht {finding.related_id}"
            )

    if result.duplicates:
        st.subheader("Mehrfach eingefügte Leistungen")
        for items in result.duplicates.values():
            cycles = ", ".join(
                item.service.cycle or "ohne Zyklus" for item in items
            )
            st.info(
                f"**{items[0].lep_title}** wurde {len(items)}-mal eingefügt "
                f"({cycles}). PRISMA löscht Mehrfachplanungen nicht automatisch."
            )

    if result.without_relation:
        st.subheader("Erkannt, aber ohne Regelbefund")
        st.write(
            "Für diese eingefügten Leistungen ist untereinander keine bestätigte "
            "Ein- oder Ausschlussbeziehung hinterlegt:"
        )
        st.write(
            ", ".join(item.lep_title or item.service.title for item in result.without_relation)
        )

    if result.unmatched:
        st.subheader("Keine exakte Zuordnung")
        st.warning(
            "Diese Zeilen bleiben bewusst ungeklärt. Es wird kein ähnlicher "
            "Leistungstitel als Ersatz angenommen."
        )
        st.dataframe(
            [
                {
                    "Zeile": item.service.line_number,
                    "Eingabe": item.service.title,
                    "Zyklus": item.service.cycle,
                }
                for item in result.unmatched
            ],
            hide_index=True,
            width="stretch",
        )

    if not result.included and not result.excluded:
        st.success(
            "Zwischen den exakt erkannten, eingefügten Leistungen wurde keine "
            "bestätigte Ein- oder Ausschlussbeziehung gefunden."
        )

