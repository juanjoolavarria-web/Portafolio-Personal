"""
Carga y normalización de la base de transacciones (Compras, Ventas, Dividendos).

Particularidad clave del archivo de origen:
las columnas "Precio USD" / "Monto USD" / "Monto Recibido USD" están nombradas
en USD, pero cuando la columna `Moneda` (o `Tipo Orden`) indica CLP, los valores
están expresados en CLP. Este módulo normaliza todo a un esquema único con una
columna `moneda_origen` explícita y montos en su moneda nativa.
"""

from __future__ import annotations

import pandas as pd

# Plataformas: la base usa "Racional/DriveWealth", "Racional" y "Renta4".
# Las dos primeras se consolidan bajo la vista "Racional".
PLATAFORMA_RACIONAL = "Racional"
PLATAFORMA_RENTA4 = "Renta4"


def _norm_plataforma(valor: str) -> str:
    if not isinstance(valor, str):
        return "Desconocida"
    v = valor.strip().lower()
    if v.startswith("racional"):
        return PLATAFORMA_RACIONAL
    if v.startswith("renta4") or v.startswith("renta 4"):
        return PLATAFORMA_RENTA4
    return valor.strip()


def _coerce_fecha(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, errors="coerce")


def load_workbook(source) -> dict[str, pd.DataFrame]:
    """
    Lee las tres hojas del Excel y devuelve un dict con DataFrames normalizados:
    'compras', 'ventas', 'dividendos'. `source` puede ser una ruta o un
    file-like (lo que entrega st.file_uploader).
    """
    xls = pd.ExcelFile(source)
    hojas = {n.lower(): n for n in xls.sheet_names}

    def _hoja(*candidatos):
        for c in candidatos:
            if c in hojas:
                return pd.read_excel(xls, sheet_name=hojas[c])
        raise ValueError(
            f"No se encontró ninguna de las hojas {candidatos}. "
            f"Hojas disponibles: {list(xls.sheet_names)}"
        )

    compras = _normalizar_compras(_hoja("compras"))
    ventas = _normalizar_ventas(_hoja("ventas"))
    dividendos = _normalizar_dividendos(_hoja("dividendos"))

    return {"compras": compras, "ventas": ventas, "dividendos": dividendos}


def _normalizar_compras(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["plataforma"] = df["Plataforma"].map(_norm_plataforma)
    df["fecha"] = _coerce_fecha(df["Fecha"])
    df["ticker"] = df["Ticker"].astype(str).str.strip()
    df["nombre"] = df["Nombre"].astype(str).str.strip()
    df["moneda_origen"] = df["Moneda"].astype(str).str.strip().str.upper()
    df["acciones"] = pd.to_numeric(df["Acciones"], errors="coerce")
    # Precio y monto: nativos en la moneda de `moneda_origen`.
    df["precio_nativo"] = pd.to_numeric(df["Precio USD"], errors="coerce")
    df["monto_nativo"] = pd.to_numeric(df["Monto USD"], errors="coerce")
    df["notas"] = df.get("Notas")
    df["tipo"] = "compra"
    return df[
        [
            "ticker", "nombre", "plataforma", "fecha", "acciones",
            "precio_nativo", "monto_nativo", "moneda_origen", "notas", "tipo",
        ]
    ]


def _normalizar_ventas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["plataforma"] = df["Plataforma"].map(_norm_plataforma)
    df["fecha"] = _coerce_fecha(df["Fecha"])
    df["ticker"] = df["Ticker"].astype(str).str.strip()
    df["nombre"] = df["Nombre"].astype(str).str.strip()
    df["acciones"] = pd.to_numeric(df["Acciones Vendidas"], errors="coerce")
    df["precio_nativo"] = pd.to_numeric(df["Precio USD"], errors="coerce")
    df["monto_nativo"] = pd.to_numeric(df["Monto Recibido USD"], errors="coerce")
    # En ventas la moneda no es columna propia: se infiere del "Tipo Orden".
    tipo_orden = df.get("Tipo Orden").astype(str).str.strip().str.upper()
    df["moneda_origen"] = tipo_orden.where(tipo_orden == "CLP", "USD")
    df["notas"] = df.get("Notas")
    df["tipo"] = "venta"
    return df[
        [
            "ticker", "nombre", "plataforma", "fecha", "acciones",
            "precio_nativo", "monto_nativo", "moneda_origen", "notas", "tipo",
        ]
    ]


def _normalizar_dividendos(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["plataforma"] = df["Plataforma"].map(_norm_plataforma)
    df["fecha"] = _coerce_fecha(df["Fecha"])
    df["ticker"] = df["Ticker"].astype(str).str.strip()
    df["nombre"] = df["Nombre"].astype(str).str.strip()
    df["moneda_origen"] = df["Moneda"].astype(str).str.strip().str.upper()
    df["monto_nativo"] = pd.to_numeric(df["Monto USD"], errors="coerce")
    df["notas"] = df.get("Notas")
    df["tipo"] = "dividendo"
    return df[
        ["ticker", "nombre", "plataforma", "fecha", "monto_nativo",
         "moneda_origen", "notas", "tipo"]
    ]


def catalogo_instrumentos(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Tabla única ticker -> nombre, moneda predominante y plataformas."""
    frames = []
    for key in ("compras", "ventas", "dividendos"):
        d = data[key][["ticker", "nombre", "plataforma", "moneda_origen"]].copy()
        frames.append(d)
    todo = pd.concat(frames, ignore_index=True)
    agg = (
        todo.groupby("ticker")
        .agg(
            nombre=("nombre", lambda s: s.dropna().iloc[0] if s.dropna().size else ""),
            moneda=("moneda_origen", lambda s: s.mode().iloc[0] if s.mode().size else "USD"),
            plataformas=("plataforma", lambda s: sorted(s.dropna().unique().tolist())),
        )
        .reset_index()
    )
    return agg
