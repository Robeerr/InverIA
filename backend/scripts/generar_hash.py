"""Genera el hash bcrypt de la contraseña de acceso, para APP_PASSWORD_HASH.

    cd backend && python scripts/generar_hash.py

POR QUÉ ESTE SCRIPT Y NO UNA ORDEN SUELTA

La contraseña se pide de forma interactiva y sin eco. Escribirla como argumento de
un comando la dejaría en el historial del intérprete —en Windows, PowerShell lo
guarda en ConsoleHost_history.txt, en texto plano y para siempre—, y en los logs
de cualquier consola web. Aquí no se escribe en pantalla, no se guarda en ningún
fichero y no viaja a ninguna parte: solo sale el hash.

POR QUÉ USA auth.py Y NO SU PROPIO BCRYPT

Llama a la MISMA función que verificará el login. Es lo único que garantiza que el
hash sea compatible: `auth.get_password_hash` trunca a 72 bytes antes de hashear
(bcrypt solo usa los primeros 72 y las versiones nuevas de la librería fallan en
vez de truncar), y un generador externo que trunque de otra forma produciría un
hash que luego no valida y dejaría fuera al único usuario.

El hash NO es secreto en el mismo sentido que la contraseña: es lo que se guarda en
el servidor. Pero tampoco hace falta enseñarlo a nadie; pégalo directamente en la
variable de entorno.
"""
import getpass
import os
import sys

# El script vive en backend/scripts/ y auth.py en backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth  # noqa: E402

LIMITE_BCRYPT = auth.BCRYPT_MAX_BYTES


def main() -> int:
    print("Generador del hash para APP_PASSWORD_HASH")
    print("La contraseña no se verá al escribirla, no se guarda y no se envía.\n")

    try:
        clave = getpass.getpass("Contraseña: ")
        repetida = getpass.getpass("Repítela:   ")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        return 1

    if not clave:
        print("\nNo has escrito nada.")
        return 1
    if clave != repetida:
        print("\nNo coinciden. Vuelve a intentarlo.")
        return 1

    bytes_clave = len(clave.encode("utf-8"))
    if auth.excede_limite_bcrypt(clave):
        # No es un aviso cosmético: bcrypt ignora lo que pase de 72 bytes, así que
        # una frase larga tendría caracteres finales que NO cuentan para entrar.
        print(f"\nAviso: tu contraseña ocupa {bytes_clave} bytes y bcrypt solo usa los "
              f"primeros {LIMITE_BCRYPT}. Todo lo que sobra es decorativo: para entrar "
              f"bastará con esos {LIMITE_BCRYPT} primeros bytes.")

    hash_generado = auth.get_password_hash(clave)

    # Comprobación en el sitio: si el hash no valida contra la misma contraseña,
    # algo va mal y es mejor saberlo ahora que al quedarte fuera de la app.
    if not auth.verify_password(clave, hash_generado):
        print("\nERROR: el hash generado no valida la contraseña. No lo uses.")
        return 2

    print("\nHash verificado. Cópialo en Render como APP_PASSWORD_HASH:\n")
    print(hash_generado)
    print("\nPégalo entero, incluido el prefijo $2b$. No lo entrecomilles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
