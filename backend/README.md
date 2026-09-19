# GrekoLabs API

API central de GrekoLabs construida con FastAPI y conectada a PostgreSQL mediante SQLAlchemy.

## Desarrollo local

Desde la raíz del repositorio, crea y activa el entorno virtual:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

Instala las dependencias:

```bash
python -m pip install -r requirements.txt
```

Crea la configuración local y reemplaza la contraseña de ejemplo por la definida en `infrastructure/.env`:

```bash
cp .env.example .env
```

El archivo `backend/.env` es local y está ignorado por Git. Su variable `DATABASE_URL` debe usar el formato:

```text
postgresql+psycopg://usuario:contraseña@host:puerto/base_de_datos
```

Con PostgreSQL en ejecución, inicia la API:

```bash
python -m uvicorn app.main:app --reload
```

## Verificación

En otra terminal, prueba los endpoints:

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/db
```

La documentación interactiva está disponible en `http://127.0.0.1:8000/docs`.
