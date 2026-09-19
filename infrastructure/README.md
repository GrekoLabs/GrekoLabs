# Local PostgreSQL

PostgreSQL para el entorno de desarrollo local de GrekoLabs, administrado con Docker Compose.

## Configuración

Desde `infrastructure/`, crea el archivo local de variables de entorno:

```bash
cp .env.example .env
```

Reemplaza el valor de `POSTGRES_PASSWORD` por una contraseña local segura antes de iniciar el servicio. El archivo `.env` está ignorado por Git.

## Comandos

Levantar PostgreSQL en segundo plano:

```bash
docker compose up -d
```

Detener y eliminar el contenedor conservando los datos:

```bash
docker compose down
```

Ver los logs:

```bash
docker compose logs -f postgres
```

Eliminar el contenedor y el volumen para reiniciar completamente la base de datos:

```bash
docker compose down --volumes
```
