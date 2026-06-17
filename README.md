# Dashboard de Portafolio — Racional + Renta4

Dashboard en Streamlit para consolidar compras, ventas y dividendos de tus
instrumentos en **Racional** y **Renta4**, con instrumentos en **USD** y **CLP**.

## Qué hace

- **Tres vistas**: Portafolio total, solo Racional, solo Renta4.
- **Toggle de moneda**: ver todo en **USD** o en **CLP**.
- **Tres rentabilidades por instrumento**: por precio, por dividendo y total.
- **Sección de importación**: sube tu Excel actualizado cuando quieras.
- **Precios y tipo de cambio automáticos** vía Yahoo Finance (yfinance).
- **Precios manuales** para fondos locales (CFI/CFM) sin cotización pública.
- **Panel de calidad de datos** que marca posiciones con información faltante.

### Cómo se calcula

- **Costeo**: promedio ponderado.
- **Tipo de cambio**: el **costo histórico** de cada operación se convierte con
  el TC del día de la operación; el **valor de mercado actual** usa el TC de hoy.
  Así la rentabilidad en CLP de un activo en USD incorpora el efecto cambiario real.
- **Rent. precio** = ganancia de capital (incluye utilidad realizada) ÷ costo invertido.
- **Rent. dividendo** = dividendos recibidos ÷ costo invertido.
- **Rent. total** = suma de ambas.

## Estructura del archivo Excel

El archivo debe tener tres hojas: **Compras**, **Ventas**, **Dividendos**, con las
columnas del archivo original. Nota importante: las columnas "Precio USD"/"Monto USD"
contienen valores en **CLP** cuando la columna `Moneda` (o `Tipo Orden` en Ventas)
indica CLP — la app lo maneja automáticamente.

## Despliegue en GitHub + Streamlit Community Cloud

1. **Crea un repositorio** en GitHub (puede ser privado) y sube estos archivos
   manteniendo la estructura:

   ```
   portfolio-dashboard/
   ├── app.py
   ├── requirements.txt
   ├── README.md
   ├── .gitignore
   ├── .streamlit/config.toml
   ├── core/
   │   ├── __init__.py
   │   ├── data_loader.py
   │   ├── market_data.py
   │   └── portfolio.py
   └── data/
       └── Inversiones_Rac-Renta4.xlsx
   ```

   Desde la terminal:
   ```bash
   git init
   git add .
   git commit -m "Dashboard de portafolio Racional + Renta4"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/portfolio-dashboard.git
   git push -u origin main
   ```

2. Entra a **https://share.streamlit.io**, inicia sesión con GitHub.
3. **New app** → elige tu repositorio, rama `main`, y archivo principal `app.py`.
4. **Deploy**. La primera vez instala dependencias (1–2 min).

> Si el repo es privado, autoriza a Streamlit Cloud el acceso a tus repos privados
> durante el inicio de sesión con GitHub.

## Uso

- En la barra lateral eliges **vista** y **moneda**.
- Para actualizar tus datos, sube el nuevo `.xlsx` en **Importar base de datos**
  y pulsa **Usar archivo**. Vuelve a la base incluida con **Base original**.
- En **Calidad de datos y precios manuales** ingresa precios de fondos locales.
- **Actualizar precios de mercado** limpia la caché y vuelve a consultar yfinance.

## Ejecutar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Notas

- yfinance es un servicio no oficial; ocasionalmente algún símbolo puede no
  devolver precio. En esos casos usa el precio manual.
- Las acciones chilenas se consultan con sufijo `.SN` (ej. `FALABELLA.SN`).
  El mapeo de tickers está en `core/market_data.py` (`TICKER_MAP`); ajústalo si
  agregas instrumentos nuevos.
- Reporte informativo; no constituye asesoría de inversión.
