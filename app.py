import base64
import hashlib
import io
import os
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from agent.graph import run_data_cleaning_agent
from core.audit import profile_dataset, validate_post_cleaning
from core.cleaning_engine import CleaningPlanError, execute_cleaning_plan
from core.csv_loader import read_tabular_file
from ui.styles import CSS


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="DataCleaner Agent",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")
API_KEY = os.getenv("GROQ_API_KEY", "")

st.markdown(CSS, unsafe_allow_html=True)


# ============================================================
# BACKGROUND (optionnel) : placez votre visuel dans assets/background.png
# ============================================================

@st.cache_resource(show_spinner=False)
def background_css() -> str:
    """Use assets/background.(png|jpg|jpeg|webp) as app background if present."""
    mime_by_suffix = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    for name in ("background.png", "background.jpg", "background.jpeg", "background.webp"):
        path = BASE_DIR / "assets" / name
        if path.exists():
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            mime = mime_by_suffix[path.suffix.lower()]
            return f"""
            <style>
            .stApp {{
                background-image:
                    linear-gradient(rgba(255,255,255,.30), rgba(255,255,255,.30)),
                    url("data:{mime};base64,{encoded}") !important;
                background-size: cover !important;
                background-position: center top !important;
                background-attachment: fixed !important;
                background-repeat: no-repeat !important;
            }}
            </style>
            """
    return ""


_bg = background_css()
if _bg:
    st.markdown(_bg, unsafe_allow_html=True)


# ============================================================
# HELPERS
# ============================================================

def robot_svg() -> str:
    """Robot holographique qui nettoie une pile de bases de données avec un balai."""

    binary = "".join(
        f'<text x="{x}" y="0" class="bin b{i % 3}">'
        + "".join(f'<tspan x="{x}" dy="16">{d}</tspan>' for d in "1011001010011010")
        + "</text>"
        for i, x in enumerate([8, 282, 300, 314])
    )

    cx, w = 62, 36

    def unit(y: int, cap: bool = False) -> str:
        parts = [
            f'<rect x="{cx - w}" y="{y}" width="{w * 2}" height="26" fill="#3F5C8A"/>',
            f'<ellipse cx="{cx}" cy="{y + 26}" rx="{w}" ry="9" fill="#3F5C8A"/>',
            f'<path d="M{cx - w} {y + 26} A{w} 9 0 0 0 {cx + w} {y + 26}" '
            f'fill="none" stroke="#5AA6CE" stroke-width="3.5"/>',
        ]
        if cap:
            parts.append(f'<ellipse cx="{cx}" cy="{y}" rx="{w}" ry="9" fill="#5AA6CE"/>')
        for dy, color, delay in ((6, "#5BD6A0", 0), (13, "#FF6B6B", .4), (20, "#FFC857", .8)):
            parts.append(
                f'<circle class="ld" style="animation-delay:{delay}s" '
                f'cx="{cx - 27}" cy="{y + dy}" r="2.2" fill="{color}"/>'
            )
        return "".join(parts)

    def star(x: int, y: int, delay: float) -> str:
        return (
            f'<g transform="translate({x},{y})"><path class="tw" style="animation-delay:{delay}s" '
            'd="M0 -8 L2.4 -2.4 L8 0 L2.4 2.4 L0 8 L-2.4 2.4 L-8 0 L-2.4 -2.4 Z" fill="#F3E2C5"/></g>'
        )

    def dust(x: int, y: int, r: float, delay: float) -> str:
        return (
            f'<circle class="dust" style="animation-delay:{delay}s" '
            f'cx="{x}" cy="{y}" r="{r}" fill="#CFE4FA"/>'
        )

    database = (
        f'<ellipse cx="{cx}" cy="286" rx="46" ry="6" fill="#02122B" opacity=".25"/>'
        + unit(248) + unit(222) + unit(196, cap=True)
        + star(30, 198, 0) + star(98, 188, .6) + star(62, 172, 1.2) + star(24, 236, 1.7)
    )
    dusts = dust(82, 292, 3, 0) + dust(102, 294, 2.4, .35) + dust(122, 290, 3, .7) + dust(70, 294, 2, 1)

    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 310">
<defs>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="3.2" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <radialGradient id="aura" cx="50%" cy="48%" r="50%">
    <stop offset="0" stop-color="#5CD2FF" stop-opacity=".32"/>
    <stop offset="1" stop-color="#5CD2FF" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="head" cx="40%" cy="30%" r="80%">
    <stop offset="0" stop-color="#1C5FB5"/>
    <stop offset="1" stop-color="#06285A"/>
  </radialGradient>
  <linearGradient id="body" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#14529F"/>
    <stop offset="1" stop-color="#06285A"/>
  </linearGradient>
  <linearGradient id="flame" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#FFFFFF"/>
    <stop offset=".35" stop-color="#9BE6FF"/>
    <stop offset="1" stop-color="#2AA7E6" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="bristle" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#FFC857"/>
    <stop offset="1" stop-color="#E8902E"/>
  </linearGradient>
</defs>
<style>
  .float {animation: fl 3.2s ease-in-out infinite;}
  @keyframes fl {0%,100%{transform:translateY(0)} 50%{transform:translateY(-8px)}}
  .sweep {transform-origin:90px 168px; animation: sw 1.3s ease-in-out infinite;}
  @keyframes sw {0%,100%{transform:rotate(-9deg)} 50%{transform:rotate(11deg)}}
  .eye {transform-box:fill-box; transform-origin:center; animation: bl 4.5s infinite;}
  @keyframes bl {0%,92%,100%{transform:scaleY(1)} 95%{transform:scaleY(.08)}}
  .pulse {animation: pl 1.8s ease-in-out infinite;}
  .ld {animation: pl 2s ease-in-out infinite;}
  @keyframes pl {0%,100%{opacity:.45} 50%{opacity:1}}
  .flame {transform-box:fill-box; transform-origin:50% 0%; animation: fm .22s ease-in-out infinite alternate;}
  @keyframes fm {from{transform:scaleY(.85) scaleX(.95)} to{transform:scaleY(1.15) scaleX(1.05)}}
  .bin {font: 11px monospace; fill:#7DB2EA; opacity:.26;}
  .b0 {animation: bn 5s linear infinite;}
  .b1 {animation: bn 7s linear infinite;}
  .b2 {animation: bn 6s linear infinite;}
  @keyframes bn {from{transform:translateY(-40px)} to{transform:translateY(40px)}}
  .spark {animation: sp 1.6s ease-out infinite;}
  @keyframes sp {0%{transform:translateY(0); opacity:.9} 100%{transform:translateY(40px); opacity:0}}
  .tw {transform-box:fill-box; transform-origin:center; animation: twk 2s ease-in-out infinite;}
  @keyframes twk {0%,100%{transform:scale(.2); opacity:0} 50%{transform:scale(1); opacity:1}}
  .dust {transform-box:fill-box; transform-origin:center; animation: du 1.3s ease-out infinite;}
  @keyframes du {0%{transform:translateY(0) scale(1); opacity:.9} 100%{transform:translateY(-24px) scale(.3); opacity:0}}
  @media (prefers-reduced-motion: reduce) { * {animation:none !important;} }
</style>

__BIN__
<circle cx="190" cy="140" r="122" fill="url(#aura)"/>

__DB__

<g transform="translate(72,0)">
<g class="float">
  <!-- flame / thruster -->
  <path class="flame" d="M108 238 Q125 300 142 238 Z" fill="url(#flame)" filter="url(#glow)"/>
  <circle class="spark" cx="116" cy="262" r="2.2" fill="#BFF0FF"/>
  <circle class="spark" cx="134" cy="268" r="1.8" fill="#BFF0FF" style="animation-delay:.5s"/>
  <path d="M104 228 L146 228 L140 240 L110 240 Z" fill="#0B3C7A" stroke="#5CD2FF" stroke-width="2"/>

  <!-- antenna -->
  <line x1="125" y1="40" x2="125" y2="60" stroke="#5CD2FF" stroke-width="3" stroke-linecap="round"/>
  <circle class="pulse" cx="125" cy="34" r="7" fill="#BFF0FF" filter="url(#glow)"/>

  <!-- right arm (static) -->
  <line x1="160" y1="168" x2="180" y2="214" stroke="#5CD2FF" stroke-width="16" stroke-linecap="round" filter="url(#glow)"/>
  <line x1="160" y1="168" x2="180" y2="214" stroke="#0B3C7A" stroke-width="11" stroke-linecap="round"/>
  <circle cx="182" cy="220" r="10" fill="#0B3C7A" stroke="#5CD2FF" stroke-width="2.5"/>

  <!-- body -->
  <ellipse cx="125" cy="188" rx="42" ry="48" fill="url(#body)" stroke="#5CD2FF" stroke-width="2.5" filter="url(#glow)"/>
  <g fill="none" stroke="#5CD2FF" stroke-opacity=".55" stroke-width="1.2">
    <ellipse cx="125" cy="188" rx="19" ry="48"/>
    <ellipse cx="125" cy="188" rx="33" ry="48"/>
    <path d="M85 170 Q125 184 165 170"/>
    <path d="M83 190 Q125 204 167 190"/>
    <path d="M85 210 Q125 224 165 210"/>
  </g>
  <circle class="pulse" cx="125" cy="176" r="8" fill="#BFF0FF" filter="url(#glow)"/>

  <!-- head -->
  <circle cx="125" cy="104" r="50" fill="url(#head)" stroke="#5CD2FF" stroke-width="2.8" filter="url(#glow)"/>
  <g fill="none" stroke="#5CD2FF" stroke-opacity=".35" stroke-width="1.1">
    <ellipse cx="125" cy="104" rx="26" ry="50"/>
    <path d="M77 90 Q125 106 173 90"/>
    <path d="M77 120 Q125 136 173 120"/>
  </g>
  <rect x="85" y="84" width="80" height="42" rx="21" fill="#031A3A" stroke="#5CD2FF" stroke-width="2"/>
  <ellipse class="eye" cx="107" cy="103" rx="7.5" ry="9" fill="#BFF0FF" filter="url(#glow)"/>
  <ellipse class="eye" cx="143" cy="103" rx="7.5" ry="9" fill="#BFF0FF" filter="url(#glow)"/>
  <path d="M115 114 Q125 123 135 114" stroke="#5CD2FF" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <circle cx="72" cy="104" r="6" fill="#0B3C7A" stroke="#5CD2FF" stroke-width="2"/>
  <circle cx="178" cy="104" r="6" fill="#0B3C7A" stroke="#5CD2FF" stroke-width="2"/>

  <!-- left arm + broom (sweeping) -->
  <g class="sweep">
    <line x1="90" y1="168" x2="66" y2="208" stroke="#5CD2FF" stroke-width="16" stroke-linecap="round" filter="url(#glow)"/>
    <line x1="90" y1="168" x2="66" y2="208" stroke="#0B3C7A" stroke-width="11" stroke-linecap="round"/>
    <line x1="80" y1="188" x2="30" y2="264" stroke="#E2C48F" stroke-width="6" stroke-linecap="round"/>
    <path d="M25 260.7 L35 267.3 L29.1 294.6 L2.3 277 Z" fill="url(#bristle)"/>
    <g stroke="#B8651B" stroke-width="1.2" stroke-opacity=".7">
      <line x1="28" y1="266" x2="16" y2="285"/>
      <line x1="31" y1="268" x2="22" y2="290"/>
      <line x1="25" y1="263" x2="9" y2="280"/>
    </g>
    <line x1="24" y1="261" x2="36" y2="268.5" stroke="#8A5A2B" stroke-width="4" stroke-linecap="round"/>
    <circle cx="64" cy="212" r="10" fill="#0B3C7A" stroke="#5CD2FF" stroke-width="2.5"/>
  </g>
</g>
</g>

__DUST__
</svg>"""
    return svg.replace("__BIN__", binary).replace("__DB__", database).replace("__DUST__", dusts)


def robot_html() -> str:
    encoded = base64.b64encode(robot_svg().encode("utf-8")).decode("ascii")
    return (
        '<div class="hero-robot">'
        '<div class="robot-bubble">Je nettoie vos données ✨</div>'
        f'<img alt="" src="data:image/svg+xml;base64,{encoded}"/>'
        '</div>'
    )



def svg_img(svg: str, cls: str = "") -> str:
    """Inline an animated SVG as <img> (st.html strips raw <svg>, <img> data URIs are kept)."""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img class="{cls}" alt="" src="data:image/svg+xml;base64,{encoded}"/>'


_REDUCE = "@media (prefers-reduced-motion: reduce){*{animation:none !important;}}"


def waves_html() -> str:
    """Vagues animées (sable + bleu) au bas du hero."""
    def wave(base: int, amp: int, fill: str, cls: str) -> str:
        d = f"M0 {base} q200 {-amp} 400 0" + " t400 0" * 7 + " V120 H0 Z"
        return f'<g class="w {cls}"><path fill="{fill}" d="{d}"/></g>'

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 120" preserveAspectRatio="none">'
        "<style>.w{animation:wave linear infinite}.w1{animation-duration:16s}"
        ".w2{animation-duration:22s;animation-direction:reverse}.w3{animation-duration:30s}"
        "@keyframes wave{from{transform:translateX(0)}to{transform:translateX(-800px)}}"
        + _REDUCE + "</style>"
        + wave(70, 34, "rgba(255,255,255,.10)", "w3")
        + wave(84, 40, "rgba(125,178,234,.30)", "w2")
        + wave(96, 30, "rgba(243,226,197,.34)", "w1")
        + "</svg>"
    )
    return svg_img(svg, "hero-waves")


def check_icon() -> str:
    """Coche verte qui se dessine."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52">'
        "<style>.c,.k{fill:none;stroke:#2E9E6B;stroke-linecap:round;stroke-linejoin:round}"
        ".c{stroke-width:3;stroke-dasharray:146;stroke-dashoffset:146;animation:dr .8s ease forwards}"
        ".k{stroke-width:4.5;stroke-dasharray:40;stroke-dashoffset:40;animation:dr .5s .6s ease forwards}"
        "@keyframes dr{to{stroke-dashoffset:0}}" + _REDUCE + "</style>"
        '<circle class="c" cx="26" cy="26" r="23"/>'
        '<path class="k" d="M15 27 l8 8 l15 -17"/></svg>'
    )
    return svg_img(svg, "check-anim")


def feature_strip() -> str:
    """Trois cartes avec icônes SVG animées (remplissent la page d'import)."""
    search = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><style>'
        ".lens{animation:lz 2.4s ease-in-out infinite alternate}"
        "@keyframes lz{from{transform:translate(-5px,-3px)}to{transform:translate(5px,4px)}}"
        ".scan{animation:sc 1.1s ease-in-out infinite alternate}"
        "@keyframes sc{from{transform:translateY(-8px);opacity:.3}to{transform:translateY(8px);opacity:1}}"
        + _REDUCE + "</style>"
        '<rect x="6" y="8" width="30" height="6" rx="3" fill="#CFE4FA"/>'
        '<rect x="6" y="20" width="22" height="6" rx="3" fill="#CFE4FA"/>'
        '<rect x="6" y="32" width="26" height="6" rx="3" fill="#CFE4FA"/>'
        '<g class="lens"><circle cx="30" cy="30" r="14" fill="rgba(125,178,234,.20)" stroke="#1B5896" stroke-width="4"/>'
        '<line class="scan" x1="21" y1="30" x2="39" y2="30" stroke="#E2C48F" stroke-width="2.6" stroke-linecap="round"/>'
        '<line x1="40" y1="40" x2="54" y2="54" stroke="#1B5896" stroke-width="5.5" stroke-linecap="round"/></g></svg>'
    )
    ticks = "".join(
        f'<rect x="18" y="{y}" width="9" height="9" rx="2.5" fill="none" stroke="#5B94CB" stroke-width="2"/>'
        f'<line x1="32" y1="{y + 4.5}" x2="45" y2="{y + 4.5}" stroke="#CFE4FA" stroke-width="3.2" stroke-linecap="round"/>'
        f'<path class="t" style="animation-delay:{i * .55}s" d="M19.5 {y + 4.8} l2.8 2.8 l5.4 -6.6"/>'
        for i, y in enumerate((17, 29, 41))
    )
    review = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><style>'
        ".t{fill:none;stroke:#2E9E6B;stroke-width:2.8;stroke-linecap:round;stroke-linejoin:round;"
        "stroke-dasharray:14;stroke-dashoffset:14;animation:tk 3.4s ease-in-out infinite}"
        "@keyframes tk{0%,8%{stroke-dashoffset:14}25%,78%{stroke-dashoffset:0}92%,100%{stroke-dashoffset:14}}"
        + _REDUCE + "</style>"
        '<rect x="11" y="7" width="42" height="50" rx="8" fill="#fff" stroke="#1B5896" stroke-width="3.5"/>'
        + ticks + "</svg>"
    )
    shield = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><style>'
        ".sh{transform-box:fill-box;transform-origin:center;animation:sp 2.4s ease-in-out infinite}"
        "@keyframes sp{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}"
        ".ck{fill:none;stroke:#2E9E6B;stroke-width:4.6;stroke-linecap:round;stroke-linejoin:round;"
        "stroke-dasharray:32;stroke-dashoffset:32;animation:tk2 3s ease-in-out infinite}"
        "@keyframes tk2{0%,10%{stroke-dashoffset:32}35%,80%{stroke-dashoffset:0}95%,100%{stroke-dashoffset:32}}"
        + _REDUCE + "</style>"
        '<path class="sh" d="M32 6 L52 14 V30 C52 43 43 52 32 58 C21 52 12 43 12 30 V14 Z" '
        'fill="rgba(125,178,234,.22)" stroke="#1B5896" stroke-width="3.5" stroke-linejoin="round"/>'
        '<path class="ck" d="M22 31 l7 7 l13 -15"/></svg>'
    )

    cards = [
        (search, "Analyse complète", "Pandas inspecte toutes les lignes, pas un simple échantillon."),
        (review, "Validation humaine", "Vous cochez les actions avant toute modification."),
        (shield, "Exécution sûre", "Moteur à liste blanche : aucun code arbitraire exécuté."),
    ]
    items = "".join(
        f'<div class="feature-card">{svg_img(icon, "feature-icon")}'
        f'<div><div class="feature-title">{escape(title)}</div>'
        f'<div class="feature-text">{escape(text)}</div></div></div>'
        for icon, title, text in cards
    )
    return f'<div class="feature-strip">{items}</div>'


def html(content: str):
    st.html(content)


def section(kicker: str, title: str, subtitle: str):
    html(
        f"""
        <div class="section">
            <div class="section-kicker">{escape(kicker)}</div>
            <div class="section-title">{escape(title)}</div>
            <div class="section-sub">{escape(subtitle)}</div>
        </div>
        """
    )


def reset_analysis():
    st.session_state.agent_result = None
    st.session_state.plan = None
    st.session_state.selected_actions = []
    st.session_state.cleaned_df = None
    st.session_state.execution_log = None
    st.session_state.validation_report = None
    st.session_state.agent_error = None
    st.session_state.agent_run_id += 1


def install_dataset(uploaded_file):
    file_bytes = uploaded_file.getvalue()
    df, raw, metadata = read_tabular_file(file_bytes, uploaded_file.name)

    st.session_state.df = df.copy(deep=True)
    st.session_state.raw_df = raw.copy(deep=True)
    st.session_state.file_name = uploaded_file.name
    st.session_state.file_hash = hashlib.sha256(file_bytes).hexdigest()
    st.session_state.file_metadata = metadata
    st.session_state.replace_mode = False
    st.session_state.scroll_to_replace = False
    reset_analysis()


def operation_label(operation: str) -> str:
    return {
        "normalize_column_names": "Noms de colonnes",
        "drop_empty_rows": "Lignes vides",
        "drop_empty_columns": "Colonnes vides",
        "drop_duplicate_rows": "Doublons complets",
        "drop_duplicates_by_columns": "Doublons par identifiant",
        "replace_null_like": "Valeurs manquantes",
        "strip_whitespace": "Espaces superflus",
        "normalize_case": "Normalisation du texte",
        "replace_values": "Standardisation des valeurs",
        "to_numeric": "Conversion numérique",
        "to_datetime": "Conversion des dates",
        "set_negative_to_null": "Valeurs négatives",
        "no_change": "Validation manuelle",
    }.get(operation, operation)


def format_dataframe_for_display(dataframe: pd.DataFrame) -> pd.DataFrame:
    """French-style visual formatting without changing the real cleaned DataFrame."""
    display = dataframe.copy()

    for column in display.columns:
        series = display[column]
        if pd.api.types.is_float_dtype(series):
            display[column] = series.apply(
                lambda value: ""
                if pd.isna(value)
                else f"{float(value):.10f}".rstrip("0").rstrip(".").replace(".", ",")
            )
        elif pd.api.types.is_datetime64_any_dtype(series):
            display[column] = series.apply(
                lambda value: ""
                if pd.isna(value)
                else pd.Timestamp(value).strftime("%Y-%m-%d")
            )

    return display


def export_excel_bytes(dataframe: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False, sheet_name="Cleaned Data")
    return buffer.getvalue()


def scroll_to_replacement_uploader():
    components.html(
        """
        <script>
        let attempts = 0;
        function scrollToTarget() {
            const doc = window.parent.document;
            const target = doc.getElementById("replacement-upload-anchor");
            if (target) {
                target.scrollIntoView({behavior: "smooth", block: "start"});
                return;
            }
            attempts += 1;
            if (attempts < 30) setTimeout(scrollToTarget, 100);
        }
        setTimeout(scrollToTarget, 150);
        </script>
        """,
        height=0,
    )


def inject_scroll_to_top_button():
    """
    Floating "back to top" button.

    Streamlit scrolls inside an internal container (stMain), not on window,
    so a simple href="#anchor" does not work reliably. This injects a real
    button into the parent document that scrolls every possible container.
    The button only appears after scrolling down and never duplicates on rerun.
    """
    components.html(
        """
        <script>
        (function () {
            const win = window.parent;
            const doc = win.document;

            // Clean up previous instance (Streamlit reruns this script often)
            try {
                if (win.__dcScrollCleanup) win.__dcScrollCleanup();
            } catch (e) {}
            const previous = doc.getElementById("scroll-top-button");
            if (previous) previous.remove();

            const button = doc.createElement("button");
            button.id = "scroll-top-button";
            button.type = "button";
            button.title = "Retour en haut";
            button.setAttribute("aria-label", "Retour en haut");
            button.innerHTML =
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
                'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">' +
                '<path d="M12 19V5"></path><path d="M5 12l7-7 7 7"></path></svg>';
            doc.body.appendChild(button);

            function scrollers() {
                const list = [
                    doc.querySelector('[data-testid="stMain"]'),
                    doc.querySelector('section.main'),
                    doc.querySelector('.main'),
                    doc.querySelector('[data-testid="stAppViewContainer"]'),
                    doc.scrollingElement,
                    doc.documentElement,
                    doc.body,
                ];
                return list.filter(Boolean);
            }

            function currentScroll() {
                let max = win.scrollY || 0;
                scrollers().forEach(function (el) {
                    max = Math.max(max, el.scrollTop || 0);
                });
                return max;
            }

            function updateVisibility() {
                if (currentScroll() > 320) {
                    button.classList.add("is-visible");
                } else {
                    button.classList.remove("is-visible");
                }
            }

            function goTop() {
                scrollers().forEach(function (el) {
                    if (el.scrollTo) {
                        el.scrollTo({top: 0, behavior: "smooth"});
                    } else {
                        el.scrollTop = 0;
                    }
                });
                try { win.scrollTo({top: 0, behavior: "smooth"}); } catch (e) {}
            }

            button.addEventListener("click", goTop);
            // 'scroll' does not bubble, so listen in the capture phase
            doc.addEventListener("scroll", updateVisibility, true);
            updateVisibility();

            win.__dcScrollCleanup = function () {
                doc.removeEventListener("scroll", updateVisibility, true);
                button.removeEventListener("click", goTop);
                button.remove();
            };
        })();
        </script>
        """,
        height=0,
    )


def centered_uploader(key: str, title: str, subtitle: str):
    """Render one single centered upload zone. No decorative duplicate box."""
    left, center, right = st.columns([1, 2.15, 1])

    with center:
        html(
            f"""
            <div class="single-upload-heading">
                <div class="cube-scene">
                    <div class="cube">
                        <span class="face f1">↑</span><span class="face f2">▤</span>
                        <span class="face f3">↑</span><span class="face f4">▤</span>
                        <span class="face f5"></span><span class="face f6"></span>
                    </div>
                </div>
                <div class="single-upload-title">{escape(title)}</div>
                <div class="single-upload-sub">{escape(subtitle)}</div>
            </div>
            """
        )

        return st.file_uploader(
            title,
            type=["csv", "xlsx", "xls"],
            key=key,
            help="Formats acceptés : CSV, XLSX et XLS.",
            label_visibility="collapsed",
        )


def render_plan(plan: dict):
    actions = plan.get("actions", []) if isinstance(plan, dict) else []
    selected = []

    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue

        operation = str(action.get("operation", "") or "")
        column = str(action.get("column", "") or "")
        columns = action.get("columns", []) or []
        target = column or ", ".join(str(item) for item in columns)

        confidence = str(action.get("confidence", "medium") or "medium").lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"

        requires_review = bool(action.get("requires_review", False)) or operation == "no_change"
        label = operation_label(operation)
        checkbox_label = label + (f" — {target}" if target else "")

        checked = st.checkbox(
            checkbox_label,
            value=not requires_review,
            key=f"plan_action_{st.session_state.agent_run_id}_{index}",
        )

        target_html = (
            f'<span class="plan-target">{escape(target)}</span>' if target else ""
        )

        replacements_html = ""
        if operation == "replace_values":
            rows = []
            for replacement in (action.get("replacements", []) or [])[:15]:
                if not isinstance(replacement, dict):
                    continue
                old = escape(str(replacement.get("old_value", "")))
                new = escape(str(replacement.get("new_value", "")))
                rows.append(
                    f"""
                    <div class="replacement-row">
                        <span class="replacement-old">{old}</span>
                        <span class="replacement-arrow">→</span>
                        <span class="replacement-new">{new}</span>
                    </div>
                    """
                )
            if rows:
                replacements_html = (
                    '<div class="replacement-box">'
                    '<div class="replacement-caption">CORRECTIONS EXACTES PROPOSÉES</div>'
                    + "".join(rows)
                    + "</div>"
                )

        html(
            f"""
            <div class="plan-card">
                <div class="plan-top">
                    <div class="plan-number">{index + 1}</div>
                    <div class="plan-title">
                        {escape(label)}
                        {target_html}
                        <span class="badge badge-{confidence}">{escape(confidence.upper())}</span>
                    </div>
                </div>
                <div class="plan-reason">{escape(str(action.get('reason', '') or ''))}</div>
                {replacements_html}
            </div>
            """
        )

        if checked:
            selected.append(action)

    return selected


def render_trace(trace):
    if not trace:
        st.caption("Aucun appel d'outil enregistré.")
        return

    for index, item in enumerate(trace, start=1):
        arguments = item.get("arguments", {}) or {}
        compact_arguments = ", ".join(
            f"{key}={str(value)[:120]}" for key, value in arguments.items()
        )
        status = item.get("status", "ok")
        result_summary = str(item.get("result_summary", ""))[:500]

        html(
            f"""
            <div class="trace-row">
                <div class="trace-tool">{index}. {escape(str(item.get('tool', 'tool')))} · {escape(status)}</div>
                <div class="trace-args">{escape(compact_arguments or 'sans paramètre')}</div>
                <div class="trace-result">{escape(result_summary)}</div>
            </div>
            """
        )


def render_execution(log):
    if not log:
        st.caption("Aucune action exécutée.")
        return

    for item in log:
        html(
            f"""
            <div class="execution-card">
                <div class="execution-title">
                    ✓ {escape(operation_label(str(item.get('operation', ''))))} · {int(item.get('affected_count', 0))}
                </div>
                <div class="execution-detail">{escape(str(item.get('details', '')))}</div>
            </div>
            """
        )


def render_post_validation(report: dict | None):
    if not report:
        return

    status = str(report.get("status", "warning"))

    if status == "ok":
        html(
            '<div class="validation-summary validation-ok">'
            '<strong>✓ Validation post-nettoyage réussie</strong>'
            '<span>Aucune régression structurelle importante détectée.</span>'
            '</div>'
        )
    elif status == "warning":
        html(
            '<div class="validation-summary validation-warning">'
            '<strong>⚠ Validation avec points à vérifier</strong>'
            '<span>Le nettoyage est terminé, mais certaines transformations méritent une vérification.</span>'
            '</div>'
        )
    else:
        html(
            '<div class="validation-summary validation-error">'
            '<strong>✕ Régression potentielle détectée</strong>'
            '<span>Vérifiez les contrôles ci-dessous avant d’exporter le dataset.</span>'
            '</div>'
        )

    for check in report.get("checks", []):
        check_status = str(check.get("status", "warning"))
        icon = {"ok": "✓", "warning": "⚠", "error": "✕"}.get(check_status, "•")

        html(
            f"""
            <div class="validation-check validation-check-{escape(check_status)}">
                <div class="validation-check-icon">{icon}</div>
                <div>
                    <div class="validation-check-title">{escape(str(check.get('name', 'Contrôle')))}</div>
                    <div class="validation-check-message">{escape(str(check.get('message', '')))}</div>
                </div>
            </div>
            """
        )


# ============================================================
# SESSION STATE
# ============================================================

DEFAULTS = {
    "df": None,
    "raw_df": None,
    "file_name": None,
    "file_hash": None,
    "file_metadata": None,
    "replace_mode": False,
    "scroll_to_replace": False,
    "upload_version": 0,
    "replacement_version": 0,
    "agent_result": None,
    "plan": None,
    "selected_actions": [],
    "cleaned_df": None,
    "execution_log": None,
    "validation_report": None,
    "agent_error": None,
    "agent_run_id": 0,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    html(
        """
        <div class="brand-wrap">
            <div class="brand-mark">✦</div>
            <div class="brand-title">DataCleaner Agent</div>
            <div class="brand-sub">Tanger Med Zones · Data Quality Workspace</div>
        </div>
        """
    )

    if API_KEY:
        html('<div class="status-box"><span class="status-dot"></span>Agent opérationnel</div>')
    else:
        st.error("GROQ_API_KEY absente")

    if st.session_state.df is not None:
        current = st.session_state.df
        html(
            f"""
            <div class="sidebar-file">
                <div class="sidebar-label">DATASET ACTIF</div>
                <div class="sidebar-name">{escape(str(st.session_state.file_name))}</div>
                <div class="sidebar-meta">{current.shape[0]:,} lignes · {current.shape[1]} colonnes</div>
            </div>
            """
        )


# ============================================================
# HERO
# ============================================================

html(
    """
    <div class="hero">
        __ROBOT__
        <div class="hero-kicker">AGENTIC DATA QUALITY</div>
        <h1>Un agent qui <span>inspecte, vérifie et agit.</span></h1>
        <p>
            Pandas analyse l'intégralité du dataset. L'agent Groq choisit dynamiquement
            les outils utiles, peut vérifier un référentiel externe quand c'est nécessaire,
            puis produit un plan contrôlé que vous validez avant toute modification.
        </p>
    </div>
    """.replace("__ROBOT__", waves_html() + robot_html())
)

# Quand un dataset est déjà actif, on affiche UNE SEULE action de remplacement
# directement dans la zone visuelle du Hero (en bas à droite).
if st.session_state.df is not None:
    hero_left, hero_action = st.columns([5.2, 1.45])

    with hero_action:
        if st.button(
            "↻ Nouveau dataset",
            key="hero_replace_dataset_button",
            use_container_width=True,
            help="Importer un autre fichier sans supprimer le dataset actuel tant que le nouveau n'est pas valide.",
        ):
            st.session_state.replace_mode = True
            st.session_state.replacement_version += 1
            st.session_state.scroll_to_replace = True
            st.rerun()

if not API_KEY:
    st.error("Ajoutez GROQ_API_KEY dans votre fichier .env puis relancez l'application.")
    st.stop()


# ============================================================
# INITIAL UPLOAD
# ============================================================

if st.session_state.df is None:
    uploaded = centered_uploader(
        key=f"initial_upload_{st.session_state.upload_version}",
        title="Importez votre dataset",
        subtitle=(
            "CSV, XLSX ou XLS · encodage, séparateur et ligne d'en-tête détectés automatiquement."
        ),
    )

    if uploaded is not None:
        try:
            with st.spinner("Lecture et analyse du fichier…"):
                install_dataset(uploaded)
            st.session_state.upload_version += 1
            st.rerun()
        except Exception as exc:
            st.error(f"Impossible de lire le fichier : {type(exc).__name__}: {exc}")

    html(feature_strip())
    st.stop()


# ============================================================
# REPLACEMENT UPLOAD - CURRENT DATASET IS KEPT UNTIL SUCCESS
# ============================================================

if st.session_state.replace_mode:
    st.html('<div id="replacement-upload-anchor" style="height:1px;scroll-margin-top:22px"></div>')

    replacement = centered_uploader(
        key=f"replacement_upload_{st.session_state.replacement_version}",
        title="Importer un autre dataset",
        subtitle=(
            "Votre dataset actuel reste actif. Il ne sera remplacé que si le nouveau fichier "
            "CSV, XLSX ou XLS est lu avec succès."
        ),
    )

    if st.session_state.scroll_to_replace:
        scroll_to_replacement_uploader()
        st.session_state.scroll_to_replace = False

    left, center, right = st.columns([1, 1, 1])
    with center:
        if st.button("Annuler", use_container_width=True):
            st.session_state.replace_mode = False
            st.session_state.scroll_to_replace = False
            st.rerun()

    if replacement is not None:
        try:
            with st.spinner("Lecture et analyse du fichier…"):
                install_dataset(replacement)
            st.rerun()
        except Exception as exc:
            st.error(
                f"Nouveau fichier refusé : {type(exc).__name__}: {exc}. "
                "Le dataset actuel est conservé."
            )


# ============================================================
# DATASET
# ============================================================

df = st.session_state.df

html(
    """
    <div class="workflow">
        <span class="step">01 · Import</span><span class="arrow">→</span>
        <span class="step">02 · Agent</span><span class="arrow">→</span>
        <span class="step">03 · Human Review</span><span class="arrow">→</span>
        <span class="step">04 · Execute</span><span class="arrow">→</span>
        <span class="step">05 · Validate & Export</span>
    </div>
    """
)

summary = profile_dataset(df)
section(
    "01 · Dataset",
    "Vue d'ensemble",
    "Le fichier reste intact tant que vous n'avez pas validé le plan de l'agent.",
)

html(
    f"""
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-label">Lignes</div><div class="metric-value">{df.shape[0]:,}</div></div>
        <div class="metric-card"><div class="metric-label">Colonnes</div><div class="metric-value">{df.shape[1]}</div></div>
        <div class="metric-card"><div class="metric-label">Valeurs manquantes</div><div class="metric-value">{summary['total_missing']:,}</div></div>
        <div class="metric-card"><div class="metric-label">Doublons complets</div><div class="metric-value">{summary['duplicate_rows_to_remove']:,}</div></div>
    </div>
    """
)

st.dataframe(df.head(12), use_container_width=True, hide_index=True)


# ============================================================
# AGENT
# ============================================================

section(
    "02 · Agent",
    "Analyse agentique",
    (
        "Le LLM choisit les outils selon le dataset. Les outils Pandas inspectent toutes les lignes ; "
        "le modèle ne reçoit que des résultats compacts."
    ),
)

if st.button("✦ Lancer l'agent Data Quality", type="primary", use_container_width=True):
    reset_analysis()
    with st.spinner("L'agent inspecte le dataset et choisit ses outils..."):
        try:
            result = run_data_cleaning_agent(df, API_KEY)
            st.session_state.agent_result = result
            st.session_state.plan = result.get("plan")
            st.session_state.agent_error = result.get("error")
        except Exception as exc:
            st.session_state.agent_error = f"{type(exc).__name__}: {exc}"

if st.session_state.agent_error:
    st.error(st.session_state.agent_error)

if st.session_state.agent_result:
    result = st.session_state.agent_result

    if st.session_state.plan is not None:
        html(
            """
            <div class="agent-banner">
                <div class="agent-dot">✓</div>
                <div><strong>Analyse agentique terminée</strong><br>
                <span style="color:#6B7F96;font-size:.78rem">Le plan est prêt pour validation humaine.</span></div>
            </div>
            """
        )

    with st.expander("Voir la trace opérationnelle de l'agent"):
        st.caption(
            "Cette vue montre les outils appelés, leurs paramètres et un résumé de résultat ; "
            "elle n'affiche pas la chaîne de pensée privée du modèle."
        )
        render_trace(result.get("trace", []))


# ============================================================
# HUMAN REVIEW + EXECUTION
# ============================================================

if st.session_state.plan:
    section(
        "03 · Human Review",
        "Validez le plan",
        (
            "Décochez toute action que vous ne souhaitez pas appliquer. "
            "Les actions nécessitant une décision humaine sont décochées par défaut."
        ),
    )

    selected = render_plan(st.session_state.plan)
    st.session_state.selected_actions = selected

    section(
        "04 · Execute",
        "Exécution déterministe",
        (
            "Seules les actions sélectionnées sont appliquées par un moteur Pandas à liste blanche. "
            "Aucun code Python arbitraire généré par le LLM n'est exécuté."
        ),
    )

    if st.button(
        "Appliquer les actions sélectionnées",
        type="primary",
        use_container_width=True,
        disabled=not selected,
    ):
        try:
            filtered_plan = {"actions": selected}
            cleaned_df, log = execute_cleaning_plan(df, filtered_plan)
            validation_report = validate_post_cleaning(df, cleaned_df, log)

            st.session_state.cleaned_df = cleaned_df
            st.session_state.execution_log = log
            st.session_state.validation_report = validation_report
        except CleaningPlanError as exc:
            st.error(f"Plan de nettoyage invalide : {exc}")
        except Exception as exc:
            st.error(f"Erreur d'exécution : {type(exc).__name__}: {repr(exc)}")


# ============================================================
# RESULT + EXPORT
# ============================================================

if st.session_state.cleaned_df is not None:
    cleaned = st.session_state.cleaned_df

    section(
        "05 · Validate & Export",
        "Résultat final",
        "Comparez la structure brute au dataset nettoyé, puis exportez le résultat.",
    )

    html(
        f'<div class="success-banner">{check_icon()}'
        '<span>Nettoyage terminé avec succès</span></div>'
    )

    before, after = st.columns(2)
    with before:
        st.markdown("### Avant · fichier brut")
        st.caption("Le préambule et la structure d'origine restent visibles.")
        st.dataframe(st.session_state.raw_df.head(15), use_container_width=True, hide_index=True)

    with after:
        st.markdown("### Après · dataset structuré")
        st.caption("Affichage localisé ; les nombres restent de vrais numériques dans le DataFrame.")
        st.dataframe(
            format_dataframe_for_display(cleaned.head(12)),
            use_container_width=True,
            hide_index=True,
        )

    after_profile = profile_dataset(cleaned)
    html(
        f"""
        <div class="metrics-grid" style="margin-top:18px">
            <div class="metric-card"><div class="metric-label">Lignes finales</div><div class="metric-value">{cleaned.shape[0]:,}</div></div>
            <div class="metric-card"><div class="metric-label">Colonnes finales</div><div class="metric-value">{cleaned.shape[1]}</div></div>
            <div class="metric-card"><div class="metric-label">Manquantes finales</div><div class="metric-value">{after_profile['total_missing']:,}</div></div>
            <div class="metric-card"><div class="metric-label">Doublons finaux</div><div class="metric-value">{after_profile['duplicate_rows_to_remove']:,}</div></div>
        </div>
        """
    )

    st.markdown("### Validation post-nettoyage")
    render_post_validation(st.session_state.validation_report)

    st.markdown("### Journal d'exécution")
    render_execution(st.session_state.execution_log)

    csv_standard = cleaned.to_csv(index=False).encode("utf-8-sig")
    csv_excel_fr = cleaned.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    xlsx_bytes = export_excel_bytes(cleaned)

    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button(
            "CSV standard",
            data=csv_standard,
            file_name="clean_data.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with d2:
        st.download_button(
            "CSV Excel FR",
            data=csv_excel_fr,
            file_name="clean_data_excel_fr.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with d3:
        st.download_button(
            "Excel XLSX",
            data=xlsx_bytes,
            file_name="clean_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


# ============================================================
# BOUTON FLOTTANT RETOUR EN HAUT (toujours en dernier)
# ============================================================

inject_scroll_to_top_button()