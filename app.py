"""
Dashboard de Portafolio — Racional + Renta4
Vistas: Total / Racional / Renta4 · Moneda: USD ⇄ CLP
Rentabilidad por instrumento: precio, dividendo y total.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

from core import data_loader as dl
from core import market_data as md
from core import portfolio as pf

BASE_DIR = Path(__file__).parent
DATA_DEFAULT = BASE_DIR / "data" / "Inversiones_Rac-Renta4.xlsx"

st.set_page_config(
    page_title="Portafolio · Racional + Renta4",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Estilo institucional
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      :root {
        --navy:#1F3A5F; --navy-d:#16293F; --ink:#1A1F2B;
        --slate:#5B6473; --line:#E3E7EE; --bg-soft:#F4F6F9;
        --pos:#1B7F5B; --neg:#B23A3A; --gold:#B98A2E;
      }
      .block-container {padding-top:2.2rem; max-width:1320px;}
      h1,h2,h3 {color:var(--ink); letter-spacing:-.01em;}
      /* Encabezado de marca */
      .brand {border-bottom:2px solid var(--navy); padding-bottom:.9rem; margin-bottom:1.4rem;}
      .brand .eyebrow {font-size:.72rem; letter-spacing:.18em; text-transform:uppercase;
        color:var(--slate); font-weight:600;}
      .brand .title {font-size:1.9rem; font-weight:700; color:var(--navy-d); margin:.1rem 0 0;}
      .brand .sub {font-size:.9rem; color:var(--slate); margin-top:.15rem;}
      /* Tarjetas KPI */
      .kpi {border:1px solid var(--line); border-radius:10px; padding:1rem 1.15rem;
        background:#fff; height:100%;}
      .kpi .lbl {font-size:.72rem; letter-spacing:.08em; text-transform:uppercase;
        color:var(--slate); font-weight:600;}
      .kpi .val {font-size:1.55rem; font-weight:700; color:var(--ink); margin-top:.25rem;
        font-variant-numeric:tabular-nums;}
      .kpi .delta {font-size:.85rem; font-weight:600; margin-top:.1rem;}
      .pos {color:var(--pos);} .neg {color:var(--neg);}
      .chip {display:inline-block; font-size:.7rem; font-weight:600; padding:.12rem .5rem;
        border-radius:999px; background:var(--bg-soft); color:var(--slate);
        border:1px solid var(--line);}
      .foot {color:var(--slate); font-size:.78rem; border-top:1px solid var(--line);
        margin-top:2rem; padding-top:.8rem;}
      [data-testid="stMetricValue"] {font-variant-numeric:tabular-nums;}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Cargas cacheadas
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def _cargar_base(_source, _firma):
    return dl.load_workbook(_source)


@st.cache_data(ttl=3600, show_spinner=False)
def _cargar_usdclp():
    return md.descargar_usdclp()


@st.cache_data(ttl=1800, show_spinner=False)
def _cargar_precios(simbolos: tuple[str, ...]):
    return md.descargar_precios_actuales(list(simbolos))


def _fmt_money(x, moneda):
    if x is None or pd.isna(x):
        return "—"
    if moneda == "CLP":
        return f"${x:,.0f}"
    return f"US${x:,.2f}"


def _fmt_pct(x):
    if x is None or pd.isna(x):
        return "—"
    return f"{x*100:,.1f}%"


def _signo_cls(x):
    if x is None or pd.isna(x):
        return ""
    return "pos" if x >= 0 else "neg"


# --------------------------------------------------------------------------- #
# Estado / fuente de datos
# --------------------------------------------------------------------------- #
if "data_source" not in st.session_state:
    st.session_state.data_source = "default"
if "uploaded_bytes" not in st.session_state:
    st.session_state.uploaded_bytes = None
if "precios_manuales" not in st.session_state:
    st.session_state.precios_manuales = {}

# --------------------------------------------------------------------------- #
# Barra lateral: controles
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### Controles")

    vista = st.radio(
        "Vista de portafolio",
        ["Portafolio total", "Racional", "Renta4"],
        index=0,
    )
    plataforma = {"Portafolio total": None, "Racional": "Racional", "Renta4": "Renta4"}[vista]

    moneda_viz = st.radio("Moneda", ["USD", "CLP"], index=0, horizontal=True)

    st.divider()
    st.markdown("#### Importar base de datos")
    st.caption(
        "Sube tu Excel actualizado (hojas Compras, Ventas, Dividendos). "
        "Reemplaza la base mientras dure la sesión."
    )
    up = st.file_uploader("Archivo .xlsx", type=["xlsx"], label_visibility="collapsed")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Usar archivo", use_container_width=True, disabled=up is None):
            st.session_state.uploaded_bytes = up.getvalue()
            st.session_state.data_source = "upload"
            _cargar_base.clear()
            st.rerun()
    with col_b:
        if st.button("Base original", use_container_width=True):
            st.session_state.uploaded_bytes = None
            st.session_state.data_source = "default"
            _cargar_base.clear()
            st.rerun()

    origen_label = "Archivo subido" if st.session_state.data_source == "upload" else "Base incluida"
    st.markdown(f"<span class='chip'>Fuente: {origen_label}</span>", unsafe_allow_html=True)

    st.divider()
    refrescar = st.button("Actualizar precios de mercado", use_container_width=True)
    if refrescar:
        _cargar_usdclp.clear()
        _cargar_precios.clear()
        st.rerun()


# --------------------------------------------------------------------------- #
# Carga de datos
# --------------------------------------------------------------------------- #
import io

if st.session_state.data_source == "upload" and st.session_state.uploaded_bytes:
    source = io.BytesIO(st.session_state.uploaded_bytes)
    firma = hash(st.session_state.uploaded_bytes)
else:
    if not DATA_DEFAULT.exists():
        st.error(
            "No se encontró la base incluida en `data/`. "
            "Sube tu archivo en la barra lateral para continuar."
        )
        st.stop()
    source = str(DATA_DEFAULT)
    firma = DATA_DEFAULT.stat().st_mtime

try:
    data = _cargar_base(source, firma)
except Exception as e:
    st.error(f"No se pudo leer el archivo: {e}")
    st.stop()

with st.spinner("Obteniendo tipo de cambio y precios de mercado…"):
    serie_usdclp = _cargar_usdclp()
    catalogo = dl.catalogo_instrumentos(data)
    simbolos = tuple(
        s for s in (md.resolver_simbolo(t) for t in catalogo["ticker"]) if s
    )
    precios_nat = _cargar_precios(simbolos)

tc_hoy = md.tc_actual(serie_usdclp)

# --------------------------------------------------------------------------- #
# Encabezado
# --------------------------------------------------------------------------- #
tc_txt = f"USD/CLP {tc_hoy:,.1f}" if tc_hoy else "USD/CLP no disponible"
st.markdown(
    f"""
    <div class="brand">
      <div class="eyebrow">Reporte de inversiones</div>
      <div class="title">Portafolio consolidado · Racional + Renta4</div>
      <div class="sub">{vista} · valores en {moneda_viz} · {tc_txt} ·
        actualizado {dt.date.today():%d-%m-%Y}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Cálculo
# --------------------------------------------------------------------------- #
posiciones = pf.calcular_posiciones(
    data, serie_usdclp, precios_nat,
    st.session_state.precios_manuales, moneda_viz, plataforma,
)
resumen = pf.resumen_portafolio(posiciones)

# --------------------------------------------------------------------------- #
# KPIs
# --------------------------------------------------------------------------- #
def kpi(col, lbl, val, delta=None, delta_cls=""):
    delta_html = f"<div class='delta {delta_cls}'>{delta}</div>" if delta else ""
    col.markdown(
        f"<div class='kpi'><div class='lbl'>{lbl}</div>"
        f"<div class='val'>{val}</div>{delta_html}</div>",
        unsafe_allow_html=True,
    )

c1, c2, c3, c4 = st.columns(4)
kpi(c1, "Valor de mercado", _fmt_money(resumen["valor_actual"], moneda_viz))
kpi(c2, "Costo invertido", _fmt_money(resumen["costo_total"], moneda_viz))
kpi(
    c3, "Rentabilidad total",
    _fmt_pct(resumen["rent_total"]),
    _fmt_money((resumen["valor_actual"] + resumen["dividendos"]
                + resumen["caja_ventas"] - resumen["costo_total"]), moneda_viz),
    _signo_cls(resumen["rent_total"]),
)
kpi(
    c4, "Dividendos acumulados",
    _fmt_money(resumen["dividendos"], moneda_viz),
    _fmt_pct(resumen["rent_dividendo"]), "pos",
)

c5, c6, c7, c8 = st.columns(4)
kpi(c5, "Rent. por precio", _fmt_pct(resumen["rent_precio"]), None, _signo_cls(resumen["rent_precio"]))
kpi(c6, "Utilidad realizada", _fmt_money(resumen["utilidad_realizada"], moneda_viz),
    None, _signo_cls(resumen["utilidad_realizada"]))
kpi(c7, "Posiciones abiertas", f"{resumen['n_abiertas']} / {resumen['n_posiciones']}")
kpi(c8, "Con alertas de datos", str(resumen["n_incompletas"]),
    "revisar" if resumen["n_incompletas"] else "ok",
    "neg" if resumen["n_incompletas"] else "pos")

st.markdown("<br>", unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Tabla de instrumentos
# --------------------------------------------------------------------------- #
tab1, tab2, tab3 = st.tabs(["Detalle por instrumento", "Composición", "Calidad de datos y precios manuales"])

df = pf.posiciones_a_dataframe(posiciones, moneda_viz)

with tab1:
    solo_abiertas = st.checkbox("Mostrar solo posiciones abiertas", value=True)
    vista_df = (df[df["Estado"] == "Abierta"] if solo_abiertas else df).copy()
    # Las rentabilidades vienen en fracción; escalar a % para el formateo de columna.
    for c in ["Rent. Precio", "Rent. Dividendo", "Rent. Total"]:
        vista_df[c] = vista_df[c] * 100

    col_money_cost = f"Costo invertido ({moneda_viz})"
    col_money_val = f"Valor actual ({moneda_viz})"
    col_money_div = f"Dividendos ({moneda_viz})"
    col_money_real = f"Realizado ({moneda_viz})"

    st.dataframe(
        vista_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Acciones": st.column_config.NumberColumn(format="%.4f"),
            col_money_cost: st.column_config.NumberColumn(
                format="$%,.0f" if moneda_viz == "CLP" else "$%,.2f"),
            col_money_val: st.column_config.NumberColumn(
                format="$%,.0f" if moneda_viz == "CLP" else "$%,.2f"),
            col_money_div: st.column_config.NumberColumn(
                format="$%,.0f" if moneda_viz == "CLP" else "$%,.2f"),
            col_money_real: st.column_config.NumberColumn(
                format="$%,.0f" if moneda_viz == "CLP" else "$%,.2f"),
            "Rent. Precio": st.column_config.NumberColumn(format="%.1f%%", help="Ganancia de capital sobre el costo invertido"),
            "Rent. Dividendo": st.column_config.NumberColumn(format="%.1f%%"),
            "Rent. Total": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
    # Las columnas de rentabilidad vienen en fracción; convertir a % para el formato.
    st.caption(
        "Rent. Precio = ganancia de capital (incluye realizado) / costo invertido · "
        "Rent. Dividendo = dividendos / costo invertido · Rent. Total = suma de ambas. "
        "El costo histórico usa el tipo de cambio del día de cada operación; el valor "
        "actual usa el tipo de cambio de hoy."
    )

    st.download_button(
        "Descargar detalle (CSV)",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"portafolio_{vista.lower().replace(' ','_')}_{moneda_viz}.csv",
        mime="text/csv",
    )

with tab2:
    abiertas = [p for p in posiciones if p.acciones_actuales > 0 and p.valor_actual > 0]
    if abiertas:
        comp = pd.DataFrame({
            "Instrumento": [p.nombre for p in abiertas],
            "Valor": [p.valor_actual for p in abiertas],
        }).sort_values("Valor", ascending=False)
        comp["Peso"] = comp["Valor"] / comp["Valor"].sum()
        cc1, cc2 = st.columns([3, 2])
        with cc1:
            st.bar_chart(comp.set_index("Instrumento")["Valor"], height=420)
        with cc2:
            comp_show = comp.copy()
            comp_show["Valor"] = comp_show["Valor"].map(lambda x: _fmt_money(x, moneda_viz))
            comp_show["Peso"] = comp_show["Peso"].map(_fmt_pct)
            st.dataframe(comp_show, hide_index=True, use_container_width=True, height=420)
    else:
        st.info("No hay posiciones abiertas con valor de mercado para mostrar composición.")

with tab3:
    incompletas = [p for p in posiciones if p.incompleto]
    if incompletas:
        st.warning(
            f"{len(incompletas)} instrumento(s) con datos incompletos. "
            "Las rentabilidades de estos casos pueden ser parciales."
        )
        qdf = pd.DataFrame({
            "Ticker": [p.ticker for p in incompletas],
            "Instrumento": [p.nombre for p in incompletas],
            "Alerta": ["; ".join(p.notas_calidad) for p in incompletas],
            "Precio fuente": [p.precio_fuente for p in incompletas],
        })
        st.dataframe(qdf, hide_index=True, use_container_width=True)
    else:
        st.success("Sin alertas de calidad de datos.")

    st.markdown("#### Precios manuales")
    st.caption(
        "Para fondos locales (CFI/CFM) y otros instrumentos sin cotización pública, "
        "ingresa el precio actual en su moneda nativa. Tiene prioridad sobre yfinance."
    )
    sin_precio = sorted({
        p.ticker for p in posiciones
        if p.acciones_actuales > 0 and p.precio_fuente in ("sin dato", "manual")
    })
    if sin_precio:
        editor_df = pd.DataFrame({
            "Ticker": sin_precio,
            "Instrumento": [
                next((p.nombre for p in posiciones if p.ticker == t), t) for t in sin_precio
            ],
            "Moneda": [
                next((p.moneda_origen for p in posiciones if p.ticker == t), "") for t in sin_precio
            ],
            "Precio manual": [
                float(st.session_state.precios_manuales.get(t, 0.0) or 0.0) for t in sin_precio
            ],
        })
        edited = st.data_editor(
            editor_df,
            hide_index=True,
            use_container_width=True,
            disabled=["Ticker", "Instrumento", "Moneda"],
            column_config={"Precio manual": st.column_config.NumberColumn(format="%.2f", min_value=0.0)},
            key="editor_precios",
        )
        if st.button("Guardar precios manuales"):
            for _, r in edited.iterrows():
                val = r["Precio manual"]
                if val and val > 0:
                    st.session_state.precios_manuales[r["Ticker"]] = float(val)
                else:
                    st.session_state.precios_manuales.pop(r["Ticker"], None)
            st.rerun()
    else:
        st.info("Todos los instrumentos abiertos tienen precio de mercado disponible.")

# --------------------------------------------------------------------------- #
# Pie
# --------------------------------------------------------------------------- #
st.markdown(
    f"""
    <div class="foot">
      Precios y tipo de cambio vía Yahoo Finance (yfinance), con caché. ·
      Método de costeo: promedio ponderado. ·
      Este reporte es informativo y no constituye asesoría de inversión.
    </div>
    """,
    unsafe_allow_html=True,
)
