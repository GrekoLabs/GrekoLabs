# Bitcoin Analytics

Proyecto analítico para trabajar con datos históricos y de tiempo real de Bitcoin.

Los modelos persistentes y la configuración de acceso a PostgreSQL viven en `backend/`.
Este proyecto no administra su propio engine ni sesiones de SQLAlchemy; consume las
interfaces de persistencia del backend cuando sea necesario.

## Vela OHLCV

Una vela OHLCV representa el comportamiento de un símbolo durante un intervalo de tiempo:

- **Open**: precio de apertura.
- **High**: precio máximo.
- **Low**: precio mínimo.
- **Close**: precio de cierre.
- **Volume**: volumen negociado durante el intervalo.

Cada vela se identifica por el símbolo, el intervalo y su timestamp.

## Precisión financiera

Los precios y el volumen se modelan con `Numeric` y `Decimal` en lugar de `float`. Los números de punto flotante pueden introducir errores de representación binaria, algo que no es apropiado para cálculos financieros ni para comparar valores con precisión.

## Próximos pasos

- Definir migraciones para crear la tabla en PostgreSQL.
- Implementar la ingestión de datos históricos desde un exchange.
- Añadir ingestión de datos en tiempo real mediante WebSockets.
- Desarrollar análisis y generación de features.
- Incorporar forecasting y modelos de machine learning.
