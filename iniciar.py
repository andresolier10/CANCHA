"""Arranque local con apertura automática del navegador."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'dependencias'))

import threading
import webbrowser
from werkzeug.serving import make_server
from app import create_app


def main():
    app = create_app()
    # El sistema elige un puerto libre para evitar conflictos con otras apps.
    server = make_server('127.0.0.1', 0, app, threaded=True)
    url = f'http://127.0.0.1:{server.server_port}'
    checking = '--comprobar' in sys.argv
    check_result = []

    def open_browser():
        if checking:
            import urllib.request
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for path in ('/', '/api/session', '/api/tournaments', '/api/live', '/static/upgrade.js'):
                    with opener.open(url + path, timeout=10) as response:
                        if response.status != 200:
                            raise RuntimeError('No responde correctamente: ' + path)
                check_result.append(True)
                print('COMPROBACION CORRECTA: Python, dependencias, datos y servidor HTTP funcionan.')
            except Exception as error:
                print('Fallo en la comprobacion:', error)
            finally:
                server.shutdown()
            return
        try:
            # make_server ya ha enlazado y preparado el puerto de escucha.
            if not webbrowser.open(url):
                print('Abre esta direccion en tu navegador:', url)
        except Exception:
            print('Si no se abre el navegador, abre esta direccion:', url)

    print('\nCANCHA esta iniciando. El navegador se abrira automaticamente.')
    print('Direccion:', url)
    print('Mantén esta ventana abierta mientras uses CANCHA.')
    print('Para cerrar el servidor, presiona Ctrl+C.\n')
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    if checking:
        browser_thread.join(timeout=15)
        if not check_result:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
