"""
RealScore CZ – Streamlit frontend.
All UI text is in Czech.
"""

import os
import requests
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="RealScore CZ",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _color_for_score(score: float) -> str:
    if score >= 65:
        return "#27ae60"   # green
    if score >= 40:
        return "#f39c12"   # yellow / amber
    return "#e74c3c"       # red


def _score_label(score: float) -> str:
    if score >= 65:
        return "Dobrá investice"
    if score >= 40:
        return "Průměrná investice"
    return "Riziková investice"


def _fmt_czk(val) -> str:
    if val is None:
        return "—"
    return f"{val:,.0f} Kč".replace(",", "\u202f")


def _fmt_pct(val) -> str:
    if val is None:
        return "—"
    return f"{val:.2f} %"


def _parse_price(text: str) -> float | None:
    s = text.strip().replace("\xa0", "").replace(" ", "").replace("Kč", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def api_analyze(payload: dict) -> dict | None:
    try:
        resp = requests.post(f"{BACKEND_URL}/api/analyze", json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        st.error(f"Chyba API ({resp.status_code}): {resp.json().get('detail', resp.text)}")
    except requests.exceptions.ConnectionError:
        st.error("Nelze se připojit k backendu. Ujistěte se, že FastAPI server běží.")
    except Exception as exc:
        st.error(f"Neočekávaná chyba: {exc}")
    return None



def api_get_filters(regions: list | None = None) -> dict:
    try:
        params = [("regions", r) for r in (regions or [])]
        resp = requests.get(f"{BACKEND_URL}/api/properties/filters", params=params, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {
        "regions": [], "cities": [], "price_min": 0, "price_max": 10_000_000,
        "energy_classes": [], "yield_max": 15.0,
    }


def api_list_properties(
    sort_by: str = "created_at",
    order: str = "desc",
    offset: int = 0,
    regions: list | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    cities: list | None = None,
    energy_classes: list | None = None,
    min_yield: float | None = None,
    ownerships: list | None = None,
) -> list[dict]:
    try:
        params: list = [
            ("sort_by", sort_by), ("order", order),
            ("limit", 200), ("offset", offset),
        ]
        for r in (regions or []):
            params.append(("regions", r))
        if price_min is not None:
            params.append(("price_min", price_min))
        if price_max is not None:
            params.append(("price_max", price_max))
        for c in (cities or []):
            params.append(("cities", c))
        for e in (energy_classes or []):
            params.append(("energy_classes", e))
        if min_yield is not None:
            params.append(("min_yield", min_yield))
        for o in (ownerships or []):
            params.append(("ownerships", o))
        resp = requests.get(f"{BACKEND_URL}/api/properties", params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


def api_count_properties(
    regions: list | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    cities: list | None = None,
    energy_classes: list | None = None,
    min_yield: float | None = None,
    ownerships: list | None = None,
) -> int:
    try:
        params: list = []
        for r in (regions or []):
            params.append(("regions", r))
        if price_min is not None:
            params.append(("price_min", price_min))
        if price_max is not None:
            params.append(("price_max", price_max))
        for c in (cities or []):
            params.append(("cities", c))
        for e in (energy_classes or []):
            params.append(("energy_classes", e))
        if min_yield is not None:
            params.append(("min_yield", min_yield))
        for o in (ownerships or []):
            params.append(("ownerships", o))
        resp = requests.get(f"{BACKEND_URL}/api/properties/count", params=params, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("total", 0)
    except Exception:
        pass
    return 0


def api_get_property(property_id: int) -> dict | None:
    try:
        resp = requests.get(f"{BACKEND_URL}/api/properties/{property_id}", timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def api_delete_all():
    try:
        requests.delete(f"{BACKEND_URL}/api/properties", timeout=10)
    except Exception:
        pass


def api_delete(property_id: int):
    try:
        requests.delete(f"{BACKEND_URL}/api/properties/{property_id}", timeout=10)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# UI components
# ---------------------------------------------------------------------------

def render_score_gauge(score: float):
    color = _color_for_score(score)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": "Celkové skóre", "font": {"size": 20}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 40],  "color": "#fdecea"},
                {"range": [40, 65], "color": "#fef9e7"},
                {"range": [65, 100], "color": "#eafaf1"},
            ],
            "threshold": {
                "line": {"color": color, "width": 4},
                "thickness": 0.75,
                "value": score,
            },
        },
    ))
    fig.update_layout(height=280, margin=dict(t=40, b=10, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)


def render_breakdown_chart(scores: dict):
    # Scoring model v2 — nové dimenze a váhy
    dimensions = {
        "Lokalita / SVL čistota (40 %)": scores["score_demographic"],
        "PENB / Energetická třída (20 %)": scores["score_economic"],
        "Vlastnictví OV/DV (15 %)": scores["score_liquidity"],
        "Fyzické parametry (15 %)": scores["score_quality"],
        "Výnosnost nájmu (10 %)": scores["score_yield"],
    }
    labels = list(dimensions.keys())
    values = list(dimensions.values())
    colors = [_color_for_score(v) for v in values]

    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker_color=colors,
        text=[f"{v:.0f}" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        title="Skóre podle dimenzí",
        xaxis=dict(range=[0, 110], title="Skóre (0–100)"),
        yaxis=dict(autorange="reversed"),
        height=320,
        margin=dict(t=50, b=20, l=10, r=60),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_metrics_table(result: dict):
    price = result.get("price")
    size_m2 = result.get("size_m2")
    estimated_rent = result.get("estimated_rent")
    gross_yield_pct = result.get("gross_yield_pct")
    price_per_m2 = result.get("price_per_m2")

    data = {
        "Metrika": [
            "Kupní cena",
            "Plocha",
            "Cena za m²",
            "Odhadovaný nájem / měsíc",
            "Hrubý výnos (roční)",
        ],
        "Hodnota": [
            _fmt_czk(price),
            f"{size_m2:.0f} m²" if size_m2 else "—",
            _fmt_czk(price_per_m2),
            _fmt_czk(estimated_rent),
            _fmt_pct(gross_yield_pct),
        ],
    }
    st.table(pd.DataFrame(data))


def render_financial_section(result: dict):
    """Sekce finanční kalkulace — zástavní hodnota, hypotéka, cash flow."""
    collateral = result.get("collateral_value")
    max_mortgage = result.get("max_mortgage")
    net_yield = result.get("net_yield_pct")
    cashflow = result.get("monthly_cashflow")
    market_avg = result.get("market_avg_price_m2")
    price_vs_market = result.get("price_vs_market_pct")
    benchmark_label = result.get("benchmark_label")

    if not any([collateral, max_mortgage, net_yield, cashflow, market_avg]):
        return  # Žádná data

    st.subheader("💰 Finanční kalkulace")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Zástavní hodnota", _fmt_czk(collateral))
        st.caption("Odhad: kupní cena × koeficient lokality")
    with col2:
        st.metric("Max. hypotéka (80 % LTV)", _fmt_czk(max_mortgage))
        st.caption("Ze zástavní hodnoty, LTV 80 %")
    with col3:
        st.metric("Čistý výnos", _fmt_pct(net_yield))
        st.caption("Po odečtení ~28 % nákladů")
    with col4:
        if cashflow is not None:
            color = "normal" if cashflow >= 0 else "inverse"
            st.metric(
                "Měsíční cash flow",
                _fmt_czk(cashflow),
                delta=None,
                delta_color=color,
            )
            st.caption("Čistý nájem − splátka hyp. (5 %, 30 let) − fond oprav")

    # Cenový benchmark — druhý řádek
    if market_avg is not None and price_vs_market is not None:
        col_bm1, col_bm2, _ = st.columns([1, 1, 2])
        with col_bm1:
            st.metric("Průměr trhu (cena/m²)", f"{market_avg:,.0f} Kč/m²")
            if benchmark_label:
                st.caption(benchmark_label)
        with col_bm2:
            sign = "+" if price_vs_market > 0 else ""
            label = "nad průměrem" if price_vs_market > 0 else "pod průměrem"
            delta_color = "inverse" if price_vs_market > 0 else "normal"
            st.metric(
                "Cena vs. trh",
                f"{sign}{price_vs_market:.1f} %",
                delta=label,
                delta_color=delta_color,
            )
            st.caption("Záporné = levnější než trh (výhodné)")


def _locality_tier_badge(tier: int | None) -> str:
    """Vrátí HTML badge pro locality tier."""
    if tier == 1:
        return "<span style='background:#27ae60;color:white;padding:2px 7px;border-radius:4px;font-size:0.8rem;font-weight:bold'>T1</span>"
    if tier == 2:
        return "<span style='background:#f39c12;color:white;padding:2px 7px;border-radius:4px;font-size:0.8rem;font-weight:bold'>T2</span>"
    if tier == 3:
        return "<span style='background:#e74c3c;color:white;padding:2px 7px;border-radius:4px;font-size:0.8rem;font-weight:bold'>T3</span>"
    return ""


def render_result(result: dict):
    scores = result["scores"]
    total = scores["score_total"]
    color = _color_for_score(total)
    label = _score_label(total)

    # Header banner
    st.markdown(
        f"""
        <div style="background:{color}22; border-left:6px solid {color};
                    padding:16px 20px; border-radius:6px; margin-bottom:1rem;">
            <h2 style="margin:0; color:{color};">{label} – {total:.0f} / 100</h2>
            <p style="margin:4px 0 0; color:#555;">{result.get("address") or result.get("city", "")}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        render_score_gauge(total)
    with col2:
        render_breakdown_chart(scores)

    # Key metrics
    st.subheader("Klíčové ukazatele")
    render_metrics_table(result)

    # Finanční kalkulace
    render_financial_section(result)

    # Property info
    with st.expander("Detaily nemovitosti"):
        elevator = result.get("has_elevator")
        elevator_str = "Ano" if elevator is True else ("Ne" if elevator is False else "—")
        revit = result.get("building_revitalized")
        revit_str = "Ano" if revit is True else ("Ne" if revit is False else "—")
        svl_map = {"none": "Bez rizika", "proximity": "Blízkost SVL", "direct": "Přímá SVL"}
        own_map = {"OV": "Osobní vlastnictví", "DV": "Družstevní", "DV_no_transfer": "Družstevní (bez převodu)"}
        tier = result.get("locality_tier")
        info = {
            "Dispozice": result.get("disposition", "—"),
            "Konstrukce": result.get("construction_type", "—"),
            "Energetická třída (PENB)": result.get("energy_class", "—"),
            "Rok výstavby": result.get("year_built", "—"),
            "Podlaží": result.get("floor", "—"),
            "Výtah": elevator_str,
            "Kraj": result.get("kraj") or "—",
            "Město / okres": f"{result.get('city', '—')} / {result.get('district', '—')}",
            "Vlastnictví": own_map.get(result.get("ownership", ""), result.get("ownership") or "—"),
            "SVL riziko": svl_map.get(result.get("svl_risk", ""), result.get("svl_risk") or "—"),
            "Lokalita tier": f"{'T' + str(tier) if tier else '—'}",
            "Revitalizace domu": revit_str,
            "Fond oprav": _fmt_czk(result.get("service_charge")),
        }
        for k, v in info.items():
            st.write(f"**{k}:** {v}")

    # Summary
    st.subheader("Hodnocení")
    st.info(result["summary"])

    # Red flags
    if result.get("red_flags"):
        st.subheader("⚠️ Varování")
        for flag in result["red_flags"]:
            st.warning(flag)

    # Link to original listing
    if result.get("url"):
        st.markdown(f"[↗ Otevřít inzerát]({result['url']})")


def _detail_to_result(d: dict) -> dict:
    """Adapt flat PropertyDetail API response to the format render_result expects."""
    return {
        **d,
        "scores": {
            "score_total": d.get("score_total") or 0,
            "score_yield": d.get("score_yield") or 0,
            "score_demographic": d.get("score_demographic") or 0,
            "score_economic": d.get("score_economic") or 0,
            "score_quality": d.get("score_quality") or 0,
            "score_liquidity": d.get("score_liquidity") or 0,
        },
        # Finanční kalkulace (přímé z PropertyDetail)
        "collateral_value": d.get("collateral_value"),
        "max_mortgage": d.get("max_mortgage"),
        "net_yield_pct": d.get("net_yield_pct"),
        "monthly_cashflow": d.get("monthly_cashflow"),
    }


# ---------------------------------------------------------------------------
# Query-param routing – property detail page
# ---------------------------------------------------------------------------

_qp_id = st.query_params.get("property_id")
if _qp_id is not None:
    if st.button("← Zpět do historie"):
        st.session_state["nav_page"] = "Historie analýz"
        del st.query_params["property_id"]
        st.rerun()

    with st.spinner("Načítám detail nemovitosti…"):
        _detail = api_get_property(int(_qp_id))

    if _detail is None:
        st.error("Nemovitost nenalezena.")
    else:
        st.title("🏠 Detail nemovitosti")
        render_result(_detail_to_result(_detail))
    st.stop()


# ---------------------------------------------------------------------------
# Sidebar – navigation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image("https://via.placeholder.com/200x60/2c3e50/ffffff?text=RealScore+CZ", width=200)
    st.markdown("---")
    page = st.radio(
        "Navigace",
        ["Analyzovat nemovitost", "Historie analýz"],
        label_visibility="collapsed",
        key="nav_page",
    )
    st.markdown("---")
    st.caption("RealScore CZ v1.0 · Data: Sreality, ČSÚ")


# ---------------------------------------------------------------------------
# Page: Analyze
# ---------------------------------------------------------------------------

if page == "Analyzovat nemovitost":
    st.title("🏠 RealScore CZ – Analýza investice")
    st.markdown("Vložte URL nemovitosti ze Sreality nebo Bezrealitky.")

    url_input = st.text_input(
        "URL nemovitosti",
        placeholder="https://www.sreality.cz/detail/prodej/byt/...",
    )
    st.caption("Podporujeme: sreality.cz, bezrealitky.cz, reality.idnes.cz")

    st.markdown("---")
    if st.button("🔍 Analyzovat", type="primary", use_container_width=True):
        if not url_input:
            st.warning("Zadejte URL nemovitosti.")
        else:
            with st.spinner("Probíhá analýza…"):
                _res = api_analyze({"url": url_input})
            if _res:
                st.success("Analýza dokončena!")
                st.session_state["last_result"] = _res

    if "last_result" in st.session_state:
        st.markdown("---")
        render_result(st.session_state["last_result"])


# ---------------------------------------------------------------------------
# Page: History
# ---------------------------------------------------------------------------

elif page == "Historie analýz":
    st.title("📋 Historie analýz")

    @st.dialog("Smazat celou historii?")
    def _confirm_delete_all():
        st.warning("Tato akce je nevratná. Budou smazány všechny záznamy z historie.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Ano, smazat vše", type="primary", use_container_width=True):
                api_delete_all()
                st.session_state["_hist_visible"] = 10
                st.rerun()
        with c2:
            if st.button("Zrušit", use_container_width=True):
                st.rerun()

    col_sort, col_order, col_refresh, col_delete = st.columns([2, 1, 1, 1])
    with col_sort:
        sort_by = st.selectbox(
            "Seřadit podle",
            ["score_total", "created_at", "gross_yield_pct", "price"],
            format_func=lambda x: {
                "created_at": "Datum analýzy",
                "score_total": "Celkové skóre",
                "gross_yield_pct": "Hrubý výnos",
                "price": "Cena",
            }[x],
        )
    with col_order:
        order = st.selectbox("Pořadí", ["desc", "asc"], format_func=lambda x: "Sestupně" if x == "desc" else "Vzestupně")
    with col_refresh:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("🔄 Obnovit")
    with col_delete:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑 Smazat vše", type="secondary"):
            _confirm_delete_all()

    # Load global filter options (regions, energy_classes, price stats)
    if "_filter_opts" not in st.session_state or refresh:
        st.session_state["_filter_opts"] = api_get_filters()
    filter_opts = st.session_state["_filter_opts"]

    # Filter UI – první řada: kraj + ceny
    col_loc, col_pmin, col_pmax = st.columns([2, 1, 1])
    with col_loc:
        _saved_regions = st.session_state.get("_saved_regions", [])
        _valid_regions = [r for r in _saved_regions if r in filter_opts["regions"]]
        selected_regions = st.multiselect(
            "Kraj",
            options=filter_opts["regions"],
            default=_valid_regions,
            placeholder="Všechny kraje",
        )
        st.session_state["_saved_regions"] = selected_regions
    with col_pmin:
        price_min_text = st.text_input(
            "Cena od (Kč)",
            value=st.session_state.get("_saved_price_min_text", ""),
            placeholder="1 000 000",
        )
        st.session_state["_saved_price_min_text"] = price_min_text
    with col_pmax:
        price_max_text = st.text_input(
            "Cena do (Kč)",
            value=st.session_state.get("_saved_price_max_text", ""),
            placeholder="3 000 000",
        )
        st.session_state["_saved_price_max_text"] = price_max_text

    # Dynamické načtení měst pro vybraný kraj
    _cities_key = f"_cities_{'|'.join(sorted(selected_regions))}"
    if st.session_state.get("_cities_cache_key") != _cities_key or "_cities_opts" not in st.session_state or refresh:
        st.session_state["_cities_cache_key"] = _cities_key
        _city_opts = api_get_filters(regions=selected_regions or None)
        st.session_state["_cities_opts"] = _city_opts.get("cities", [])
    available_cities = st.session_state["_cities_opts"]

    # Rozšířené filtry — druhá řada
    col_own, col_city, col_penb, col_yield = st.columns([2, 2, 2, 1])
    with col_own:
        _saved_ownerships = st.session_state.get("_saved_ownerships", ["OV"])
        selected_ownerships = st.multiselect(
            "Vlastnictví",
            options=["OV", "DV", "DV_no_transfer"],
            default=_saved_ownerships,
            format_func=lambda x: {
                "OV": "OV — osobní",
                "DV": "DV — družstevní",
                "DV_no_transfer": "DV — bez převodu",
            }[x],
            placeholder="Všechny typy",
        )
        st.session_state["_saved_ownerships"] = selected_ownerships
    with col_city:
        _saved_cities = st.session_state.get("_saved_cities", [])
        _valid_cities = [c for c in _saved_cities if c in available_cities]
        selected_cities = st.multiselect(
            "Město",
            options=available_cities,
            default=_valid_cities,
            placeholder="Nejdřív vyberte kraj" if not selected_regions else "Všechna města",
            disabled=not selected_regions,
        )
        st.session_state["_saved_cities"] = selected_cities
    with col_penb:
        _saved_penb = st.session_state.get("_saved_penb", [])
        _valid_penb = [e for e in _saved_penb if e in filter_opts.get("energy_classes", [])]
        selected_penb = st.multiselect(
            "PENB třída",
            options=filter_opts.get("energy_classes", ["A", "B", "C", "D", "E", "F", "G"]),
            default=_valid_penb,
            placeholder="Všechny třídy",
        )
        st.session_state["_saved_penb"] = selected_penb
    with col_yield:
        min_yield_text = st.text_input(
            "Min. výnos (%)",
            value=st.session_state.get("_saved_min_yield_text", ""),
            placeholder="4.0",
        )
        st.session_state["_saved_min_yield_text"] = min_yield_text

    active_price_min = _parse_price(price_min_text)
    active_price_max = _parse_price(price_max_text)
    active_min_yield = _parse_price(min_yield_text)

    total = api_count_properties(
        regions=selected_regions or None,
        price_min=active_price_min,
        price_max=active_price_max,
        cities=selected_cities or None,
        energy_classes=selected_penb or None,
        min_yield=active_min_yield,
        ownerships=selected_ownerships or None,
    )

    # Reset cache when sort/order/filters change or on first load
    _cache_key = (
        f"{sort_by}_{order}"
        f"_{','.join(sorted(selected_regions))}"
        f"_{price_min_text}_{price_max_text}"
        f"_{','.join(sorted(selected_cities))}"
        f"_{','.join(sorted(selected_penb))}"
        f"_{min_yield_text}"
        f"_{','.join(sorted(selected_ownerships))}"
    )
    if st.session_state.get("_hist_cache_key") != _cache_key or "_hist_props" not in st.session_state:
        st.session_state["_hist_cache_key"] = _cache_key
        st.session_state["_hist_visible"] = 10
        st.session_state["_hist_props"] = api_list_properties(
            sort_by=sort_by, order=order, offset=0,
            regions=selected_regions or None,
            price_min=active_price_min, price_max=active_price_max,
            cities=selected_cities or None,
            energy_classes=selected_penb or None,
            min_yield=active_min_yield,
            ownerships=selected_ownerships or None,
        )

    if refresh:
        st.session_state["_hist_props"] = api_list_properties(
            sort_by=sort_by, order=order, offset=0,
            regions=selected_regions or None,
            price_min=active_price_min, price_max=active_price_max,
            cities=selected_cities or None,
            energy_classes=selected_penb or None,
            min_yield=active_min_yield,
            ownerships=selected_ownerships or None,
        )
        st.session_state["_hist_visible"] = 10

    properties = st.session_state["_hist_props"]
    visible = st.session_state.get("_hist_visible", 10)

    if not properties and total == 0:
        st.info("Zatím nebyly analyzovány žádné nemovitosti.")
    else:
        st.write(f"Zobrazeno: **{min(visible, len(properties))}** z **{total}** nemovitostí")

        for prop in properties[:visible]:
            score = prop.get("score_total") or 0
            color = _color_for_score(score)
            addr = prop.get("address") or prop.get("city") or "Neznámá adresa"
            tier_badge = _locality_tier_badge(prop.get("locality_tier"))
            penb = prop.get("energy_class") or ""

            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([3, 1, 1, 1, 2, 2, 1, 1])
            with c1:
                st.markdown(f"**{addr}**")
            with c2:
                st.markdown(prop.get("disposition") or "—")
            with c3:
                # Locality tier badge
                if tier_badge:
                    st.markdown(tier_badge, unsafe_allow_html=True)
                else:
                    st.markdown("—")
            with c4:
                # PENB badge
                if penb:
                    penb_color = {"A": "#27ae60", "B": "#2ecc71", "C": "#f1c40f",
                                  "D": "#e67e22", "E": "#e74c3c", "F": "#c0392b", "G": "#922b21"}.get(penb, "#888")
                    st.markdown(
                        f"<span style='background:{penb_color};color:white;padding:2px 7px;"
                        f"border-radius:4px;font-size:0.8rem;font-weight:bold'>{penb}</span>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown("—")
            with c5:
                st.markdown(f"<span style='color:{color};font-weight:bold'>{score:.0f}/100</span>", unsafe_allow_html=True)
            with c6:
                st.markdown(_fmt_czk(prop.get("price")))
            with c7:
                st.markdown(
                    f"<a href='?property_id={prop['id']}' title='Zobrazit detail' "
                    f"style='font-size:1.2rem;text-decoration:none;'>🔍</a>",
                    unsafe_allow_html=True,
                )
            with c8:
                if st.button("🗑", key=f"del_{prop['id']}", help="Smazat"):
                    api_delete(prop["id"])
                    st.rerun()
            st.divider()

        if visible < total:
            remaining = total - visible
            if st.button(f"Načíst dalších 10 ({remaining} zbývá)", use_container_width=True):
                next_visible = visible + 10
                if next_visible > len(properties):
                    more = api_list_properties(
                        sort_by=sort_by, order=order, offset=len(properties),
                        regions=selected_regions or None,
                        price_min=active_price_min, price_max=active_price_max,
                        cities=selected_cities or None,
                        energy_classes=selected_penb or None,
                        min_yield=active_min_yield,
                        ownerships=selected_ownerships or None,
                    )
                    st.session_state["_hist_props"] = properties + more
                st.session_state["_hist_visible"] = next_visible
                st.rerun()
