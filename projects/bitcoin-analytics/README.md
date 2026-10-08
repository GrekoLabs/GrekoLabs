# Bitcoin Analytics

Proyecto analítico para trabajar con datos históricos y de tiempo real de Bitcoin.

El collector de Binance consulta market data público de Binance Spot y normaliza
velas OHLCV al esquema `BitcoinCandleCreate`. El backfill y la reparación escriben
candles cerradas en PostgreSQL con el servicio compartido del backend. No se
requieren credenciales de Binance.

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

## Historical backfill y gap repair

El backfill usa `SessionLocal`, el modelo `BitcoinCandle` y
`save_bitcoin_candles()` de `backend/`. El backend carga automáticamente
`backend/.env`; también se puede configurar `DATABASE_URL` en el entorno. La tabla
debe existir antes de ejecutar estos comandos. Los intervalos admitidos son `1m`,
`5m`, `15m`, `1h`, `4h` y `1d`; `all` los procesa en ese orden: `1d`, `4h`, `1h`,
`15m`, `5m`, `1m`.

Desde la raíz del repositorio, primero inspecciona el plan sin hacer solicitudes a
Binance ni escribir velas:

```bash
cd /home/grekolab/projects/GrekoLabs
projects/bitcoin-analytics/.venv/bin/python -m bitcoin_analytics.backfill \
  --interval 1d --start 2020-01-01 --dry-run
```

Para descargar el histórico completo cerrado hasta el límite actual:

```bash
projects/bitcoin-analytics/.venv/bin/python -m bitcoin_analytics.backfill \
  --interval 1d --start 2020-01-01
```

`--end` es exclusivo y, si se omite, corresponde al inicio de la última vela que
todavía está en formación. Fechas y horas sin zona se interpretan como UTC. Por
ejemplo, `--end 2024-01-01` incluye velas con timestamp anterior a esa medianoche.
`--limit` configura velas por página (entre 1 y el máximo real de Binance, 1000).
El comando pagina cronológicamente y persiste cada página; nunca carga toda la
historia en memoria.

La reanudación es segura: cada ejecución vuelve a buscar timestamps ausentes en el
rango solicitado, y la clave única con `ON CONFLICT DO NOTHING` hace idempotente la
persistencia. No se usa solo el máximo timestamp, así que también se retoman huecos
anteriores. Para detectar y reparar ausencias:

```bash
projects/bitcoin-analytics/.venv/bin/python -m bitcoin_analytics.repair \
  --interval 1d --start 2020-01-01
```

La detección agrupa timestamps contiguos con consultas PostgreSQL acotadas. Binance
solo aporta velas reales; no se sintetizan datos. Si la API no ofrece velas para un
período, se marca como no resuelto y se continúa. Se respetan reintentos limitados,
`Retry-After` y el bloqueo HTTP 418; anomalías o conflictos con filas existentes
se informan y nunca se sobrescriben. Cualquier error, conflicto o hueco no resuelto
produce código de salida distinto de cero. El modo `--dry-run` únicamente consulta
la base para contar rangos pendientes.

### Consultas SQL de verificación

Conteo y cobertura temporal de un intervalo:

```sql
SELECT count(*) AS candles,
       min(timestamp) AS first_candle,
       max(timestamp) AS last_candle
FROM bitcoin_candles
WHERE exchange = 'binance' AND symbol = 'BTCUSDT' AND interval = '1d';
```

Comprobar valores fuera de las invariantes OHLCV:

```sql
SELECT timestamp, open, high, low, close, volume
FROM bitcoin_candles
WHERE exchange = 'binance' AND symbol = 'BTCUSDT' AND interval = '1d'
  AND (high < GREATEST(open, close, low)
       OR low > LEAST(open, close, high)
       OR volume < 0);
```

La reparación es manual y puede generar bastantes solicitudes de red, especialmente
para intervalos cortos. No ejecute la carga histórica completa hasta haber revisado
el resultado del `--dry-run`; no hay scheduler ni se crea/modifica el esquema de la
base automáticamente.
