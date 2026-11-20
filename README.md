# CANCHA

Aplicación web local para gestionar torneos, plantillas, alineaciones, resultados y eventos en vivo. Desarrollada con Python, Flask y SQLite.

## Instalación desde el código

Requiere Python 3.12 y pip. En Windows, desde la carpeta del proyecto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe iniciar.py
```

En Linux o macOS, utiliza `python3 -m venv .venv`, instala los requisitos con `.venv/bin/python -m pip install -r requirements.txt` y ejecuta `.venv/bin/python iniciar.py`.

El navegador se abre automáticamente. Crea el administrador la primera vez. El servidor escucha solo en este equipo; subir este repositorio a GitHub no publica la aplicación en Internet.

## Funciones

- Liga, grupos, fase liguera y eliminación directa.
- Cuadros y configuración inicial de ida y vuelta por cruce.
- Plantillas editables, convocados, titulares y formaciones.
- Eventos con autor, sustituciones y elegibilidad según el minuto.
- Ficha con resumen, alineaciones y estadísticas comparativas.
- Noticias basadas en los datos registrados.
- Centro de partidos en vivo y estimaciones exploratorias.

Consulta [NOVEDADES.md](NOVEDADES.md) para reglas y límites.

## Datos locales

Las cuentas y los torneos se crean en `instance/`. Esa carpeta, las claves y los respaldos se excluyen del repositorio. La edición portátil del escritorio incluye Python y dependencias; esta copia de código los instala con pip.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```
