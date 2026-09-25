# Bitcoin Analytics

Proyecto analítico para trabajar con datos históricos y de tiempo real de Bitcoin.

El collector de Binance consulta market data público de Binance Spot y normaliza
velas OHLCV al esquema `BitcoinCandleCreate`. En esta etapa solo descarga datos:
no guarda en PostgreSQL ni usa credenciales, WebSockets o collectors en tiempo real.
Por defecto excluye la vela cuya `close time` todavía está en el futuro; se puede
usar `include_open_candle=True` cuando también se necesite la vela en formación.

Los modelos persistentes y la configuración de acceso a PostgreSQL viven en `backend/`.
Este proyecto no administra su propio engine ni sesiones de SQLAlchemy; consume las
interfaces de persistencia del backend cuando sea necesario. El sistema está diseñado
para almacenar datos provenientes de múltiples exchanges.

## Vela OHLCV

Una vela OHLCV representa el comportamiento de un símbolo durante un intervalo de tiempo:

- **Open**: precio de apertura.
- **High**: precio máximo.
- **Low**: precio mínimo.
- **Close**: precio de cierre.
- **Volume**: volumen negociado durante el intervalo.

Cada vela se identifica por el exchange, el símbolo, el intervalo y su timestamp.

## Precisión financiera

Los precios y el volumen se modelan con `Numeric` y `Decimal` en lugar de `float`. Los números de punto flotante pueden introducir errores de representación binaria, algo que no es apropiado para cálculos financieros ni para comparar valores con precisión.

## Próximos pasos

- Definir migraciones para crear la tabla en PostgreSQL.
- Ampliar la ingestión histórica a más exchanges.
- Añadir ingestión de datos en tiempo real mediante WebSockets.
- Desarrollar análisis y generación de features.
- Incorporar forecasting y modelos de machine learning.

## Entorno local

Crear y activar el entorno virtual del proyecto:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Ejecutar los tests unitarios:

```bash
PYTHONPATH=src pytest
```

Realizar una consulta pequeña a Binance Spot:

```bash
PYTHONPATH=src python -c 'from collectors.binance import fetch_klines; print(fetch_klines("BTCUSDT", "1h", limit=5, include_open_candle=False))'
```

La consulta usa el endpoint público y devuelve objetos normalizados sin escribir en
PostgreSQL.
