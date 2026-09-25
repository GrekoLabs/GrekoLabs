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
cd /home/grekolab/projects/GrekoLabs/projects/bitcoin-analytics
python3 -m venv .venv
source .venv/bin/activate
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

El archivo `requirements.txt` instala el paquete en modo editable y sus
dependencias de ejecución, incluido el acceso a la infraestructura SQLAlchemy
compartida del backend.

Ejecutar los tests unitarios:

```bash
cd /home/grekolab/projects/GrekoLabs
projects/bitcoin-analytics/.venv/bin/python -m pytest projects/bitcoin-analytics/tests -q
```

Realizar una consulta pequeña a Binance Spot:

```bash
cd /home/grekolab/projects/GrekoLabs
projects/bitcoin-analytics/.venv/bin/python -c 'from bitcoin_analytics.collectors.binance import fetch_klines; print(fetch_klines("BTCUSDT", "1h", limit=5, include_open_candle=False))'
```

La consulta usa el endpoint público y devuelve objetos normalizados sin escribir en
PostgreSQL.

## Carga local en PostgreSQL

La persistencia vive en `backend/` y usa la sesión SQLAlchemy compartida. El script
de desarrollo carga diez velas cerradas de `BTCUSDT` en `1h` e informa `received`,
`inserted` y `skipped`. Requiere que `DATABASE_URL` esté configurada en el entorno;
no incluye credenciales en el código.

Desde la raíz del repositorio, configura `DATABASE_URL` usando el archivo local
existente y ejecuta el módulo instalado:

```bash
cd /home/grekolab/projects/GrekoLabs
set -a
source infrastructure/.env
set +a
export DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT:-5432}/${POSTGRES_DB}"
projects/bitcoin-analytics/.venv/bin/python -m bitcoin_analytics.load_historical --create-tables
projects/bitcoin-analytics/.venv/bin/python -m bitcoin_analytics.load_historical
```

`--create-tables` es una acción explícita de desarrollo local: ejecuta
`Base.metadata.create_all(bind=engine)` antes de la primera carga. No se ejecuta al
importar módulos ni durante el arranque de FastAPI. La segunda ejecución demuestra
la idempotencia mediante la restricción única de `bitcoin_candles`.
