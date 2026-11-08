"""Design tokens + the one CSS block injected on every page. All raw CSS lives here."""
import streamlit as st

TOKENS = {
    "maroon": "#7F1719",
    "maroon-dark": "#6A1214",
    "cream": "#F4E6D3",
    "page-bg": "#F8F4F0",
    "card-bg": "#F8F4F0",
    "card-hl": "#FFFFFF",
    "tan": "#E2C294",
    "tan-hover": "#D8B47F",
    "tan-text": "#1F1A14",
    "image-ph": "#E6E9EF",
    "ink": "#1F2328",
    "muted": "#5B6470",
    "border": "#DDE1E6",
    "footer-bg": "#F7F8FA",
    "link": "#1A55C6",
    "gold": "#E8C48A",
    "panel": "#F3F4F6",
}

FONTS = ("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700"
         "&family=Nunito:wght@700;800&display=swap")

_CSS = """
@import url('{fonts}');
:root {{ {vars} }}

/* ---------- base ---------- */
html, body, .stApp, [data-testid="stAppViewContainer"] {{ background: var(--page-bg); color: var(--ink);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"], [data-testid="stDecoration"], #MainMenu, footer {{ display: none !important; }}
.block-container, [data-testid="stMainBlockContainer"] {{ max-width: 1080px; padding: 0 2rem !important; }}
h1, h2, h3, h4 {{ color: var(--ink); font-family: 'Inter', sans-serif; letter-spacing: -0.01em; }}
a {{ color: var(--link); }}
.muted {{ color: var(--muted); }}
.small {{ font-size: 0.82rem; }}
.bleed {{ margin-left: calc(50% - 50vw); margin-right: calc(50% - 50vw);
  padding-left: calc(50vw - 50%); padding-right: calc(50vw - 50%); }}

/* Streamlit gives every markdown block margin-bottom:-1rem to cancel a trailing <p> margin. Our raw-HTML
   blocks end in a <div>, so that pull overlapped the next element by 16px. Cancel it for those. */
[data-testid="stMarkdownContainer"]:has(> div:last-child),
[data-testid="stMarkdownContainer"]:has(> table:last-child) {{ margin-bottom: 0 !important; }}

/* ---------- header / nav / banner ---------- */
.as-header {{ background: var(--maroon); color: #fff; padding-top: 1.2rem; margin-top: -1rem; padding-bottom: .8rem;
  display: flex; align-items: baseline; justify-content: space-between; }}
.as-wordmark {{ font-family: 'Nunito', 'Inter', sans-serif; font-weight: 800; font-size: 1.6rem; color: #fff; }}
.as-by {{ font-family: 'Nunito', sans-serif; font-weight: 700; font-size: .88rem; color: var(--gold); margin-left: .5rem; }}
.as-tagline {{ font-family: 'Nunito', sans-serif; font-weight: 700; color: var(--gold); font-size: .95rem; }}
.st-key-navrow {{ background: var(--maroon); width: 100vw !important; max-width: 100vw !important;
  margin-left: calc(50% - 50vw); padding: 0 calc(50vw - 50%); gap: 0.25rem !important;
  position: relative; z-index: 3; margin-top: -2rem; }}
.st-key-navrow a[data-testid="stPageLink-NavLink"] {{ padding: 0.4rem .8rem 0.55rem; border-radius: 0;
  border-bottom: 3px solid transparent; background: transparent !important; }}
.st-key-navrow a[data-testid="stPageLink-NavLink"] p, .st-key-navrow a[data-testid="stPageLink-NavLink"] span {{
  color: #F3E2E2 !important; font-weight: 400; font-size: .92rem; }}
.st-key-navrow a[data-testid="stPageLink-NavLink"]:hover p {{ color: #fff !important; }}
.st-key-navitem_active a[data-testid="stPageLink-NavLink"] {{ border-bottom: 3px solid var(--tan) !important; }}
.st-key-navitem_active a p {{ color: #fff !important; font-weight: 700; }}
.st-key-navrow [data-testid="stPageLink-NavLink"][aria-current="page"] {{ border-bottom-color: var(--tan); }}
.st-key-navrow [data-testid="stPageLink-NavLink"][aria-current="page"] p {{ color: #fff !important; font-weight: 700; }}
.as-banner {{ background: var(--cream); color: var(--maroon); font-weight: 600; font-size: .9rem;
  padding-top: .45rem; padding-bottom: .45rem; margin-top: -1rem; margin-bottom: .6rem; }}

/* ---------- headings ---------- */
.as-h1 {{ font-size: 1.6rem; font-weight: 700; letter-spacing: -.01em; margin: .3rem 0 0; }}
.as-h2 {{ font-size: 1.3rem; font-weight: 700; letter-spacing: -.01em; margin: .2rem 0 0; }}
.as-h3 {{ font-size: 1rem; font-weight: 700; margin: .2rem 0 .25rem; }}
.as-sub {{ color: var(--muted); font-size: .86rem; margin-bottom: 0; }}

/* ---------- panels / cards (st.container keys) ---------- */
[class*="st-key-panel"] {{ border: 1.5px solid var(--maroon); border-radius: 12px; background: #fff;
  padding: .8rem 1rem !important; gap: .45rem !important; }}
[class*="st-key-card"] {{ border: 1px solid var(--border); border-radius: 12px; background: var(--card-bg);
  padding: 0 0 .75rem 0 !important; overflow: hidden; gap: 0.4rem !important; }}
[class*="st-key-cardhl"] {{ border-color: var(--tan); box-shadow: 0 0 0 1px var(--tan); }}
[class*="st-key-card"] > div:not(:first-child) {{ padding-left: 1rem; padding-right: 1rem; }}
[class*="st-key-tile"] {{ border: 1px solid var(--border); border-radius: 12px; background: var(--card-bg);
  padding: .75rem .85rem !important; gap: .45rem !important; }}
[class*="st-key-tilehl"] {{ border-color: var(--tan); box-shadow: 0 0 0 1px var(--tan); }}
[class*="st-key-softcard"] {{ border: 1px solid var(--border); border-radius: 12px; background: #fff;
  padding: .7rem .9rem !important; gap: .4rem !important; }}
[class*="st-key-resrow"] {{ border-top: 1px solid var(--border); padding: .5rem .8rem !important; background: var(--page-bg); }}
[class*="st-key-resrowopen"] {{ background: #fff; }}
[class*="st-key-restable"] {{ border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
  background: #fff; gap: 0 !important; }}
[class*="st-key-cabinpanel"] {{ background: var(--panel); border-radius: 10px; padding: .7rem !important; gap: .4rem !important; margin: 0 .8rem .6rem; width: calc(100% - 1.6rem) !important; }}
[class*="st-key-cabinpanel"] .amen {{ background: transparent; padding: 0; min-height: 0; }}

/* ---------- image tiles ---------- */
.img-ph {{ background: var(--image-ph); color: var(--muted); display: flex; align-items: center; justify-content: center;
  font-size: .8rem; text-align: center; border-radius: 8px; width: 100%; }}
.img-tile {{ width: 100% !important; object-fit: cover !important; border-radius: 8px; display: block; background: var(--image-ph); }}
/* Photo library: square tiles. The plane photo fits inside its square (whole aircraft visible), the rest fill it. */
.img-tile.lib, .img-ph.lib {{ aspect-ratio: 1 / 1; height: auto !important; }}
.img-tile.lib-fit {{ object-fit: contain !important; background: #fff; border: 1px solid var(--border); }}
.card-img {{ border-radius: 0 !important; height: 190px; }}
.card-img.img-ph {{ border-radius: 0; }}
.credit {{ color: var(--muted); font-size: .72rem; margin-top: .25rem; line-height: 1.3; }}
.credit a {{ color: var(--muted); }}

/* ---------- fare / deal card text ---------- */
.fc-top {{ display: flex; justify-content: space-between; align-items: baseline; gap: .5rem; }}
.fc-route {{ font-weight: 700; font-size: 1.05rem; }}
.fc-price {{ font-weight: 700; font-size: 1.35rem; }}
.fc-line {{ color: var(--muted); font-size: .84rem; margin-top: .12rem; }}
.fc-meta {{ color: var(--ink); font-size: .84rem; margin-top: .2rem; }}
.est {{ font-size: .72rem; font-weight: 600; color: var(--muted); margin-left: .2rem; }}
.badge-drop {{ background: var(--cream); color: var(--maroon); font-weight: 700; font-size: .78rem;
  padding: .12rem .45rem; border-radius: 6px; white-space: nowrap; }}
.badge-track {{ background: var(--panel); color: var(--muted); font-size: .72rem; padding: .12rem .45rem; border-radius: 6px; }}
.was {{ color: var(--muted); font-size: .82rem; }}
.spark {{ border: 1px dashed var(--border); border-radius: 8px; padding: .3rem .5rem; margin: .4rem 0; background: #fff; }}
.spark-empty {{ color: var(--muted); font-size: .75rem; text-align: center; padding: .7rem 0; }}

/* ---------- buttons ---------- */
[data-testid="stBaseButton-primary"], [data-testid="stBaseLinkButton-primary"] {{
  background: var(--tan) !important; border: 1px solid var(--tan) !important; color: var(--tan-text) !important;
  font-weight: 600 !important; border-radius: 8px !important; }}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseLinkButton-primary"]:hover {{ background: var(--tan-hover) !important; }}
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseLinkButton-primary"] p {{ color: var(--tan-text) !important; font-weight: 600; }}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseLinkButton-secondary"] {{
  background: #fff !important; border: 1px solid var(--border) !important; color: var(--ink) !important;
  border-radius: 8px !important; }}
[data-testid="stBaseButton-tertiary"] p {{ color: var(--maroon); text-decoration: underline; font-size: .85rem; }}
[data-testid="stFormSubmitButton"] button {{ background: var(--tan) !important; border-color: var(--tan) !important;
  color: var(--tan-text) !important; font-weight: 600; border-radius: 8px; }}
a.linkish {{ color: var(--maroon) !important; font-weight: 600; font-size: .92rem; text-decoration: underline; }}
.book-link {{ color: var(--link); font-weight: 600; font-size: .85rem; }}

/* ---------- pills (st.pills / st.segmented_control) ---------- */
[data-testid="stBaseButton-pillsActive"], [data-testid="stBaseButton-segmented_controlActive"] {{
  background: var(--tan) !important; border-color: var(--tan) !important; color: var(--tan-text) !important; font-weight: 600; }}
[data-testid="stBaseButton-pillsActive"] p, [data-testid="stBaseButton-segmented_controlActive"] p {{ color: var(--tan-text) !important; }}
[data-testid="stBaseButton-pills"], [data-testid="stBaseButton-segmented_control"] {{ background: #fff !important; }}
button[data-variant="segmented_control"], button[data-variant="pills"] {{ background: #fff !important; color: var(--ink) !important;
  border-color: var(--border) !important; }}
button[data-variant="segmented_control"][aria-checked="true"], button[data-variant="pills"][aria-checked="true"] {{
  background: var(--tan) !important; border-color: var(--tan) !important; color: var(--tan-text) !important; font-weight: 600; }}
button[data-variant][aria-checked="true"] p {{ color: var(--tan-text) !important; }}

/* ---------- form fields ---------- */
[data-baseweb="select"] > div, [data-baseweb="input"], .stDateInput input, .stTextInput input {{ background: #fff !important; }}
label p {{ font-weight: 600 !important; font-size: .82rem !important; }}

/* ---------- fees grid / chips / reviews ---------- */
.fees-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: .35rem; margin: .3rem 0; }}
.fee {{ background: var(--page-bg); border-radius: 8px; padding: .3rem .55rem; }}
.fee .k {{ color: var(--muted); font-size: .72rem; }}
.fee .v {{ font-weight: 700; font-size: .85rem; }}
.fee .v.unknown {{ color: var(--muted); font-weight: 500; font-style: italic; }}
.fee.wide {{ grid-column: 1 / -1; order: 1; }}
.fee-row {{ display: flex; justify-content: space-between; gap: 1rem; font-size: .8rem; padding: .12rem 0;
  border-bottom: 1px solid rgba(0, 0, 0, .07); }}
.fee-row:last-of-type {{ border-bottom: 0; }}
.fee-note {{ color: var(--muted); font-size: .7rem; line-height: 1.3; margin-top: .2rem; }}
.recent {{ background: var(--cream); border-radius: 8px; padding: .45rem .7rem; font-size: .8rem; }}
.chip {{ display: inline-flex; align-items: center; gap: .3rem; background: var(--cream); border-radius: 999px;
  padding: .18rem .6rem; font-size: .78rem; font-weight: 600; margin: 0 .3rem .3rem 0; }}
.amen {{ background: var(--panel); border-radius: 10px; padding: .5rem .65rem; height: 100%; min-height: 72px; }}
.amen .k {{ color: var(--muted); font-size: .75rem; }}
.amen .v {{ font-weight: 700; font-size: .92rem; margin-top: .1rem; }}
.amen .v.unknown {{ color: var(--muted); font-weight: 500; font-style: italic; }}
.typical {{ display: inline-block; font-size: .7rem; color: var(--maroon); background: var(--cream);
  border-radius: 4px; padding: .05rem .35rem; margin-left: .3rem; font-weight: 600; }}
.stars {{ font-weight: 700; }}
.rule {{ border: 0; border-top: 1px solid var(--border); margin: 1.2rem 0; }}

/* ---------- results table ---------- */
.rt-head {{ color: var(--muted); font-size: .8rem; font-weight: 600; padding: .4rem 0; }}
[class*="st-key-rthead"] {{ background: var(--footer-bg); padding: 0 .8rem !important; }}
.logo-tile {{ width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center;
  font-weight: 800; color: #fff; font-size: .85rem; font-family: 'Nunito', sans-serif; }}
.logo-img {{ width: 36px; height: 36px; border-radius: 8px; object-fit: contain; background: #fff; border: 1px solid var(--border); }}
.r-main {{ font-weight: 700; font-size: .88rem; }}
.r-sub {{ color: var(--muted); font-size: .76rem; line-height: 1.3; }}
.r-price {{ font-weight: 700; font-size: 1.1rem; }}
.per-trav {{ color: var(--muted); font-size: .75rem; }}

/* ---------- matrix ---------- */
.mx-img {{ height: 150px; }}
[class*="st-key-card_mx"] [data-testid="stBaseButton-primary"] {{ border-radius: 999px !important; min-height: 34px; }}
[class*="st-key-card_mx"] {{ background: var(--card-bg); }}
.mod-drop {{ color: var(--maroon); font-size: .8rem; font-weight: 700; margin-left: .2rem; }}
[class*="st-key-tileempty"] {{ border: 1.5px dashed var(--border); border-radius: 12px; background: #FFFDF8;
  padding: 1rem 1.1rem !important; height: 100%; }}
[class*="st-key-tileempty"] .mod-route {{ font-size: 1rem; }}
/* routes table (airline detail) */
[class*="st-key-routespanel"] {{ border: 1px solid var(--border); border-radius: 12px; background: #fff; overflow: hidden;
  gap: 0 !important; margin-top: .3rem; }}
.rp-head {{ background: var(--cream); display: flex; justify-content: space-between; align-items: baseline; gap: 1rem;
  padding: .4rem .8rem; font-size: .9rem; }}
.rp-head span {{ color: var(--maroon); font-size: .76rem; }}
.rp-hint {{ color: var(--muted); font-size: .76rem; padding: .3rem .8rem; }}
/* Each route row is one big button: an invisible st.button stretched over the row's text. */
[class*="st-key-routerow"] {{ position: relative; border-top: 1px solid var(--border); gap: 0 !important; }}
[class*="st-key-routerow"]:hover {{ background: #FBF4EA; }}
.rp-row {{ display: grid; grid-template-columns: 1.65fr 1.1fr .85fr auto; gap: .5rem; align-items: center;
  font-size: .8rem; padding: .38rem .8rem; }}
.rp-row .num {{ text-align: right; white-space: nowrap; }}
[class*="st-key-routerow"] [data-testid="stElementContainer"]:has(button),
[class*="st-key-routerow"] [data-testid="stButton"], [class*="st-key-routerow"] [data-testid="stButton"] > div {{
  position: absolute; inset: 0; width: 100% !important; height: 100%; margin: 0; padding: 0; }}
[class*="st-key-routerow"] [data-testid="stButton"] button {{ width: 100%; height: 100%; min-height: 0; padding: 0;
  background: transparent !important; border: 0 !important; }}
[class*="st-key-routerow"] [data-testid="stButton"] button p {{ font-size: 0 !important; }}
[class*="st-key-routespanel"] > [data-testid="stElementContainer"] [data-testid="stBaseButton-tertiary"] {{ margin: .25rem .8rem .35rem; }}
[class*="st-key-routespanel"] [data-testid="stBaseButton-tertiary"] p {{ color: var(--muted); font-size: .78rem; }}
/* inline label + segmented control */
.inline-lbl {{ color: var(--muted); font-size: .84rem; }}
[class*="st-key-inlineseg"] {{ flex-wrap: nowrap !important; }}
.mx-name {{ font-weight: 700; font-size: .98rem; margin-top: 0; }}
.mx-n {{ color: var(--muted); font-size: .82rem; margin-top: .05rem; }}
.mod-label {{ color: var(--muted); font-size: .72rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }}
.mod-route {{ font-weight: 700; margin-top: .3rem; }}
.mod-price {{ font-weight: 700; font-size: 1.15rem; }}
.mod-meta {{ color: var(--muted); font-size: .78rem; }}
.news li, .routes li {{ font-size: .85rem; margin-bottom: .3rem; }}

/* ---------- footer ---------- */
.as-footer {{ background: var(--footer-bg); border-top: 1px solid var(--border); margin-top: 1.5rem;
  padding-top: 1rem; padding-bottom: .9rem; font-size: .8rem; }}
.as-footer .cols {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; }}
.as-footer h5 {{ font-size: .88rem; font-weight: 700; margin: 0 0 .5rem; padding: 0 !important; color: var(--ink); }}
.as-footer .cols div > div {{ margin-bottom: .25rem; color: var(--muted); }}
.as-footer a {{ color: var(--link); }}
.as-footer .disc {{ border-top: 1px solid var(--border); margin-top: 1rem; padding-top: .8rem; color: var(--muted); font-size: .84rem; }}
.as-footer.short {{ padding-top: .8rem; padding-bottom: .8rem; }}
.as-footer.short .disc {{ border-top: 0; margin: 0; padding: 0; }}

/* ---------- equal-size cards ---------- */
/* Every card in a grid row stretches to the tallest; actions pin to the bottom.
   DOM: stColumn > stVerticalBlock > stLayoutWrapper > card container. */
[data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [class*="st-key-card"]),
[data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [class*="st-key-tile"]) {{
  display: flex; flex-direction: column; }}
[data-testid="stColumn"] > [data-testid="stVerticalBlock"]:has(> [data-testid="stLayoutWrapper"] > [class*="st-key-card"]),
[data-testid="stColumn"] > [data-testid="stVerticalBlock"]:has(> [data-testid="stLayoutWrapper"] > [class*="st-key-tile"]),
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-card"]),
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-tile"]) {{ flex: 1 1 auto; }}
[class*="st-key-card"], [class*="st-key-tile"] {{ height: 100%; flex: 1 1 auto; justify-content: flex-start; }}
[class*="st-key-card"] > :last-child:not(:first-child), [class*="st-key-tile"] > :last-child:not(:first-child) {{ margin-top: auto; }}
/* A row with an open dropdown (Cabin experience, Fare & upgrades, Price trend) stops stretching, so the other cards in it
   keep exactly the layout they had: only the opened card grows. */
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] :is([class*="st-key-cxpanel"], .up-total, [class*="st-key-trendbox"] .tc)) {{
  align-items: flex-start; }}
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] :is([class*="st-key-cxpanel"], .up-total, [class*="st-key-trendbox"] .tc))
  > [data-testid="stColumn"] :is([class*="st-key-card"], [class*="st-key-tile"]) {{ height: auto; flex: 0 0 auto; }}
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] :is([class*="st-key-cxpanel"], .up-total, [class*="st-key-trendbox"] .tc))
  > [data-testid="stColumn"] :is([class*="st-key-card"], [class*="st-key-tile"]) > :last-child {{ margin-top: 0; }}
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] :is([class*="st-key-cxpanel"], .up-total, [class*="st-key-trendbox"] .tc))
  > [data-testid="stColumn"] :is([data-testid="stVerticalBlock"], [data-testid="stLayoutWrapper"]) {{ flex: 0 0 auto; }}
/* Fixed text heights so cards match across rows too. */
.fc-route, .mx-name {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }}
.fc-top > :last-child, .badge-drop, .badge-track {{ flex-shrink: 0; white-space: nowrap; }}

/* ---------- − value + steppers ---------- */
.stp-label {{ font-weight: 600; font-size: .82rem; margin-bottom: -.55rem; line-height: 1.6; }}
[class*="st-key-stepbox"] {{ background: #fff; border: 1px solid var(--border); border-radius: 8px;
  padding: 3px 4px; min-height: 40px; flex-wrap: nowrap !important; }}
[class*="st-key-stepbox"] button {{ width: 32px; min-width: 32px; height: 32px; min-height: 32px; padding: 0 !important;
  border-radius: 50% !important; background: var(--cream) !important; border: 1px solid var(--tan) !important; }}
[class*="st-key-stepbox"] button p {{ font-size: 1.15rem !important; font-weight: 700; color: var(--maroon) !important;
  text-decoration: none !important; line-height: 1; }}
[class*="st-key-stepbox"] button:disabled {{ opacity: .35; }}
[class*="st-key-stepbox"] button:hover:not(:disabled) {{ background: var(--tan) !important; }}
[class*="st-key-stepbox"] [data-testid="stMarkdownContainer"] p,
[class*="st-key-stepbox"] [data-testid="stMarkdownContainer"] {{ margin: 0 !important; }}
.stp-val {{ margin: 0; line-height: 32px; text-align: center; font-size: .9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}

/* ---------- V2: travelers popover + bag boxes ---------- */
[data-testid="stPopover"] button {{ background: #fff !important; border: 1px solid var(--border) !important;
  border-radius: 8px !important; min-height: 36px; justify-content: space-between; }}
[data-testid="stPopover"] button p {{ font-size: .9rem; }}
[data-testid="stPopoverBody"] {{ border: 1.5px solid var(--maroon) !important; border-radius: 12px !important;
  min-width: 300px; background: #fff; }}
[class*="st-key-partyrow"] {{ background: var(--page-bg); border: 1px solid var(--border); border-radius: 10px;
  padding: .45rem .6rem !important; flex-wrap: nowrap !important; }}
.pr-name {{ display: flex; align-items: center; gap: .45rem; font-size: .84rem; line-height: 1.15; }}
.pr-age {{ color: var(--muted); font-size: .7rem; font-weight: 400; }}
[class*="st-key-bagbox"] {{ background: var(--cream); background: #FBF4EA; border: 1px solid #EBDCC6; border-radius: 10px;
  padding: .2rem .45rem .2rem .6rem !important; min-height: 42px; flex-wrap: nowrap !important; }}
[class*="st-key-pm_"] {{ flex-wrap: nowrap !important; gap: .45rem !important; }}
[class*="st-key-pm_"] button {{ width: 28px; min-width: 28px; height: 28px; min-height: 28px; padding: 0 !important;
  border-radius: 50% !important; background: #fff !important; border: 1px solid var(--tan) !important; }}
[class*="st-key-pm_"] button p {{ font-size: 1.1rem !important; font-weight: 700; color: var(--ink) !important;
  text-decoration: none !important; line-height: 1; }}
[class*="st-key-pm_"] button:disabled {{ opacity: .35; border-color: var(--border) !important; }}
[class*="st-key-pm_"] button:hover:not(:disabled) {{ background: var(--cream) !important; }}
.pm-val {{ min-width: 1.2rem; text-align: center; font-weight: 700; line-height: 28px; height: 28px; }}
[class*="st-key-pm_"] > div {{ display: flex; align-items: center; }}
[class*="st-key-pm_"] [data-testid="stElementContainer"] {{ margin: 0 !important; }}
.pr-ico, .bag-ico {{ display: inline-flex; color: var(--maroon); }}
.nowrap {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
[class*="st-key-legrow"] button {{ white-space: nowrap; }}
[class*="st-key-legrow"] .r-main.nowrap {{ overflow: visible; text-overflow: clip; }}
.pm-val, [class*="st-key-pm_"] [data-testid="stMarkdownContainer"] p {{ margin: 0 !important; }}

/* ---------- V2: mode cards ---------- */
[class*="st-key-modecard"] button {{ background: #fff !important; border: 1px solid var(--border) !important;
  border-radius: 10px !important; text-align: left; justify-content: flex-start; padding: .4rem .75rem !important;
  min-height: 50px; }}
[class*="st-key-modecard"] button p {{ font-size: .82rem; color: var(--muted); text-align: left; }}
[class*="st-key-modecard"] button > div, [class*="st-key-modecard"] button [data-testid="stMarkdownContainer"] {{
  justify-content: flex-start !important; width: 100%; text-align: left; }}
[class*="st-key-modecard"] button strong {{ font-size: .95rem; color: var(--ink); }}
[class*="st-key-modecardon"] button {{ background: #FFF9EC !important; border: 2px solid var(--maroon) !important; }}

/* ---------- V2: card bag chip ---------- */
.bag-chip {{ display: inline-flex; align-items: center; gap: .35rem; margin-top: .5rem; background: var(--cream);
  color: var(--ink); border-radius: 999px; padding: .22rem .7rem .22rem .55rem; font-size: .74rem; font-weight: 700;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }}
.bag-chip-ico {{ display: inline-flex; color: var(--ink); flex-shrink: 0; }}
.bag-chip-ico svg {{ width: 13px; height: 13px; }}

/* ---------- V2: round trip · separate legs ---------- */
.step-h {{ display: flex; gap: .7rem; align-items: center; margin: .6rem 0 .5rem; scroll-margin-top: 1rem; }}
.step-n {{ background: var(--maroon); color: #fff; border-radius: 50%; width: 30px; height: 30px; display: flex;
  align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0; }}
[class*="st-key-legrow"] {{ border: 1px solid var(--border); border-radius: 10px; background: #fff;
  padding: .4rem .6rem !important; margin-bottom: .1rem; }}
[class*="st-key-legrowon"] {{ background: #FFF9EC; border: 2px solid var(--maroon); }}
[class*="st-key-legrow"] [data-testid="stBaseButton-tertiary"] p {{ font-size: 1.35rem !important; color: var(--maroon) !important;
  text-decoration: none !important; }}
.sel-txt {{ color: var(--maroon); font-weight: 700; font-size: .8rem; }}
[class*="st-key-legrow"] .chip {{ font-size: .72rem; margin-bottom: .2rem; }}
.leg-card {{ background: var(--page-bg); border: 1px solid var(--border); border-radius: 10px; padding: .6rem .75rem;
  margin-top: .55rem; }}
.leg-lbl {{ color: var(--maroon); font-weight: 700; font-size: .72rem; letter-spacing: .05em; }}
.buy {{ font-size: .84rem; margin: .2rem 0; }}
.buy.ok {{ color: var(--ink); }}
.buy.unk {{ color: var(--muted); font-style: italic; }}
.bs-row {{ display: flex; justify-content: space-between; font-size: .85rem; margin: .2rem 0; gap: .5rem; }}
.bs-total {{ display: flex; justify-content: space-between; font-weight: 700; font-size: 1.02rem;
  border-top: 1px solid var(--border); padding-top: .45rem; margin-top: .4rem; }}
.st-key-softcard_rtsum {{ border: 1.5px solid var(--maroon) !important; position: sticky; top: 1rem; }}

/* ---------- V2: round trip · bundles ---------- */
[class*="st-key-bundlecard"] {{ border: 1px solid var(--border); border-radius: 12px; background: #fff;
  padding: 0 0 .9rem !important; overflow: hidden; margin-bottom: .4rem; }}
[class*="st-key-bundlecardhl"] {{ border: 1.5px solid var(--maroon); }}
[class*="st-key-bundlecard"] > div:not(:first-child) {{ padding-left: 1rem; padding-right: 1rem; }}
.bc-head {{ background: var(--cream); display: flex; justify-content: space-between; gap: 1rem; padding: .55rem 1rem;
  font-size: .76rem; flex-wrap: wrap; }}
.bc-tag {{ font-weight: 800; letter-spacing: .04em; color: var(--ink); }}
.bc-score {{ color: var(--maroon); cursor: help; }}
.bc-price {{ font-weight: 800; font-size: 1.6rem; }}
.bl-row {{ display: flex; align-items: center; gap: .6rem; margin: .3rem 0 .25rem; }}
.bl-t {{ display: flex; flex-direction: column; line-height: 1.1; }}
.bl-t b {{ font-size: 1.05rem; white-space: nowrap; }}
.bl-t span {{ color: var(--muted); font-size: .72rem; }}
.bl-line {{ flex: 1; border-top: 1.5px dashed var(--tan); height: 0; position: relative; text-align: center;
  color: var(--maroon); font-size: .85rem; line-height: 0; }}
[class*="st-key-bundledetail"] {{ background: var(--footer-bg); border-radius: 10px; padding: .7rem .85rem !important; }}
table.cmp {{ width: 100%; border-collapse: collapse; font-size: .84rem; }}
table.cmp th {{ color: var(--maroon); font-size: .72rem; text-align: left; letter-spacing: .04em; padding: .3rem 0; }}
table.cmp td {{ border-top: 1px solid var(--border); padding: .45rem .3rem .45rem 0; vertical-align: top; }}
table.cmp td:first-child {{ color: var(--muted); }}
table.cmp td .chip {{ font-size: .7rem; }}

/* ---------- V3: fare / deal cards ---------- */
.v3-price {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: .2rem .5rem; margin-top: .15rem; }}
.v3-price .fc-price {{ font-size: 1.55rem; font-weight: 800; letter-spacing: -.02em; line-height: 1.05;
  color: var(--ink); font-variant-numeric: tabular-nums; }}
.v3-price .est {{ font-size: .75rem; color: var(--muted); }}
.v3-unit {{ color: var(--muted); font-size: .85rem; font-weight: 500; white-space: nowrap; display: inline-flex;
  align-items: baseline; gap: .45rem; }}
.v3-route {{ display: flex; align-items: center; justify-content: space-between; gap: .5rem; margin-top: .1rem; }}
.v3-route .fc-route {{ font-size: 1.02rem; }}
.v3-legs {{ display: grid; grid-template-columns: auto 1fr; column-gap: .6rem; row-gap: .05rem; font-size: .83rem;
  margin-top: .35rem; }}
.v3-leg {{ color: var(--maroon); font-weight: 700; font-size: .7rem; letter-spacing: .02em; line-height: 1.7; }}
.mod-top {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .15rem .5rem; margin-bottom: .35rem; }}
.mod-note {{ color: var(--muted); font-size: .68rem; white-space: nowrap; }}
.mod-tag {{ background: var(--cream); color: var(--maroon); font-size: .66rem; font-weight: 700; letter-spacing: .02em;
  text-transform: uppercase; border-radius: 6px; padding: .15rem .5rem; white-space: nowrap; flex-shrink: 0; }}
/* bags box + Upgrades (V6 p15) */
[class*="st-key-faresbox"] {{ background: #FFFDF8; border: 1px solid #EBDCC6; border-radius: 10px; padding: .4rem .55rem !important; }}
[class*="st-key-baghead"] {{ flex-wrap: nowrap !important; justify-content: space-between; }}
[class*="st-key-baghead"] [data-testid="stElementContainer"]:has(.bag-chip) {{ flex: 1 1 auto; min-width: 0; width: auto !important; }}
[class*="st-key-baghead"] [data-testid="stElementContainer"]:has(button) {{ flex: 0 0 auto; width: auto !important; }}
[class*="st-key-baghead"] button, [class*="st-key-trendrow"] button {{ min-height: 0 !important; padding: .1rem .15rem !important; white-space: nowrap; }}
[class*="st-key-baghead"] button p {{ color: var(--maroon) !important; font-weight: 700; font-size: .8rem; text-decoration: none !important; }}
.bag-chip.v3 {{ margin: 0; white-space: normal; line-height: 1.25; border-radius: 12px; padding: .3rem .65rem .3rem .55rem;
  font-size: .73rem; }}
.bag-chip.v3.on {{ background: #E8F2EA; }}
.bag-chip.v3.off {{ background: var(--panel); }}
[class*="st-key-uprow"] {{ flex-wrap: nowrap !important; justify-content: space-between; }}
[class*="st-key-uprow"] [data-testid="stElementContainer"] {{ width: auto !important; flex: 0 1 auto; }}
[class*="st-key-uprow"] [data-testid="stCheckbox"] label {{ align-items: center; }}
[class*="st-key-uprow"] [data-testid="stCheckbox"] p {{ font-size: .84rem; }}
.up-line {{ display: flex; align-items: center; gap: .5rem; font-size: .84rem; line-height: 1.25; }}
.up-box {{ flex: 0 0 auto; width: 16px; height: 16px; border: 1px solid #C9CDD3; border-radius: 4px; background: #fff;
  color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: .68rem; font-weight: 800; }}
.up-box.in {{ background: #1E7B34; border-color: #1E7B34; }}
.up-lbl {{ flex: 1 1 auto; min-width: 0; }}
.up-val {{ font-size: .82rem; font-weight: 700; text-align: right; white-space: nowrap; }}
.up-val.in {{ color: #1E7B34; }}
.up-hint {{ color: var(--muted); font-size: .73rem; line-height: 1.3; }}
.v3-up {{ color: #B42318; font-weight: 700; font-size: .8rem; white-space: nowrap; }}
.fare-more {{ margin-top: .3rem; font-size: .78rem; }}
.fare-more summary {{ cursor: pointer; color: var(--maroon); font-weight: 700; }}
.fare-more .up-row {{ font-size: .78rem; padding: .3rem 0; }}
.fare-more .up-sub {{ font-size: .7rem; padding-bottom: .25rem; }}
.up-head {{ font-weight: 700; font-size: .9rem; margin-bottom: .35rem; }}
.up-row {{ display: flex; justify-content: space-between; gap: 1rem; font-size: .85rem; padding: .4rem 0;
  border-top: 1px solid var(--border); white-space: nowrap; }}
.up-row > span:first-child {{ white-space: normal; }}
.up-sub {{ color: var(--muted); font-size: .75rem; line-height: 1.35; padding-bottom: .4rem; max-width: 26rem; }}
.fare-block {{ margin: .6rem 0; }}
.fare-block .credit {{ margin-top: .3rem; }}
/* card price-trend row + pop-up (V6 p9) */
[class*="st-key-trendrow"] {{ border: 1px solid var(--border); border-radius: 10px; background: #fff; padding: .3rem .55rem !important;
  flex-wrap: nowrap !important; justify-content: space-between; }}
[class*="st-key-trendrow"] [data-testid="stElementContainer"] {{ width: auto !important; flex: 0 1 auto; min-width: 0; }}
[class*="st-key-trendrow"] [data-testid="stElementContainer"]:has(button) {{ flex: 0 0 auto; }}
[class*="st-key-trendrow"] button p {{ font-size: .72rem !important; color: var(--muted) !important; text-decoration: none !important;
  white-space: nowrap; overflow: visible; text-overflow: clip; }}
[class*="st-key-trendrow"] button > div, [class*="st-key-trendrow"] [data-testid="stMarkdownContainer"]:has(> p) {{ overflow: visible; }}
.tr-sum {{ display: flex; align-items: center; gap: .45rem; }}
[class*="st-key-trendrow"] .tr-mini {{ width: 44px; }}
[class*="st-key-trendrow"] .tr-pct {{ white-space: nowrap; font-size: .74rem; }}
.tr-mini {{ flex-shrink: 0; }}
.tc-grid {{ display: grid; grid-template-columns: auto 1fr; column-gap: .55rem; }}
.tc-y {{ display: flex; flex-direction: column; justify-content: space-between; color: var(--muted); font-size: .72rem; padding: .35rem 0; }}
.tc-axis {{ padding-left: 2.6rem; }}
.ts-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: .5rem; }}
.ts-tile {{ background: var(--panel); border-radius: 8px; padding: .5rem .7rem; }}
.ts-tile .k {{ color: var(--muted); font-size: .74rem; }}
.ts-tile .v {{ font-weight: 700; font-size: 1rem; }}
.ts-tile .v.down {{ color: #1E7B34; }}
/* pop-ups: maroon band with a labeled Close */
[data-testid="stDialog"] [role="dialog"] {{ background: var(--page-bg); overflow-x: hidden; }}
[data-testid="stDialog"] [role="dialog"] > h2 {{ background: var(--maroon); border-radius: .75rem .75rem 0 0; min-height: 64px;
  margin-bottom: .9rem; }}
[data-testid="stDialog"] [role="dialog"] > h2, [data-testid="stDialog"] [role="dialog"] > h2 * {{ color: #fff !important; }}
[data-testid="stDialog"] button[aria-label="Close"] {{ z-index: 2; border: 1px solid #fff; border-radius: 8px; width: auto; height: auto;
  padding: .3rem .6rem; gap: .35rem; display: inline-flex; align-items: center; background: transparent; }}
[data-testid="stDialog"] button[aria-label="Close"]::before {{ content: "Close"; font-size: .85rem; font-weight: 700; color: #fff; }}
[data-testid="stDialog"] button[aria-label="Close"] svg, [data-testid="stDialog"] button[aria-label="Close"] svg path {{ color: #fff; fill: #fff; }}
[data-testid="stDialog"] .tc-plot {{ height: 240px; }}
[data-testid="stDialog"] .tc-cur {{ background: var(--page-bg); }}
@media (max-width: 760px) {{ .ts-grid {{ grid-template-columns: 1fr 1fr; }} }}
.fee.cab {{ padding: .5rem .6rem; min-height: 72px; }}
.fee.cab .chip {{ font-size: .72rem; margin: .15rem .2rem 0 0; }}
.tr-txt {{ display: flex; flex-direction: column; line-height: 1.25; min-width: 0; flex: 1; }}
.tr-pct {{ font-weight: 700; font-size: .8rem; }}
.tr-pct.down, .tc-delta.down {{ color: #1E7B34; }}
.tr-pct.up, .tc-delta.up {{ color: var(--maroon); }}
.tr-pct.flat, .tc-delta.flat {{ color: var(--muted); }}
.tr-hint {{ color: var(--muted); font-size: .72rem; }}
.tc {{ position: relative; }}
.tc-cur {{ height: 2.6rem; background: #fff; }}
.tc-cur b {{ font-size: .95rem; }}
.tc-delta {{ font-size: .74rem; font-weight: 600; }}
.tc-plot {{ position: relative; height: 90px; background: #FBF7F2; border-radius: 6px; }}
.tc-plot svg {{ width: 100%; height: 100%; display: block; overflow: visible; }}
.tc-hits {{ position: absolute; inset: 0; display: flex; cursor: crosshair; }}
.tc-hit {{ flex: 1 1 0; height: 100%; }}
.tc-hit > div {{ display: none; position: absolute; pointer-events: none; }}
.tc-hit:hover > div {{ display: block; }}
.tc-lbl {{ top: -2.6rem; left: 0; right: 0; }}
.tc-vl {{ top: 0; bottom: 0; width: 1px; background: var(--maroon); }}
.tc-dot {{ position: absolute; width: 11px; height: 11px; border-radius: 50%; background: var(--maroon);
  border: 2px solid #fff; box-shadow: 0 0 0 1px var(--maroon); transform: translate(-50%, -50%); }}
.tc-plot:hover .tc-last {{ display: none; }}
.tc-axis {{ display: flex; justify-content: space-between; color: var(--muted); font-size: .7rem; margin-top: .25rem; }}
/* Home: trip type + bags toggles */
.st-key-hometoggles {{ flex-wrap: nowrap !important; gap: .6rem !important; }}
.st-key-hometoggles > div {{ width: auto !important; }}
/* Airline deal tiles: Book now at the bottom */
[class*="st-key-tile_"] [data-testid="stLinkButton"], [class*="st-key-tilehl_"] [data-testid="stLinkButton"] {{ margin-top: .2rem; }}
/* Narrow airline deal tiles: wrap instead of truncating, tag above the route, bags box stacks */
[class*="st-key-tile"] .v3-route {{ flex-wrap: wrap; gap: .25rem .5rem; }}
[class*="st-key-tile"] .fc-route, [class*="st-key-tile"] .fc-line, [class*="st-key-tile"] .fc-meta {{
  white-space: normal; overflow: visible; }}

/* ---------- V4: round trip summary (separate legs) ---------- */
.sum-h {{ font-weight: 700; font-size: .9rem; margin-bottom: .25rem; }}
.buy2 {{ display: flex; gap: .45rem; font-size: .84rem; margin: .22rem 0; line-height: 1.35; }}
.buy2 .bi {{ font-weight: 800; width: .9rem; flex-shrink: 0; text-align: center; }}
.buy2.yes .bi {{ color: #1E7B34; }}
.buy2.no .bi {{ color: #B42318; }}
.buy2.unk {{ color: var(--muted); font-style: italic; }}
.sum-total {{ display: flex; justify-content: space-between; align-items: baseline; font-weight: 700; }}
.sum-price {{ font-size: 1.4rem; font-weight: 800; color: var(--ink); }}

/* ---------- V4: bundles table ---------- */
.st-key-restable_bundles {{ background: #fff; }}
[class*="st-key-bundlerow"] {{ border-top: 1px solid var(--border); padding: .5rem .8rem !important; background: var(--page-bg); }}
[class*="st-key-bundlerowopen"] {{ background: #fff; }}
[class*="st-key-bundlerowopen"] [data-testid="stBaseButton-secondary"] {{ border-color: var(--tan) !important; }}
[class*="st-key-bundlerow"] [class*="st-key-bundledetail"] {{ margin: .4rem 0 .1rem; }}
.st-key-restable_bundles .rt-head {{ white-space: nowrap; }}
table.cmp, table.cmp th, table.cmp td {{ border-left: 0 !important; border-right: 0 !important; }}
table.cmp {{ border: 0 !important; }}
table.cmp tr:first-child th {{ border-top: 0 !important; border-bottom: 1px solid var(--border) !important; }}
table.cmp tr {{ background: transparent !important; }}
.bt-tags {{ display: flex; flex-wrap: wrap; gap: .3rem; margin-bottom: .25rem; }}
.btag {{ font-size: .68rem; font-weight: 700; border-radius: 999px; padding: .1rem .5rem; white-space: nowrap; cursor: help;
  border: 1px solid transparent; }}
.btag.tag-best {{ background: var(--tan); color: var(--tan-text); }}
.btag.tag-short {{ background: #fff; color: var(--maroon); border-color: var(--maroon); }}
.btag.tag-low {{ background: #E8F2EA; color: #1E7B34; }}
.bt-times {{ margin-top: 0; font-size: .8rem; row-gap: .1rem; }}
.bt-price {{ font-size: 1.2rem; font-weight: 800; color: var(--ink); line-height: 1.1; }}
.bt-logos {{ display: flex; flex-direction: column; gap: .25rem; }}
.bt-logos .logo-tile, .bt-logos .logo-img {{ width: 32px; height: 32px; font-size: .7rem; }}

/* ---------- V4 (Nov 2026): form fields ---------- */
/* Streamlit paints inputs with the secondary background; the wireframes use white with a thin border. */
[data-testid="stSelectbox"] [role="group"], [data-testid="stTextInputRootElement"], [data-testid="stDateInputField"] {{
  background: #fff !important; border: 1px solid var(--border) !important; border-radius: 8px !important; }}
.stTextInput input:disabled {{ color: var(--ink) !important; -webkit-text-fill-color: var(--ink); opacity: 1; cursor: default; }}
[data-testid="stTextInput"] [data-testid="stWidgetLabel"], [data-testid="stTextInput"] [data-testid="stWidgetLabel"] p {{
  color: var(--ink) !important; opacity: 1 !important; }}
/* Dropdown-style popovers: label on the left, chevron on the right. */
[data-testid="stPopoverButton"] > div {{ width: 100%; justify-content: space-between; }}
[data-testid="stPopoverButton"] > div > div:first-child {{ flex: 1 1 auto; min-width: 0; justify-content: flex-start; text-align: left; }}
label p {{ font-size: .88rem !important; }}
.stp-label {{ font-size: .88rem; }}
[data-testid="stBaseButton-primary"], [data-testid="stBaseLinkButton-primary"],
[data-testid="stBaseButton-secondary"], [data-testid="stBaseLinkButton-secondary"] {{ min-height: 34px; }}
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseLinkButton-primary"] p,
[data-testid="stBaseButton-secondary"] p, [data-testid="stBaseLinkButton-secondary"] p {{ font-weight: 600; font-size: .85rem; }}
[class*="st-key-modecard"] button p {{ font-weight: 400; font-size: .8rem; }}
[class*="st-key-modecard"] button strong {{ font-weight: 700; font-size: .92rem; }}
.st-key-navrow {{ padding-bottom: 4px; }}
.st-key-navrow .st-key-navitem_active a[data-testid="stPageLink-NavLink"] p,
.st-key-navrow .st-key-navitem_active a[data-testid="stPageLink-NavLink"] span {{ font-weight: 700 !important; color: #fff !important; }}

/* ---------- V4: filter pills are rounded rectangles; Sort stays a full pill ---------- */
.st-key-panel_filters button[data-variant="pills"], .st-key-hometoggles button[data-variant="pills"] {{
  border-radius: 8px !important; min-height: 34px; padding-left: .7rem; padding-right: .7rem; }}
.st-key-panel_filters {{ background: var(--footer-bg); }}
.st-key-hometoggles button[data-variant="segmented_control"] {{ min-height: 34px; padding-left: .7rem; padding-right: .7rem; }}
[class*="st-key-inlineseg"] button[data-variant="pills"] {{ min-height: 32px; padding-left: .75rem; padding-right: .75rem; }}
.inline-lbl {{ font-size: .92rem; white-space: nowrap; }}

/* ---------- V4: card photo with credit on it ---------- */
.card-photo {{ position: relative; }}
.card-photo .credit {{ position: absolute; left: 0; right: 0; bottom: 0; margin: 0; padding: 1rem .7rem .3rem;
  background: linear-gradient(transparent, rgba(0, 0, 0, .62)); color: #fff; font-size: .68rem; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }}
.card-photo .credit a {{ color: #fff !important; text-decoration: none; }}
.card-body {{ padding: .55rem .85rem 0; }}
[class*="st-key-card"] > div:not(:first-child) {{ padding-left: .85rem; padding-right: .85rem; }}
.st-key-back_airlines p {{ color: var(--link) !important; font-size: .95rem !important; }}
[class*="st-key-softcard_fact"] {{ background: var(--footer-bg); }}

/* ---------- V4: To picker ---------- */
[data-testid="stPopoverBody"]:has([class*="st-key-destpick"]) {{ width: 440px !important; max-width: 440px !important; }}
.dest-hint {{ color: var(--muted); font-size: .76rem; line-height: 1.3; }}
.dest-n {{ color: var(--muted); font-size: .78rem; white-space: nowrap; }}
[class*="st-key-destlist"] {{ gap: 0 !important; }}
[class*="st-key-destlist"] [data-testid="stBaseButton-tertiary"] {{ justify-content: flex-start; width: 100%; min-height: 30px;
  padding: 0 .25rem; }}
[class*="st-key-destlist"] [data-testid="stBaseButton-tertiary"] p {{ color: var(--ink); text-decoration: none; font-weight: 600;
  font-size: .88rem; text-align: left; }}
[class*="st-key-destlist"] [data-testid="stBaseButton-tertiary"] > div {{ justify-content: flex-start; width: 100%; }}
[class*="st-key-destlist"] [data-testid="stBaseButton-tertiary"] [data-testid="stMarkdownContainer"] {{ text-align: left; }}
[class*="st-key-destlist"] [data-testid="stBaseButton-tertiary"]:hover {{ background: var(--page-bg); }}
[class*="st-key-destmetro"] {{ flex-wrap: nowrap !important; min-height: 32px; padding: 0 .25rem; }}
[class*="st-key-destairport"] {{ min-height: 28px; padding-left: 1.75rem; justify-content: center; }}
[class*="st-key-destlist"] label p {{ font-size: .88rem !important; font-weight: 500 !important; }}
/* Clear / Done stay pinned to the bottom of the pop-up while it scrolls (V7.2 p13) */
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-destfoot"]), [class*="st-key-destfoot"] {{
  position: sticky; bottom: 0; z-index: 3; background: #fff; }}
[class*="st-key-destfoot"] {{ flex-wrap: nowrap !important; padding: .45rem 0 .75rem; border-top: 1px solid var(--border); }}
/* No bottom padding on this pop-up, so the pinned footer sits flush with its edge and no list row shows beneath it. */
[data-testid="stPopoverBody"]:has([class*="st-key-destpick"]) {{ padding-bottom: 0 !important; }}
/* On short screens the city list shrinks (it scrolls on its own) so the whole pop-up fits without scrolling. */
[class*="st-key-destlist"] {{ height: auto !important; max-height: clamp(120px, calc(100vh - 590px), 250px) !important;
  overflow-y: auto !important; }}
[class*="st-key-destfoot"] button {{ min-height: 34px; white-space: nowrap; }}
[class*="st-key-destmetro"] label p strong {{ font-weight: 600; }}

/* ---------- V4: separate legs ---------- */
[class*="st-key-pick_"] button {{ width: 24px; height: 24px; min-height: 24px; padding: 0; border-radius: 50%;
  border: 1.5px solid var(--muted) !important; background: #fff; }}
[class*="st-key-legrow"] [class*="st-key-pick_"] button p {{ font-size: 0 !important; color: transparent !important; }}
[class*="st-key-legrowon"] [class*="st-key-pick_"] button {{ border: 2px solid var(--maroon) !important;
  background: radial-gradient(circle, var(--maroon) 0 52%, #fff 56%) !important; }}
[class*="st-key-legcard"] {{ background: var(--page-bg); border: 1px solid var(--border); border-radius: 10px;
  padding: .6rem .75rem !important; margin-top: .3rem; }}
[class*="st-key-lchead"] {{ flex-wrap: nowrap !important; }}
[class*="st-key-lchead"] [data-testid="stBaseButton-tertiary"] {{ min-height: 0; padding: 0; }}
[class*="st-key-lchead"] [data-testid="stBaseButton-tertiary"] p, .leg-card .book-link, [class*="st-key-lchead"] a.book-link {{
  color: var(--link) !important; font-size: .85rem !important; font-weight: 600; text-decoration: underline; }}
.st-key-returnslot {{ border: 1.5px dashed var(--border); border-radius: 10px; background: #fff; padding: .55rem .8rem !important; }}
.chip svg {{ flex-shrink: 0; }}
.st-key-rtbarrow {{ flex-wrap: wrap; }}
.st-key-panel_rtbar [data-testid="stBaseButton-tertiary"] p, .st-key-panel_compact [data-testid="stBaseButton-tertiary"] p {{
  font-weight: 600; font-size: .95rem; }}

/* ---------- compact layout: tighter spacing between and inside boxes ---------- */
[data-testid="stMainBlockContainer"] > div > [data-testid="stVerticalBlock"],
[data-testid="stMain"] [data-testid="stVerticalBlock"] {{ gap: .55rem; }}
[data-testid="stHorizontalBlock"] {{ gap: .6rem; }}
[data-testid="stBaseButton-primary"], [data-testid="stBaseLinkButton-primary"] {{ min-height: 34px; }}
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseLinkButton-primary"] p {{ font-size: .86rem; }}
[data-testid="stColumn"] [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] [data-testid="stLinkButton"]) {{ gap: .3rem; }}
[data-testid="stDateInputField"], [data-testid="stTextInputRootElement"], [data-testid="stSelectbox"] [role="group"] {{ min-height: 36px; height: 36px; }}
[data-testid="stTextInputField"], [data-testid="stDateInput"] input {{ font-size: .86rem; }}
[data-testid="stPopover"] button p, [data-testid="stSelectbox"] input {{ font-size: .86rem !important; }}
label p {{ font-size: .8rem !important; }}
.stp-label {{ font-size: .8rem; }}
.stp-label.field {{ margin-bottom: -.05rem; }} /* lines a popover up with the input beside it */
[data-testid="stBaseButton-primary"]:disabled {{ opacity: .5; cursor: not-allowed; }}
.st-key-panel_rtbar [data-testid="stMarkdownContainer"], .st-key-panel_compact [data-testid="stMarkdownContainer"] {{ margin-bottom: 0 !important; }}
.st-key-panel_rtbar [data-testid="stMarkdownContainer"] p, .st-key-panel_compact [data-testid="stMarkdownContainer"] p {{ margin-bottom: 0; }}
[class*="st-key-legrow"] .r-main.nowrap {{ font-size: .82rem; }}
[class*="st-key-legrow"] [data-testid="stHorizontalBlock"] {{ gap: .5rem; }}
[class*="st-key-legrow"] [data-testid="stBaseButton-secondary"] {{ padding-left: .4rem; padding-right: .4rem; }}
[class*="st-key-legrow"] [data-testid="stBaseButton-secondary"] p {{ font-size: .8rem; white-space: nowrap; overflow: visible; }}
[class*="st-key-legrow"] [data-testid="stBaseButton-secondary"] [data-testid="stMarkdownContainer"] {{ overflow: visible; }}
[class*="st-key-legrow"] .r-sub {{ display: block; }}
.credit {{ font-size: .68rem; }}
.bag-chip.v3 {{ font-size: .68rem; padding: .2rem .5rem .2rem .45rem; }}
.card-photo .credit {{ font-size: .62rem; padding: .7rem .6rem .2rem; }}
[class*="st-key-faresbox"] {{ padding: .22rem .4rem !important; }}
[class*="st-key-baghead"] button p {{ font-size: .74rem !important; }}
.tr-pct {{ font-size: .74rem; }}
.tr-hint {{ font-size: .66rem; }}
.chip {{ font-size: .7rem; padding: .1rem .45rem; margin: 0 .2rem .15rem 0; }}
.step-h {{ margin: .3rem 0 .25rem; }}
.step-n {{ width: 26px; height: 26px; font-size: .85rem; }}
.news li, .routes li {{ font-size: .8rem; margin-bottom: .15rem; }}
.mx-img {{ height: 115px; }}
[class*="st-key-tileempty"] {{ padding: .7rem .85rem !important; height: auto; }}
.fee .v {{ font-size: .8rem; }}
.fee .k {{ font-size: .68rem; }}
.recent {{ padding: .3rem .55rem; font-size: .76rem; }}
a.linkish {{ font-size: .84rem; }}

/* ---------- V7: Fare & upgrades, Cabin experience and Price trend dropdowns ---------- */
.up-base {{ justify-content: space-between; padding-top: .15rem; }}
.up-base .up-lbl {{ font-weight: 500; }}
.up-sec {{ color: var(--maroon); font-weight: 700; font-size: .7rem; letter-spacing: .05em; text-transform: uppercase; margin-top: .1rem; }}
.up-total {{ display: flex; justify-content: space-between; font-weight: 700; font-size: .88rem;
  border-top: 1px solid var(--border); padding-top: .35rem; margin-top: .1rem; }}
.bag-chip.v3.cx {{ background: var(--cream); }}
[class*="st-key-faresbox"], [class*="st-key-trendbox"], [class*="st-key-cabinpanel"], [class*="st-key-farepanel"],
[class*="st-key-bundledetail"], [class*="st-key-softcard_cabin"], [class*="st-key-card_"], [class*="st-key-resrow"],
[class*="st-key-legrow"], [class*="st-key-bundlerow"] {{ overflow: visible !important; }}
[class*="st-key-faresbox"] [data-testid="stMarkdownContainer"], [class*="st-key-cabinpanel"] [data-testid="stMarkdownContainer"],
[class*="st-key-bundledetail"] [data-testid="stMarkdownContainer"], [class*="st-key-softcard_cabin"] [data-testid="stMarkdownContainer"],
[class*="st-key-legrow"] [data-testid="stMarkdownContainer"] {{ overflow: visible; }}
.cx-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .5rem; margin-top: .35rem; }}
.cx-grid.stacked {{ grid-template-columns: 1fr 1fr; gap: .4rem; }}
.cx-grid.stacked .amen-ent {{ grid-column: 1 / -1; }}
.cx-grid .amen {{ background: var(--panel); min-height: 0; }}
.cx-grid.stacked .amen {{ padding: .4rem .5rem; }}
.cx-grid .amen .v {{ font-size: .84rem; line-height: 1.3; }}
.cx-grid.stacked .amen .v {{ font-size: .76rem; }}
.cx-grid .unknown {{ color: var(--muted); font-weight: 500; font-style: italic; }}
.cx-grid .amen-ent .chip {{ margin: .25rem .25rem 0 0; }}
.freebie-box {{ margin-top: .45rem; border: 1px solid #E9D49E; background: #FFFAEB; border-radius: 10px; padding: .4rem .6rem; }}
.freebie-box .k {{ color: var(--muted); font-size: .72rem; }}
.freebie-box .v {{ font-weight: 700; font-size: .84rem; }}
.cx-typical {{ margin-top: .3rem; }}
/* entertainment chip pop-ups (V7 p20): hover, or tap/focus on touch screens */
.chip.ent {{ position: relative; cursor: help; outline: none; }}
.chip.ent:focus-visible {{ box-shadow: 0 0 0 2px var(--maroon); }}
.chip-pop {{ display: none; position: absolute; z-index: 60; top: calc(100% + 6px); left: 0; min-width: 210px; max-width: 260px;
  grid-template-columns: auto 1fr; gap: .2rem .7rem; background: #fff; border: 1.5px solid var(--maroon); border-radius: 10px;
  padding: .45rem .6rem; box-shadow: 0 6px 18px rgba(0,0,0,.12); font-size: .76rem; font-weight: 400; white-space: normal;
  color: var(--ink); line-height: 1.3; text-align: left; }}
.chip-pop .k {{ color: var(--muted); }}
.chip-pop .v {{ font-weight: 700; }}
.chip-pop .v.unknown {{ font-weight: 500; font-style: italic; color: var(--muted); }}
.chip.ent:hover .chip-pop, .chip.ent:focus .chip-pop {{ display: grid; }}
.chip.ent:hover, .chip.ent:focus {{ z-index: 61; }}
/* row buttons under results (V7 p10) */
[class*="st-key-rowbtns"] {{ margin-top: .1rem; }}
[class*="st-key-rowbtns"] button {{ min-height: 32px; padding: .15rem .8rem; white-space: nowrap; }}
[class*="st-key-farepanel"] {{ background: var(--panel); border-radius: 10px; padding: .6rem .8rem !important; }}
[class*="st-key-farepanel"] .bag-chip.v3 {{ align-self: flex-start; }}
/* price trend dropdown on deal cards (V7 p4) */
[class*="st-key-trendbox"] {{ border: 1px solid var(--border); border-radius: 10px; background: #fff; padding: .3rem .55rem !important; }}
[class*="st-key-trendbox"] [class*="st-key-trendrow"] {{ border: 0; padding: 0 !important; background: transparent; }}
[class*="st-key-trendbox"] [class*="st-key-trendrow"] button p {{ font-size: .9rem !important; color: var(--maroon) !important; }}
[class*="st-key-trendbox"] .tr-hint {{ display: block; }}
[class*="st-key-trendbox"] .tc-cur {{ height: 2.8rem; }}
[class*="st-key-trendbox"] .tc-y {{ font-size: .64rem; }}
[class*="st-key-trendbox"] .tc-axis {{ padding-left: 2.2rem; font-size: .68rem; color: var(--muted); }}
.tr-lohi {{ color: var(--muted); font-size: .72rem; margin-top: .15rem; text-align: center; }}
.cx-imgs-h {{ font-weight: 700; font-size: .9rem; margin: .1rem 0 .3rem; }}
[class*="st-key-cxpanel"] .cx-imgs-h {{ font-size: .8rem; }}
.cx-imgs {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .4rem; }}
.cx-imgs img, .cx-imgs .img-ph {{ width: 100%; object-fit: cover; border-radius: 8px; display: block; }}
[class*="st-key-cxpanel"] .img-ph {{ font-size: .62rem; }}
[class*="st-key-cxpanel"] {{ border: 1px solid #EBDCC6; background: #FFFDF8; border-radius: 10px; padding: .45rem .55rem !important;
  overflow: visible !important; }}
[class*="st-key-cxpanel"] [data-testid="stMarkdownContainer"] {{ overflow: visible; }}
[class*="st-key-btnrow"] {{ flex-wrap: wrap; }}
.up-box.none {{ visibility: hidden; }}
.cmp-sub {{ color: var(--muted); font-size: .68rem; font-weight: 400; }}
@media (max-width: 760px) {{ .cx-grid {{ grid-template-columns: 1fr; }} .cx-grid.stacked {{ grid-template-columns: 1fr; }} }}

@media (max-width: 760px) {{
  .as-footer .cols {{ grid-template-columns: 1fr; }}
  .as-header {{ flex-direction: column; gap: .2rem; }}
}}
"""


def css():
    vars_ = " ".join(f"--{k}: {v};" for k, v in TOKENS.items())
    return _CSS.format(fonts=FONTS, vars=vars_)


def inject():
    st.markdown(f"<style>{css()}</style>", unsafe_allow_html=True)
