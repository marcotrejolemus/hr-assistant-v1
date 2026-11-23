# Imagen del HR Assistant v1 (spec/04, punto 5).
# Solo lleva lo necesario para correr: dependencias, app/ y data/.
# Ningún secreto va en la imagen: las claves llegan como variables de entorno
# de la plataforma (Render) o de quien corre el contenedor.
FROM python:3.12-slim

# Sin archivos .pyc, salida sin búfer (los logs JSON salen al momento) y pip sin
# caché ni aviso de versión, para una imagen más pequeña.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Usuario y grupo de sistema sin privilegios, sin shell de inicio de sesión.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home \
       --home-dir /app --shell /usr/sbin/nologin app

# Primero las dependencias, para aprovechar la caché de capas de Docker.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# El código y los datos sintéticos quedan como propiedad de root y de solo
# lectura para el usuario de la app: el proceso no puede modificarlos.
COPY app/ ./app/
COPY data/ ./data/

# Desde aquí todo corre sin root (mínimo privilegio).
USER 10001:10001

# Puerto por omisión; la plataforma puede cambiarlo con la variable PORT.
EXPOSE 8000

# Se usa sh -c para expandir ${PORT:-8000}; exec deja a uvicorn como PID 1 para
# que reciba las señales de apagado de la plataforma.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
