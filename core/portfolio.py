"""
Motor de cálculo del portafolio.

Convenciones de moneda
----------------------
Cada transacción tiene un monto en su `moneda_origen` (USD o CLP). Para poder
mostrar todo el portafolio en una moneda de visualización (USD o CLP) se aplica:

  * COSTO / FLUJOS HISTÓRICOS  -> se convierten con el TC del día de la
    transacción (TC histórico). Así la inversión refleja lo efectivamente
    desembolsado y, al medirla contra el valor actual, la rentabilidad en CLP
    de un activo USD incorpora también el efecto cambiario real.

  * VALOR DE MERCADO ACTUAL    -> se convierte con el TC de hoy.

Rentabilidades por instrumento
------------------------------
  rent_precio    = (valor_actual - costo_remanente) / costo_base
  rent_dividendo =  dividendos_totales / costo_base
  rent_total     = (valor_actual + dividendos + caja_por_ventas - costo_total) / costo_total

Posiciones: costo PROMEDIO PONDERADO. Cada venta reduce el costo remanente al
costo promedio vigente; la utilidad realizada se acumula aparte.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import market_data as md


@dataclass
class PosicionResultado:
    ticker: str
    nombre: str
    moneda_origen: str
    plataformas: list[str]
    acciones_actuales: float
    costo_total_base: float          # costo de todo lo comprado (moneda viz)
    costo_remanente: float           # costo de lo aún en cartera (moneda viz)
    valor_actual: float              # acciones_actuales * precio_actual (moneda viz)
    dividendos: float                # dividendos recibidos (moneda viz)
    caja_ventas: float               # efectivo recibido por ventas (moneda viz)
    utilidad_realizada: float        # caja_ventas - costo de lo vendido (moneda viz)
    precio_actual_nativo: float | None
    precio_fuente: str               # 'yfinance' | 'manual' | 'sin dato'
    incompleto: bool                 # faltan compras u otros datos
    notas_calidad: list[str] = field(default_factory=list)

    @property
    def rent_precio(self) -> float | None:
        # Ganancia de capital: (valor actual + realizado de capital) vs costo total.
        if self.costo_total_base <= 0:
            return None
        ganancia_cap = (self.valor_actual - self.costo_remanente) + self.utilidad_realizada
        return ganancia_cap / self.costo_total_base

    @property
    def rent_dividendo(self) -> float | None:
        if self.costo_total_base <= 0:
            return None
        return self.dividendos / self.costo_total_base

    @property
    def rent_total(self) -> float | None:
        if self.costo_total_base <= 0:
            return None
        rp = self.rent_precio or 0.0
        rd = self.rent_dividendo or 0.0
        return rp + rd


def _convertir(monto, moneda_origen, moneda_viz, tc):
    """Convierte `monto` desde moneda_origen a moneda_viz usando el TC dado
    (CLP por USD). Devuelve np.nan si falta TC necesario."""
    if monto is None or pd.isna(monto):
        return np.nan
    if moneda_origen == moneda_viz:
        return float(monto)
    if tc is None or pd.isna(tc) or tc == 0:
        return np.nan
    if moneda_origen == "USD" and moneda_viz == "CLP":
        return float(monto) * tc
    if moneda_origen == "CLP" and moneda_viz == "USD":
        return float(monto) / tc
    return float(monto)


def calcular_posiciones(
    data: dict[str, pd.DataFrame],
    serie_usdclp: pd.Series,
    precios_actuales_nativos: dict[str, float],
    precios_manuales: dict[str, float] | None,
    moneda_viz: str,
    plataforma: str | None = None,
) -> list[PosicionResultado]:
    """
    Calcula las posiciones consolidadas.

    precios_actuales_nativos: {ticker -> precio en su moneda nativa} (yfinance)
    precios_manuales: {ticker -> precio en su moneda nativa} (override usuario)
    plataforma: None = total; o "Racional"/"Renta4" para filtrar.
    """
    precios_manuales = precios_manuales or {}
    tc_hoy = md.tc_actual(serie_usdclp)

    compras = data["compras"]
    ventas = data["ventas"]
    dividendos = data["dividendos"]

    if plataforma:
        compras = compras[compras["plataforma"] == plataforma]
        ventas = ventas[ventas["plataforma"] == plataforma]
        dividendos = dividendos[dividendos["plataforma"] == plataforma]

    catalogo = _catalogo(data, plataforma)
    resultados: list[PosicionResultado] = []

    for ticker, info in catalogo.items():
        moneda_orig = info["moneda"]
        notas_q: list[str] = []
        incompleto = False

        c = compras[compras["ticker"] == ticker].sort_values("fecha")
        v = ventas[ventas["ticker"] == ticker].sort_values("fecha")
        d = dividendos[dividendos["ticker"] == ticker]

        # --- Costo de compras (promedio ponderado) en moneda de visualización ---
        acciones_comp = 0.0
        costo_comp_viz = 0.0          # costo acumulado de lo comprado (viz)
        costo_total_base = 0.0        # idem (no se descuenta con ventas)
        compras_sin_monto = 0
        for _, row in c.iterrows():
            monto = row["monto_nativo"]
            acc = row["acciones"]
            tc_dia = md.tc_asof(serie_usdclp, row["fecha"])
            monto_viz = _convertir(monto, moneda_orig, moneda_viz, tc_dia)
            if pd.isna(monto) or monto is None:
                compras_sin_monto += 1
                continue
            if not pd.isna(monto_viz):
                costo_comp_viz += monto_viz
                costo_total_base += monto_viz
            if acc is not None and not pd.isna(acc):
                acciones_comp += float(acc)

        if compras_sin_monto:
            incompleto = True
            notas_q.append(f"{compras_sin_monto} compra(s) sin monto registrado")

        # Costo promedio por acción (en viz). Si no hay acciones (fondos CLP
        # registrados solo por monto), trabajamos a nivel de monto.
        costo_prom = (costo_comp_viz / acciones_comp) if acciones_comp > 0 else None

        # --- Ventas: caja recibida y costo de lo vendido ---
        acciones_vend = 0.0
        caja_ventas_viz = 0.0
        costo_vendido_viz = 0.0
        ventas_sin_compra = False
        for _, row in v.iterrows():
            monto = row["monto_nativo"]
            acc = row["acciones"]
            tc_dia = md.tc_asof(serie_usdclp, row["fecha"])
            monto_viz = _convertir(monto, moneda_orig, moneda_viz, tc_dia)
            if not pd.isna(monto_viz):
                caja_ventas_viz += monto_viz
            if acc is not None and not pd.isna(acc):
                acciones_vend += float(acc)
                if costo_prom is not None:
                    costo_vendido_viz += costo_prom * float(acc)

        acciones_actuales = acciones_comp - acciones_vend
        # Tolerancia a ruido de redondeo en fracciones de acción.
        if abs(acciones_actuales) < 1e-4:
            acciones_actuales = 0.0

        if acciones_comp == 0 and acciones_vend > 0:
            incompleto = True
            ventas_sin_compra = True
            notas_q.append("ventas sin compras registradas (costo no disponible)")

        # Costo remanente: costo de lo que sigue en cartera.
        if costo_prom is not None:
            costo_remanente = costo_prom * acciones_actuales
        else:
            # Fondos sin acciones: aproximamos costo remanente como
            # costo_total menos caja de ventas (flujo neto invertido vivo).
            costo_remanente = max(costo_comp_viz - caja_ventas_viz, 0.0)
            if acciones_vend == 0:
                costo_remanente = costo_comp_viz

        utilidad_realizada = caja_ventas_viz - costo_vendido_viz if costo_prom is not None else 0.0

        # --- Precio actual y valor de mercado ---
        precio_nat, fuente = _precio_actual(
            ticker, precios_manuales, precios_actuales_nativos
        )
        if acciones_actuales > 0:
            if precio_nat is not None:
                valor_nat = precio_nat * acciones_actuales
                valor_actual = _convertir(valor_nat, moneda_orig, moneda_viz, tc_hoy)
                if pd.isna(valor_actual):
                    valor_actual = 0.0
                    incompleto = True
                    notas_q.append("sin TC para valorizar")
            else:
                # Sin precio: usamos el costo remanente como proxy y marcamos.
                valor_actual = costo_remanente
                incompleto = True
                notas_q.append("sin precio de mercado (valor = costo)")
        else:
            valor_actual = 0.0  # posición cerrada

        # --- Dividendos ---
        div_viz = 0.0
        for _, row in d.iterrows():
            tc_dia = md.tc_asof(serie_usdclp, row["fecha"])
            m = _convertir(row["monto_nativo"], row["moneda_origen"], moneda_viz, tc_dia)
            if not pd.isna(m):
                div_viz += m

        resultados.append(
            PosicionResultado(
                ticker=ticker,
                nombre=info["nombre"],
                moneda_origen=moneda_orig,
                plataformas=info["plataformas"],
                acciones_actuales=acciones_actuales,
                costo_total_base=costo_total_base,
                costo_remanente=costo_remanente,
                valor_actual=valor_actual,
                dividendos=div_viz,
                caja_ventas=caja_ventas_viz,
                utilidad_realizada=utilidad_realizada,
                precio_actual_nativo=precio_nat,
                precio_fuente=fuente,
                incompleto=incompleto,
                notas_calidad=notas_q,
            )
        )

    return resultados


def _precio_actual(ticker, manuales, yf_nativos):
    """Devuelve (precio_nativo, fuente). Manual tiene prioridad sobre yfinance."""
    if ticker in manuales and manuales[ticker] not in (None, "", 0):
        try:
            return float(manuales[ticker]), "manual"
        except (TypeError, ValueError):
            pass
    sym = md.resolver_simbolo(ticker)
    if sym and sym in yf_nativos:
        return yf_nativos[sym], "yfinance"
    return None, "sin dato"


def _catalogo(data, plataforma):
    frames = []
    for key in ("compras", "ventas", "dividendos"):
        d = data[key]
        if plataforma:
            d = d[d["plataforma"] == plataforma]
        frames.append(d[["ticker", "nombre", "plataforma", "moneda_origen"]])
    todo = pd.concat(frames, ignore_index=True)
    cat = {}
    for ticker, g in todo.groupby("ticker"):
        nombres = g["nombre"].dropna()
        monedas = g["moneda_origen"].dropna()
        cat[ticker] = {
            "nombre": nombres.iloc[0] if len(nombres) else ticker,
            "moneda": monedas.mode().iloc[0] if len(monedas.mode()) else "USD",
            "plataformas": sorted(g["plataforma"].dropna().unique().tolist()),
        }
    return cat


def resumen_portafolio(posiciones: list[PosicionResultado]) -> dict:
    """Totales agregados del portafolio (en moneda de visualización)."""
    costo_total = sum(p.costo_total_base for p in posiciones)
    valor = sum(p.valor_actual for p in posiciones)
    div = sum(p.dividendos for p in posiciones)
    caja = sum(p.caja_ventas for p in posiciones)
    costo_rem = sum(p.costo_remanente for p in posiciones)
    realizada = sum(p.utilidad_realizada for p in posiciones)

    rent_precio = ((valor - costo_rem) + realizada) / costo_total if costo_total else None
    rent_div = div / costo_total if costo_total else None
    rent_total = (rent_precio + rent_div) if (rent_precio is not None and rent_div is not None) else None

    return {
        "costo_total": costo_total,
        "costo_remanente": costo_rem,
        "valor_actual": valor,
        "dividendos": div,
        "caja_ventas": caja,
        "utilidad_realizada": realizada,
        "rent_precio": rent_precio,
        "rent_dividendo": rent_div,
        "rent_total": rent_total,
        "n_posiciones": len(posiciones),
        "n_abiertas": sum(1 for p in posiciones if p.acciones_actuales > 0),
        "n_incompletas": sum(1 for p in posiciones if p.incompleto),
    }


def posiciones_a_dataframe(posiciones: list[PosicionResultado], moneda_viz: str) -> pd.DataFrame:
    filas = []
    for p in posiciones:
        filas.append({
            "Ticker": p.ticker,
            "Instrumento": p.nombre,
            "Plataforma": ", ".join(p.plataformas),
            "Moneda": p.moneda_origen,
            "Acciones": p.acciones_actuales,
            f"Costo invertido ({moneda_viz})": p.costo_total_base,
            f"Valor actual ({moneda_viz})": p.valor_actual,
            f"Dividendos ({moneda_viz})": p.dividendos,
            f"Realizado ({moneda_viz})": p.utilidad_realizada,
            "Rent. Precio": p.rent_precio,
            "Rent. Dividendo": p.rent_dividendo,
            "Rent. Total": p.rent_total,
            "Precio fuente": p.precio_fuente,
            "Estado": "Abierta" if p.acciones_actuales > 0 else "Cerrada",
            "Alerta datos": "; ".join(p.notas_calidad) if p.notas_calidad else "",
        })
    df = pd.DataFrame(filas)
    if not df.empty:
        df = df.sort_values(
            [f"Valor actual ({moneda_viz})"], ascending=False
        ).reset_index(drop=True)
    return df
