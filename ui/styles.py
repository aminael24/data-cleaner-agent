CSS = r"""
<style>
:root {
    /* Palette bleue (marine -> bleu clair) */
    --ice: #EAF2FB;
    --paper: #FFFFFF;
    --navy-900: #04204A;
    --navy: #0B2F5E;
    --dark: #061B38;
    --blue-800: #12508F;
    --blue: #1B5896;
    --blue-600: #225C9B;
    --azure: #5B94CB;
    --sky: #7DB2EA;
    --teal: #2FA38A;
    --green: #2E9E6B;
    --amber: #B7791F;
    --danger: #B4443A;
    --muted: #6B7F96;
    --line: rgba(11, 47, 94, .12);
    --shadow: 0 14px 40px rgba(11, 47, 94, .09);
}

html, body, [class*="css"] {
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.stApp {
    background:
        radial-gradient(circle at 90% 0%, rgba(91,148,203,.16), transparent 30%),
        radial-gradient(circle at 0% 100%, rgba(27,88,150,.10), transparent 32%),
        linear-gradient(180deg, #FFFFFF 0%, var(--ice) 100%);
    color: var(--dark);
}

[data-testid="stHeader"] {background: transparent;}

.block-container {
    max-width: 1440px;
    padding-top: 1rem;
    padding-bottom: 6rem;
}

#MainMenu {visibility: hidden;}
footer {display: none;}
[data-testid="stToolbar"] {visibility: hidden; height: 0;}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #031A3A 0%, var(--navy) 60%, #12508F 140%);
    border-right: 0;
}

.brand-wrap {padding: 1rem .15rem 1.2rem;}
.brand-mark {
    width: 52px; height: 52px; border-radius: 50%;
    display:flex; align-items:center; justify-content:center;
    background: radial-gradient(circle at 35% 30%, #CFE4FA 0%, var(--azure) 35%, var(--blue) 80%);
    color: #fff; font-size: 1.4rem; font-weight: 900;
    border: 3px solid rgba(255,255,255,.35);
    box-shadow: 0 12px 28px rgba(0,0,0,.22);
    margin-bottom: 14px;
}
.brand-title {color:#fff; font-size:1.18rem; font-weight:800; letter-spacing:-.02em;}
.brand-sub {color:rgba(255,255,255,.55); font-size:.74rem; margin-top:4px;}
.status-box {
    margin-top: 12px; padding: 12px 13px; border-radius: 14px;
    display:flex; gap:9px; align-items:center;
    border:1px solid rgba(255,255,255,.10); background:rgba(255,255,255,.06);
    color:rgba(255,255,255,.88); font-size:.77rem; font-weight:650;
}
.status-dot {width:8px; height:8px; border-radius:50%; background:#5BD6A0; box-shadow:0 0 0 5px rgba(91,214,160,.15);}
.sidebar-file {
    margin-top:18px; padding:14px; border-radius:15px;
    background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.10);
}
.sidebar-label {font-size:.60rem; letter-spacing:.13em; font-weight:800; color:rgba(255,255,255,.42);}
.sidebar-name {font-size:.79rem; font-weight:700; color:#fff; margin-top:6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
.sidebar-meta {font-size:.68rem; color:rgba(255,255,255,.55); margin-top:4px;}
[data-testid="stSidebar"] .stButton > button {
    background:rgba(255,255,255,.09)!important; color:#fff!important;
    border:1px solid rgba(255,255,255,.14)!important; border-radius:12px!important;
    min-height:42px; box-shadow:none!important;
}

/* ---------- Hero ---------- */
.hero {
    position:relative; overflow:hidden; border-radius:28px;
    padding:34px 290px 34px 46px; min-height:310px;
    background:
        radial-gradient(90% 140% at 100% 0%, rgba(125,178,234,.55) 0%, transparent 55%),
        linear-gradient(120deg, #04204A 0%, #12508F 55%, #225C9B 100%);
    box-shadow:0 22px 56px rgba(4,32,74,.26); margin-bottom:14px;
}
.hero::before {
    content:""; position:absolute; left:-10%; right:-10%; bottom:-80px; height:160px;
    background:
        radial-gradient(120% 100% at 20% 100%, rgba(91,148,203,.55), transparent 60%),
        radial-gradient(120% 100% at 80% 100%, rgba(125,178,234,.40), transparent 62%);
}
.hero::after {
    content:""; position:absolute; width:380px; height:380px; border-radius:50%;
    right:-120px; top:-190px;
    background:radial-gradient(circle, rgba(255,255,255,.28), transparent 68%);
}
.hero-kicker {position:relative; z-index:2; color:#9CC7F5; font-size:.66rem; font-weight:850; letter-spacing:.16em;}
.hero h1 {position:relative; z-index:2; color:#fff; max-width:920px; font-size:clamp(1.9rem,3.3vw,2.9rem); line-height:1.06; letter-spacing:-.05em; margin:12px 0 0;}
.hero h1 span {color:#9CC7F5;}
.hero p {position:relative; z-index:2; max-width:760px; color:rgba(255,255,255,.78); line-height:1.6; font-size:.88rem; margin:12px 0 0;}

/* ---------- Robot holographique (image SVG animée) ---------- */
.hero-robot {
    position:absolute; z-index:3; right:30px; top:0;
    width:240px; height:232px; pointer-events:none;
}
.hero-robot img {width:100%; height:100%; display:block; object-fit:contain;}
.robot-bubble {
    position:absolute; left:-96px; top:46px; z-index:4;
    background:#fff; color:var(--navy); font-size:.76rem; font-weight:800;
    padding:8px 15px; border-radius:15px 15px 15px 4px;
    box-shadow:0 12px 28px rgba(0,0,0,.22);
    animation: robotBubble 6s ease-in-out infinite;
    white-space:nowrap;
}
@keyframes robotBubble {0%,8%{opacity:0; transform:translateY(6px) scale(.9)} 16%,70%{opacity:1; transform:none} 82%,100%{opacity:0; transform:translateY(-4px) scale(.95)}}
@media (prefers-reduced-motion: reduce) {.robot-bubble {animation:none; opacity:1;}}

/* Bouton natif Streamlit placé visuellement en bas à droite du hero */
.st-key-hero_replace_dataset_button {
    position: relative !important;
    z-index: 20 !important;
    margin-top: -112px !important;
    margin-bottom: 54px !important;
    padding-right: 18px !important;
}
.st-key-hero_replace_dataset_button button {
    min-height: 48px !important;
    border-radius: 14px !important;
    border: 1px solid rgba(255,255,255,.30) !important;
    background: rgba(255,255,255,.14) !important;
    color: #fff !important;
    font-weight: 760 !important;
    box-shadow: 0 12px 28px rgba(0,0,0,.14) !important;
    backdrop-filter: blur(10px) !important;
}
.st-key-hero_replace_dataset_button button:hover {
    background: rgba(255,255,255,.26) !important;
    border-color: rgba(255,255,255,.55) !important;
    color: #fff !important;
}

/* ---------- Upload 3D animé (compact) ---------- */
@property --angle {
    syntax: '<angle>';
    initial-value: 0deg;
    inherits: false;
}

.single-upload-heading {
    max-width: 640px;
    margin: 14px auto 10px;
    text-align: center;
}
.single-upload-title {
    color: var(--navy);
    font-size: 1.15rem;
    font-weight: 840;
    letter-spacing: -.025em;
}
.single-upload-sub {
    max-width: 560px;
    margin: 5px auto 0;
    color: var(--muted);
    font-size: .78rem;
    line-height: 1.5;
}

/* Cube 3D rotatif */
.cube-scene {
    position: relative;
    width: 46px; height: 46px;
    margin: 0 auto 14px;
    perspective: 420px;
    animation: cubeFloat 3.4s ease-in-out infinite;
}
.cube-scene::after {
    content: "";
    position: absolute; left: 50%; bottom: -16px;
    width: 40px; height: 8px; margin-left: -20px;
    border-radius: 50%;
    background: radial-gradient(closest-side, rgba(4,32,74,.30), transparent);
    animation: cubeShadow 3.4s ease-in-out infinite;
}
.cube {
    position: relative; width: 100%; height: 100%;
    transform-style: preserve-3d;
    animation: cubeSpin 9s linear infinite;
}
.cube .face {
    position: absolute; inset: 0;
    display: flex; align-items: center; justify-content: center;
    border: 1.5px solid rgba(125,178,234,.95);
    background: linear-gradient(135deg, rgba(27,88,150,.92), rgba(4,32,74,.95));
    box-shadow: inset 0 0 16px rgba(125,178,234,.40);
    color: #CFE4FA; font-size: 1.15rem; font-weight: 800;
    border-radius: 6px;
}
.cube .f1 {transform: rotateY(0deg)   translateZ(23px);}
.cube .f2 {transform: rotateY(90deg)  translateZ(23px);}
.cube .f3 {transform: rotateY(180deg) translateZ(23px);}
.cube .f4 {transform: rotateY(-90deg) translateZ(23px);}
.cube .f5 {transform: rotateX(90deg)  translateZ(23px);}
.cube .f6 {transform: rotateX(-90deg) translateZ(23px);}
@keyframes cubeSpin {
    from {transform: rotateX(-22deg) rotateY(0deg);}
    to   {transform: rotateX(-22deg) rotateY(360deg);}
}
@keyframes cubeFloat {0%,100%{transform: translateY(0);} 50%{transform: translateY(-6px);}}
@keyframes cubeShadow {0%,100%{transform: scale(1); opacity:1;} 50%{transform: scale(.78); opacity:.6;}}

[data-testid="stFileUploader"] {
    width: 100% !important;
    max-width: 640px !important;
    margin: 0 auto 16px !important;
    perspective: 1000px;
}
[data-testid="stFileUploader"] > label {display: none !important;}

/* Zone de dépôt : verre + bordure animée + inclinaison 3D */
section[data-testid="stFileUploaderDropzone"],
[data-testid="stFileUploaderDropzone"] {
    min-height: 150px !important;
    padding: 20px 24px !important;
    border-radius: 22px !important;
    border: 2px solid transparent !important;
    background:
        linear-gradient(rgba(255,255,255,.96), rgba(244,249,255,.96)) padding-box,
        conic-gradient(from var(--angle), #04204A, #5B94CB, #7DB2EA, #2AA7E6, #04204A) border-box !important;
    animation: borderSpin 7s linear infinite;
    box-shadow:
        0 1px 0 rgba(255,255,255,.9) inset,
        0 18px 40px rgba(4,32,74,.14),
        0 6px 0 rgba(27,88,150,.12) !important;

    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 10px !important;
    text-align: center !important;

    transform-style: preserve-3d;
    transition: transform .35s cubic-bezier(.2,.8,.2,1), box-shadow .35s ease !important;
}
@keyframes borderSpin {to {--angle: 360deg;}}

[data-testid="stFileUploaderDropzone"]:hover {
    transform: rotateX(5deg) translateY(-5px) !important;
    box-shadow:
        0 1px 0 rgba(255,255,255,.9) inset,
        0 30px 56px rgba(4,32,74,.22),
        0 8px 0 rgba(27,88,150,.16) !important;
}

[data-testid="stFileUploaderDropzone"] > div,
[data-testid="stFileUploaderDropzoneInstructions"] {
    width: 100% !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    text-align: center !important;
    gap: 2px !important;
    margin: 0 auto !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] span {
    color: var(--navy) !important;
    font-weight: 750 !important;
    font-size: 0 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] span::after {
    content: "Glissez-déposez votre fichier ici";
    font-size: .92rem;
    color: var(--navy);
}
[data-testid="stFileUploaderDropzoneInstructions"] small {
    color: var(--muted) !important;
    font-size: 0 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] small::after {
    content: "200 Mo max · CSV, XLSX, XLS";
    font-size: .74rem;
    color: var(--muted);
}

/* Bouton Upload 3D "pressable" */
[data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {
    order: -1 !important;
    align-self: center !important;
    margin: 0 auto !important;
    min-width: 170px !important;
    min-height: 44px !important;
    border-radius: 13px !important;
    background: linear-gradient(180deg, #2A6CB8 0%, var(--blue) 45%, var(--navy) 100%) !important;
    color: #fff !important;
    border: 1px solid rgba(255,255,255,.28) !important;
    font-weight: 780 !important;
    box-shadow:
        0 5px 0 #06285A,
        0 14px 24px rgba(4,32,74,.30),
        inset 0 1px 0 rgba(255,255,255,.35) !important;
    transition: transform .15s ease, box-shadow .15s ease, background .2s ease !important;
    animation: btnPulse 2.8s ease-in-out infinite;
}
@keyframes btnPulse {
    0%,100% {filter: brightness(1);}
    50%     {filter: brightness(1.12);}
}
[data-testid="stFileUploaderDropzone"] button:hover {
    transform: translateY(-2px) !important;
    background: linear-gradient(180deg, #5B94CB 0%, #2A6CB8 45%, var(--blue) 100%) !important;
    box-shadow:
        0 7px 0 #06285A,
        0 18px 28px rgba(4,32,74,.34),
        inset 0 1px 0 rgba(255,255,255,.4) !important;
}
[data-testid="stFileUploaderDropzone"] button:active {
    transform: translateY(4px) !important;
    box-shadow:
        0 1px 0 #06285A,
        0 6px 12px rgba(4,32,74,.30),
        inset 0 1px 0 rgba(255,255,255,.3) !important;
}

[data-testid="stFileUploaderFile"] {
    max-width: 640px !important;
    margin-left: auto !important;
    margin-right: auto !important;
}

@media (prefers-reduced-motion: reduce) {
    .cube, .cube-scene, .cube-scene::after,
    [data-testid="stFileUploaderDropzone"],
    [data-testid="stFileUploaderDropzone"] button {animation: none !important;}
}

/* ---------- Validation post-nettoyage ---------- */
.validation-summary {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 15px 17px;
    border-radius: 15px;
    margin: 8px 0 12px;
    font-size: .78rem;
}
.validation-summary strong {font-size:.84rem;}
.validation-ok {background:rgba(46,158,107,.09); border:1px solid rgba(46,158,107,.22);}
.validation-warning {background:rgba(183,121,31,.10); border:1px solid rgba(183,121,31,.25);}
.validation-error {background:rgba(180,68,58,.09); border:1px solid rgba(180,68,58,.22);}
.validation-check {
    display:flex;
    gap:12px;
    align-items:flex-start;
    padding:13px 15px;
    margin:7px 0;
    border-radius:14px;
    background:rgba(255,255,255,.82);
    border:1px solid var(--line);
}
.validation-check-icon {
    width:29px;
    height:29px;
    flex:0 0 29px;
    display:flex;
    align-items:center;
    justify-content:center;
    border-radius:9px;
    font-weight:850;
}
.validation-check-ok .validation-check-icon {background:rgba(46,158,107,.13); color:var(--green);}
.validation-check-warning .validation-check-icon {background:rgba(183,121,31,.15); color:var(--amber);}
.validation-check-error .validation-check-icon {background:rgba(180,68,58,.11); color:var(--danger);}
.validation-check-title {font-size:.77rem; font-weight:800; color:var(--dark);}
.validation-check-message {font-size:.72rem; color:var(--muted); line-height:1.45; margin-top:3px;}

/* ---------- Sections ---------- */
.workflow {display:flex; gap:14px; align-items:center; justify-content:center; flex-wrap:wrap; margin:34px 0 10px;}
.step {padding:13px 24px; border-radius:999px; background:rgba(255,255,255,.92); border:1px solid var(--line); color:var(--navy); font-size:.9rem; font-weight:780; box-shadow:0 8px 22px rgba(11,47,94,.08);}
.arrow {color:var(--azure); font-size:1.35rem; font-weight:700;}
.section {margin:34px 0 17px;}
.section-kicker {color:var(--blue); font-size:.64rem; font-weight:850; letter-spacing:.15em; text-transform:uppercase; margin-bottom:5px;}
.section-title {font-size:1.48rem; line-height:1.2; font-weight:820; letter-spacing:-.035em; color:var(--navy);}
.section-sub {max-width:850px; margin-top:7px; color:var(--muted); font-size:.83rem; line-height:1.55;}

.metrics-grid {display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-bottom:18px;}
.metric-card {
    background:rgba(255,255,255,.88); border:1px solid var(--line);
    border-top:3px solid var(--blue);
    padding:19px; border-radius:18px; box-shadow:var(--shadow);
}
.metric-label {font-size:.61rem; letter-spacing:.1em; color:var(--muted); font-weight:820; text-transform:uppercase;}
.metric-value {font-size:1.64rem; font-weight:830; color:var(--navy); margin-top:5px;}

/* Boutons principaux */
.stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"] {
    background:linear-gradient(135deg, var(--blue), var(--navy))!important;
    color:#fff!important; border:0!important; border-radius:13px!important;
    min-height:49px!important; font-weight:760!important;
    box-shadow:0 12px 26px rgba(27,88,150,.26)!important;
    transition: transform .18s ease, box-shadow .18s ease, background .18s ease !important;
}
.stButton > button[kind="primary"]:hover, .stButton > button[data-testid="stBaseButton-primary"]:hover {
    background:linear-gradient(135deg, var(--azure), var(--blue))!important;
    transform: translateY(-2px);
    box-shadow:0 16px 32px rgba(27,88,150,.32)!important;
}
.stButton > button[kind="primary"]:disabled {
    background: rgba(11,47,94,.18)!important;
    box-shadow:none!important;
    color: rgba(255,255,255,.8)!important;
}
.stButton > button[kind="secondary"], .stButton > button[data-testid="stBaseButton-secondary"] {
    border-radius:13px!important; border:1px solid var(--line)!important;
    color:var(--navy)!important; background:rgba(255,255,255,.85)!important;
}
.stDownloadButton > button {
    border-radius:13px!important; min-height:46px!important; font-weight:740!important;
    border:1px solid rgba(27,88,150,.28)!important;
    color:var(--blue)!important; background:rgba(255,255,255,.92)!important;
}
.stDownloadButton > button:hover {
    background:var(--blue)!important; color:#fff!important; border-color:var(--blue)!important;
}

[data-testid="stDataFrame"] {border:1px solid var(--line); border-radius:17px; overflow:hidden; box-shadow:var(--shadow);}

[data-testid="stExpander"] {
    border:1px solid var(--line)!important; border-radius:16px!important;
    background:rgba(255,255,255,.78)!important;
}

.agent-banner, .success-banner {
    margin:12px 0 18px; border-radius:16px; padding:15px 17px;
    background:rgba(46,158,107,.09); border:1px solid rgba(46,158,107,.20); color:var(--dark);
}
.agent-banner {display:flex; gap:12px; align-items:center;}
.agent-dot {width:34px; height:34px; border-radius:10px; display:flex; align-items:center; justify-content:center; color:white; background:linear-gradient(135deg, var(--teal), var(--green)); font-weight:800;}

/* ---------- Plan cards ---------- */
.plan-card {margin:10px 0 20px; padding:20px 22px; border-radius:19px; background:rgba(255,255,255,.90); border:1px solid var(--line); border-left:4px solid var(--blue); box-shadow:var(--shadow);}
.plan-top {display:flex; align-items:center; gap:12px;}
.plan-number {min-width:35px; height:35px; border-radius:11px; display:flex; align-items:center; justify-content:center; background:rgba(27,88,150,.10); color:var(--blue); font-size:.75rem; font-weight:850;}
.plan-title {display:flex; align-items:center; flex-wrap:wrap; gap:8px; font-weight:800; font-size:.86rem; color:var(--navy);}
.plan-target {padding:5px 10px; border-radius:999px; background:rgba(91,148,203,.15); color:var(--blue); font-size:.66rem; font-weight:780;}
.badge {padding:5px 10px; border-radius:999px; font-size:.62rem; font-weight:850; letter-spacing:.04em;}
.badge-high {background:rgba(46,158,107,.13); color:var(--green);}
.badge-medium {background:rgba(183,121,31,.14); color:var(--amber);}
.badge-low {background:rgba(180,68,58,.11); color:var(--danger);}
.plan-reason {margin:12px 0 0 47px; color:var(--muted); font-size:.78rem; line-height:1.55;}
.replacement-box {margin:13px 0 0 47px; padding:12px; border-radius:12px; background:rgba(27,88,150,.05); border:1px solid rgba(27,88,150,.08);}
.replacement-caption {font-size:.57rem; letter-spacing:.12em; font-weight:850; color:var(--muted); margin-bottom:7px;}
.replacement-row {display:flex; gap:10px; align-items:center; font-size:.76rem; padding:4px 0;}
.replacement-old {color:var(--danger); font-weight:700;}
.replacement-arrow {color:rgba(11,47,94,.35);}
.replacement-new {color:var(--green); font-weight:760;}

.trace-row, .execution-card {padding:13px 15px; background:rgba(255,255,255,.82); border:1px solid var(--line); border-radius:14px; margin:8px 0;}
.trace-tool, .execution-title {font-size:.78rem; font-weight:800; color:var(--navy);}
.trace-args, .trace-result, .execution-detail {font-size:.71rem; color:var(--muted); margin-top:5px; line-height:1.45; overflow-wrap:anywhere;}
.trace-result {color:rgba(107,127,150,.85);}

/* ---------- Bouton flottant : retour en haut ---------- */
#scroll-top-button {
    position: fixed;
    right: 28px;
    bottom: 28px;
    width: 52px;
    height: 52px;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 999999;
    border-radius: 16px;
    border: 1px solid rgba(255,255,255,.40);
    background: linear-gradient(135deg, var(--blue), var(--navy));
    color: #fff;
    cursor: pointer;
    box-shadow: 0 14px 34px rgba(27,88,150,.35);
    opacity: 0;
    visibility: hidden;
    transform: translateY(14px);
    transition: opacity .25s ease, transform .25s ease, visibility .25s ease, background .2s ease, box-shadow .2s ease;
}
#scroll-top-button.is-visible {
    opacity: 1;
    visibility: visible;
    transform: translateY(0);
}
#scroll-top-button.is-visible:hover {
    transform: translateY(-4px);
    background: linear-gradient(135deg, var(--azure), var(--blue));
    box-shadow: 0 18px 40px rgba(27,88,150,.42);
}
#scroll-top-button:active {transform: scale(.94);}
#scroll-top-button svg {width: 22px; height: 22px; pointer-events: none;}

@media (max-width: 900px) {
    .hero-robot {display:none;}
    .metrics-grid {grid-template-columns:repeat(2,minmax(0,1fr));}
    .hero {padding:32px 26px 96px; min-height:0;}
    .arrow {display:none;}
    .step {padding:10px 16px; font-size:.78rem;}
    .st-key-hero_replace_dataset_button {
        margin-top: -98px !important;
        margin-bottom: 38px !important;
        padding-right: 8px !important;
    }
}
@media (max-width: 600px) {
    .metrics-grid {grid-template-columns:1fr;}
    .plan-reason, .replacement-box {margin-left:0;}
    #scroll-top-button {right:14px; bottom:18px; width:46px; height:46px; border-radius:14px;}
}

/* =====================================================================
   ACCENT SABLE #F3E2C5  +  EFFETS "WOW"  (surcharge finale)
   ===================================================================== */
:root {
    --sand: #F3E2C5;
    --sand-soft: #FBF4E6;
    --sand-deep: #E2C48F;
    --sand-ink: #8A6A2F;
}

@keyframes riseIn {
    from {opacity: 0; transform: translateY(18px);}
    to   {opacity: 1; transform: translateY(0);}
}
@keyframes sandShine {
    from {background-position: 0% center;}
    to   {background-position: 200% center;}
}
@keyframes auroraDrift {
    from {transform: translateX(-5%);}
    to   {transform: translateX(5%);}
}
@keyframes btnSweep {
    0%, 60% {left: -60%;}
    100%    {left: 130%;}
}

::selection {background: var(--sand); color: var(--navy);}
::-webkit-scrollbar {width: 11px; height: 11px;}
::-webkit-scrollbar-track {background: var(--sand-soft);}
::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--azure), var(--blue-800));
    border-radius: 10px; border: 2px solid var(--sand-soft);
}

/* ---------- Fond : mer (bleu) + plage (sable) ---------- */
.stApp {
    background:
        radial-gradient(900px 520px at 96% -6%, rgba(125,178,234,.32), transparent 60%),
        radial-gradient(820px 540px at -6% 106%, rgba(243,226,197,.95), transparent 62%),
        radial-gradient(700px 420px at 106% 102%, rgba(243,226,197,.60), transparent 62%),
        linear-gradient(180deg, #F7FAFE 0%, #EDF4FB 55%, #FAF2E2 100%);
}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {border-right: 1px solid rgba(243,226,197,.20);}
.brand-mark {
    box-shadow: 0 0 0 4px rgba(243,226,197,.22), 0 14px 30px rgba(0,0,0,.28);
}
.sidebar-label {color: rgba(243,226,197,.75);}
.sidebar-file {border-left: 3px solid var(--sand);}
.status-box {border-color: rgba(243,226,197,.25);}

/* ---------- Hero ---------- */
.hero {
    background:
        radial-gradient(70% 95% at 100% 115%, rgba(243,226,197,.50) 0%, transparent 62%),
        radial-gradient(90% 140% at 100% 0%, rgba(125,178,234,.55) 0%, transparent 55%),
        linear-gradient(120deg, #04204A 0%, #12508F 55%, #225C9B 100%);
    border: 1px solid rgba(243,226,197,.25);
    box-shadow: 0 26px 64px rgba(4,32,74,.30), inset 0 1px 0 rgba(255,255,255,.14);
    animation: riseIn .8s ease backwards;
}
.hero::before {
    background:
        radial-gradient(120% 100% at 15% 100%, rgba(243,226,197,.55), transparent 60%),
        radial-gradient(120% 100% at 85% 100%, rgba(125,178,234,.45), transparent 62%);
    animation: auroraDrift 12s ease-in-out infinite alternate;
}
.hero-kicker {
    color: var(--sand);
    display: inline-flex; align-items: center; gap: 12px;
}
.hero-kicker::before {
    content: ""; width: 30px; height: 2px; border-radius: 2px;
    background: linear-gradient(90deg, var(--sand), transparent);
}
.hero h1 span {
    background: linear-gradient(90deg, #F3E2C5 0%, #FFFFFF 45%, #F3E2C5 90%);
    background-size: 200% auto;
    -webkit-background-clip: text; background-clip: text;
    color: transparent; -webkit-text-fill-color: transparent;
    animation: sandShine 5s linear infinite;
}
.robot-bubble {
    background: var(--sand); color: var(--navy);
    border: 1px solid rgba(255,255,255,.7);
}
.st-key-hero_replace_dataset_button button {
    border: 1px solid rgba(243,226,197,.55) !important;
    background: rgba(243,226,197,.14) !important;
}
.st-key-hero_replace_dataset_button button:hover {
    background: rgba(243,226,197,.32) !important;
    border-color: rgba(243,226,197,.9) !important;
}

/* ---------- Étapes ---------- */
.step {
    background: linear-gradient(180deg, #FFFFFF, var(--sand-soft));
    border: 1px solid rgba(226,196,143,.75);
    transition: transform .25s ease, box-shadow .25s ease;
    animation: riseIn .6s ease backwards;
}
.workflow .step:nth-of-type(2) {animation-delay: .06s;}
.workflow .step:nth-of-type(3) {animation-delay: .12s;}
.workflow .step:nth-of-type(4) {animation-delay: .18s;}
.workflow .step:nth-of-type(5) {animation-delay: .24s;}
.step:hover {
    transform: translateY(-4px);
    box-shadow: 0 16px 30px rgba(4,32,74,.14), 0 0 0 4px rgba(243,226,197,.75);
}
.arrow {color: var(--sand-deep);}

/* ---------- Titres de section ---------- */
.section {animation: riseIn .6s ease backwards;}
.section-kicker {
    display: inline-flex; align-items: center; gap: 10px;
    color: var(--blue-800);
}
.section-kicker::before {
    content: ""; width: 28px; height: 3px; border-radius: 3px;
    background: linear-gradient(90deg, var(--blue-800), var(--sand-deep));
}
.section-title {
    background: linear-gradient(90deg, var(--navy-900), var(--blue-600));
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent; color: transparent;
}

/* ---------- Cartes métriques 3D ---------- */
.metrics-grid {perspective: 1100px;}
.metric-card {
    position: relative; overflow: hidden;
    background: linear-gradient(180deg, #FFFFFF, var(--sand-soft));
    border: 1px solid rgba(226,196,143,.60);
    transition: transform .3s cubic-bezier(.2,.8,.2,1), box-shadow .3s ease;
    animation: riseIn .7s ease backwards;
}
.metric-card:nth-child(2) {animation-delay: .08s;}
.metric-card:nth-child(3) {animation-delay: .16s;}
.metric-card:nth-child(4) {animation-delay: .24s;}
.metric-card::before {
    content: ""; position: absolute; left: 0; right: 0; top: 0; height: 4px;
    background: linear-gradient(90deg, var(--blue-800), var(--azure), var(--sand-deep));
}
.metric-card:hover {
    transform: rotateX(6deg) translateY(-7px);
    box-shadow: 0 26px 46px rgba(4,32,74,.18);
}
.metric-value {
    background: linear-gradient(90deg, var(--navy-900), var(--blue-600));
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent; color: transparent;
}

/* ---------- Cartes du plan ---------- */
.plan-card {
    background: linear-gradient(180deg, #FFFFFF, #FFFCF6);
    border-left: 4px solid var(--azure);
    transition: transform .25s ease, box-shadow .25s ease;
    animation: riseIn .5s ease backwards;
}
.plan-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 20px 38px rgba(4,32,74,.14);
}
.plan-number {
    background: linear-gradient(135deg, var(--blue-800), var(--azure));
    color: #fff;
}
.plan-target {background: rgba(243,226,197,.85); color: var(--sand-ink);}
.trace-row, .execution-card, .validation-check {
    border-color: rgba(226,196,143,.45);
    transition: transform .2s ease, box-shadow .2s ease;
}
.trace-row:hover, .execution-card:hover, .validation-check:hover {
    transform: translateX(4px);
    box-shadow: 0 10px 22px rgba(4,32,74,.08);
}

/* ---------- Boutons ---------- */
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    position: relative; overflow: hidden;
}
.stButton > button[kind="primary"]::after,
.stButton > button[data-testid="stBaseButton-primary"]::after {
    content: ""; position: absolute; top: 0; left: -60%;
    width: 40%; height: 100%; pointer-events: none;
    background: linear-gradient(100deg, transparent, rgba(243,226,197,.60), transparent);
    transform: skewX(-20deg);
    animation: btnSweep 3.6s ease-in-out infinite;
}
.stDownloadButton > button {
    border: 1px solid rgba(226,196,143,.9) !important;
    background: linear-gradient(180deg, #FFFFFF, var(--sand-soft)) !important;
    color: var(--navy) !important;
    transition: transform .2s ease, box-shadow .2s ease, background .2s ease !important;
}
.stDownloadButton > button:hover {
    background: var(--sand) !important;
    color: var(--navy) !important;
    border-color: var(--sand-deep) !important;
    transform: translateY(-3px);
    box-shadow: 0 14px 26px rgba(4,32,74,.14) !important;
}

/* ---------- Tableaux / expanders ---------- */
[data-testid="stDataFrame"] {
    border: 1px solid rgba(226,196,143,.60);
    box-shadow: 0 14px 34px rgba(4,32,74,.08);
}
[data-testid="stExpander"] {
    border: 1px solid rgba(226,196,143,.60) !important;
    background: linear-gradient(180deg, rgba(255,255,255,.88), rgba(251,244,230,.80)) !important;
}

/* ---------- Upload : touche sable ---------- */
section[data-testid="stFileUploaderDropzone"],
[data-testid="stFileUploaderDropzone"] {
    background:
        linear-gradient(#FFFEFB, #FBF4E6) padding-box,
        conic-gradient(from var(--angle), #04204A, #5B94CB, #F3E2C5, #7DB2EA, #E2C48F, #04204A) border-box !important;
}
.cube .face {
    border-color: rgba(243,226,197,.95);
    color: var(--sand);
}

/* ---------- Bouton retour en haut ---------- */
#scroll-top-button {
    border: 2px solid var(--sand);
    color: var(--sand);
}
#scroll-top-button.is-visible:hover {
    background: linear-gradient(135deg, var(--sand), var(--sand-deep));
    color: var(--navy);
}

@media (prefers-reduced-motion: reduce) {
    .hero, .hero::before, .hero h1 span, .step, .section, .metric-card,
    .plan-card, .stButton > button::after {animation: none !important;}
}

/* =====================================================================
   UPLOAD : état "fichier sélectionné" (puce + boutons + / ✕)
   Les styles 3D du bouton Upload ne doivent pas s'appliquer ici.
   ===================================================================== */
[data-testid="stFileUploader"]:has([data-testid="stFileUploaderFile"]) section[data-testid="stFileUploaderDropzone"],
[data-testid="stFileUploader"]:has([data-testid="stFileUploaderFile"]) [data-testid="stFileUploaderDropzone"] {
    min-height: 0 !important;
    padding: 12px 18px !important;
    flex-direction: row !important;
    justify-content: center !important;
    gap: 14px !important;
    animation: none !important;
    transform: none !important;
    border: 2px solid rgba(226,196,143,.85) !important;
    background: linear-gradient(#FFFEFB, #FBF4E6) !important;
    box-shadow: 0 10px 26px rgba(4,32,74,.10) !important;
}
[data-testid="stFileUploader"]:has([data-testid="stFileUploaderFile"]) [data-testid="stFileUploaderDropzone"]:hover {
    transform: none !important;
}
[data-testid="stFileUploader"]:has([data-testid="stFileUploaderFile"]) [data-testid="stFileUploaderDropzone"] > div {
    width: auto !important;
    flex-direction: row !important;
}
/* boutons + et ✕ : petits, sobres, sans effet 3D */
[data-testid="stFileUploader"]:has([data-testid="stFileUploaderFile"]) [data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploader"]:has([data-testid="stFileUploaderFile"]) [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {
    order: 0 !important;
    min-width: 0 !important;
    width: 38px !important;
    min-height: 38px !important;
    height: 38px !important;
    padding: 0 !important;
    margin: 0 !important;
    border-radius: 11px !important;
    background: rgba(11,47,94,.07) !important;
    color: var(--navy) !important;
    border: 1px solid rgba(11,47,94,.14) !important;
    box-shadow: none !important;
    animation: none !important;
    filter: none !important;
    transform: none !important;
}
[data-testid="stFileUploader"]:has([data-testid="stFileUploaderFile"]) [data-testid="stFileUploaderDropzone"] button:hover {
    background: var(--sand) !important;
    border-color: var(--sand-deep) !important;
    transform: none !important;
    box-shadow: none !important;
}
[data-testid="stFileUploader"]:has([data-testid="stFileUploaderFile"]) [data-testid="stFileUploaderDropzone"] button svg {
    color: var(--navy) !important;
    fill: currentColor;
}
/* puce du fichier : fond transparent, texte lisible */
[data-testid="stFileUploaderFile"] {
    background: transparent !important;
    max-width: none !important;
    margin: 0 !important;
}
[data-testid="stFileUploaderFileName"] {color: var(--navy) !important; font-weight: 700 !important;}
[data-testid="stFileUploaderFile"] small {color: var(--muted) !important;}
[data-testid="stFileUploaderFile"] [data-testid="stFileChipIcon"],
[data-testid="stFileUploaderFile"] > div:first-child > div:first-child {
    background: linear-gradient(135deg, var(--blue-800), var(--navy)) !important;
    color: #fff !important;
    border-radius: 10px !important;
}

/* =====================================================================
   SVG ANIMÉS : vagues, coche, cartes de fonctionnalités, flèches
   ===================================================================== */
.hero-waves {
    position: absolute; left: 0; right: 0; bottom: 0; z-index: 1;
    width: 100%; height: 86px; display: block; pointer-events: none;
}
.check-anim {width: 34px; height: 34px; flex: 0 0 34px;}
.success-banner {display: flex; align-items: center; gap: 12px; font-weight: 720;}

.arrow {display: inline-block; animation: nudge 1.8s ease-in-out infinite;}
@keyframes nudge {0%,100% {transform: translateX(0);} 50% {transform: translateX(5px);}}

.agent-dot {position: relative;}
.agent-dot::after {
    content: ""; position: absolute; inset: -5px; border-radius: 14px;
    border: 2px solid rgba(46,158,107,.55);
    animation: ping 1.8s ease-out infinite;
}
@keyframes ping {0% {transform: scale(.8); opacity: 1;} 100% {transform: scale(1.45); opacity: 0;}}

.feature-strip {
    max-width: 980px; margin: 8px auto 0;
    display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px;
}
.feature-card {
    display: flex; align-items: center; gap: 14px;
    padding: 14px 16px; border-radius: 18px;
    background: linear-gradient(180deg, rgba(255,255,255,.92), rgba(251,244,230,.90));
    border: 1px solid rgba(226,196,143,.60);
    box-shadow: 0 10px 26px rgba(4,32,74,.07);
    transition: transform .3s cubic-bezier(.2,.8,.2,1), box-shadow .3s ease;
    animation: riseIn .7s ease backwards;
}
.feature-card:nth-child(2) {animation-delay: .1s;}
.feature-card:nth-child(3) {animation-delay: .2s;}
.feature-card:hover {transform: translateY(-5px); box-shadow: 0 20px 38px rgba(4,32,74,.14);}
.feature-icon {width: 54px; height: 54px; flex: 0 0 54px;}
.feature-title {font-size: .84rem; font-weight: 800; color: var(--navy);}
.feature-text {font-size: .72rem; color: var(--muted); line-height: 1.45; margin-top: 3px;}

@media (max-width: 900px) {
    .feature-strip {grid-template-columns: 1fr;}
}
@media (prefers-reduced-motion: reduce) {
    .arrow, .agent-dot::after, .feature-card {animation: none !important;}
}
</style>
"""