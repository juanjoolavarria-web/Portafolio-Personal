"""
Precios de mercado y tipo de cambio.

- Precios actuales de instrumentos vía yfinance.
- Serie histórica de USD/CLP vía yfinance (par "USDCLP=X").
- Mapeo de tickers locales -> símbolos yfinance.
- Fallback de precios manuales para instrumentos que yfinance no cubre
  (fondos CFI/CFM chilenos, tickers sin cotización pública, etc.).

Todo está envuelto en cachés de Streamlit cuando se invoca desde la app;
las funciones puras viven aquí para ser testeables sin Streamlit.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

# ---------------------------------------------------------------------------
# Mapeo ticker base -> símbolo yfinance.
# Las acciones chilenas en bolsa cotizan con sufijo ".SN" en Yahoo Finance.
# Los fondos mutuos/CFI/CFM locales NO tienen símbolo público -> None
# (requieren precio manual). Los tickers US cotizan con su símbolo directo.
# ---------------------------------------------------------------------------
TICKER_MAP: dict[str, str | None] = {
    # --- Acciones Chile (Bolsa de Santiago, sufijo .SN en Yahoo) ---
    "BSANTANDER": "BSANTANDER.SN",
    "CHILE": "CHILE.SN",
    "COPEC": "COPEC.SN",
    "FALABELLA": "FALABELLA.SN",
    "HABITAT": "HABITAT.SN",
    "QUINENCO": "QUINENCO.SN",
    "LTM": "LTM.SN",
    # --- Fondos locales sin cotización pública (precio manual) ---
    "CFMITNIPSA": None,   # ETF Acc. Chilenas IPSA (fondo)
    "CFIETFGE": None,     # ETF Acciones Globales
    "CFIETFCC": None,     # ETF Acciones Chilenas (BCI)
    "CFIBTGRE": None,     # BTG Pactual Retorno Estratégico
    # --- US / internacionales (símbolo directo en Yahoo) ---
    "VOO": "VOO", "KKR": "KKR", "PLTR": "PLTR", "PYPL": "PYPL",
    "SPOT": "SPOT", "APP": "APP", "DLO": "DLO", "GLOB": "GLOB",
    "GPRK": "GPRK", "OPEN": "OPEN", "OSCR": "OSCR", "SOUN": "SOUN",
    "FISV": "FI", "CRWV": "CRWV", "CIB": "CIB", "MH": "MH",
    "FLG": "FLG", "CERT": "CERT", "BX": "BX", "ENPH": "ENPH",
    "FIG": "FIG", "GME": "GME", "MELI": "MELI", "MODG": "MODG",
    "UUUU": "UUUU", "VKTX": "VKTX", "W": "W", "WOOF": "WOOF",
}

USDCLP_SYMBOL = "USDCLP=X"


def resolver_simbolo(ticker: str) -> str | None:
    """Devuelve el símbolo yfinance, o None si requiere precio manual."""
    return TICKER_MAP.get(ticker.upper(), ticker.upper())


def descargar_precios_actuales(simbolos: list[str]) -> dict[str, float]:
    """
    Último precio de cierre por símbolo. Devuelve {simbolo: precio}.
    Símbolos que fallan simplemente no aparecen en el dict.
    """
    import yfinance as yf

    out: dict[str, float] = {}
    simbolos = [s for s in dict.fromkeys(simbolos) if s]
    if not simbolos:
        return out
    try:
        data = yf.download(
            simbolos, period="5d", interval="1d",
            progress=False, auto_adjust=True, threads=True,
        )
    except Exception:
        return out
    if data is None or data.empty:
        return out
    close = data["Close"] if "Close" in data else data
    if isinstance(close, pd.Series):  # un solo símbolo
        close = close.to_frame(name=simbolos[0])
    for sym in close.columns:
        serie = close[sym].dropna()
        if not serie.empty:
            out[sym] = float(serie.iloc[-1])
    return out


def descargar_usdclp(desde: dt.date | None = None) -> pd.Series:
    """
    Serie diaria de USD/CLP indexada por fecha (tz-naive). Se usa para:
    - convertir transacciones históricas al TC de su día (asof);
    - obtener el TC actual (último valor).
    """
    import yfinance as yf

    start = (desde or dt.date(2021, 1, 1)).isoformat()
    try:
        data = yf.download(
            USDCLP_SYMBOL, start=start, interval="1d",
            progress=False, auto_adjust=True,
        )
    except Exception:
        return pd.Series(dtype=float)
    if data is None or data.empty:
        return pd.Series(dtype=float)
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.dropna()


def tc_asof(serie_usdclp: pd.Series, fecha) -> float | None:
    """TC vigente en `fecha` (último dato disponible <= fecha)."""
    if serie_usdclp is None or serie_usdclp.empty or pd.isna(fecha):
        return None
    fecha = pd.Timestamp(fecha).tz_localize(None)
    idx = serie_usdclp.index[serie_usdclp.index <= fecha]
    if len(idx) == 0:
        return float(serie_usdclp.iloc[0])  # fecha anterior a la serie
    return float(serie_usdclp.loc[idx[-1]])


def tc_actual(serie_usdclp: pd.Series) -> float | None:
    if serie_usdclp is None or serie_usdclp.empty:
        return None
    return float(serie_usdclp.iloc[-1])
