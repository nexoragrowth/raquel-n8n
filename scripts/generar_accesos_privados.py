# -*- coding: utf-8 -*-
"""
generar_accesos_privados.py — 2026-10-21 · arma el documento PRIVADO de accesos (ACCESOS.md) para entregar a la clínica / pasárselo a una IA.

Lee los valores de los .env locales (raquel-n8n/.env y nexora-whatsapp-agent/.env.local) y los acomoda con la estructura de docs/ACCESOS.template.md.
El archivo se escribe FUERA de los repositorios (por defecto C:\\Users\\<vos>\\Documents\\Asiri-Accesos\\ACCESOS.md) y se restringe a tu usuario de Windows.
NUNCA imprime un valor: solo dice qué claves quedaron completas y cuáles faltan. NUNCA se commitea (la carpeta está en .gitignore por si se la copia al repo).

USO:  python scripts/generar_accesos_privados.py                    # genera el archivo
      python scripts/generar_accesos_privados.py --salida D:\\ruta    # otra carpeta (siempre fuera de un repositorio)
Después: guardarlo CIFRADO (gestor de contraseñas, o 7-Zip con contraseña: clic derecho → 7-Zip → Añadir al archivo → cifrado AES-256) y entregárselo a la clínica
por un canal seguro. El archivo en claro se borra de la carpeta cuando ya está guardado cifrado.
"""
import argparse, getpass, json, os, re, subprocess, sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
PANEL = ROOT.parent / "nexora-whatsapp-agent"

# (grupo, [(clave a mostrar, [dónde buscarla en orden], descripción)])
SECCIONES = [
    ("1. n8n (el motor de Asiri) — https://n8n.raquelrodriguez.com.ar", [
        ("N8N_API_KEY", ["N8N_API_KEY"], "clave de la API de n8n (con esto una IA lee, prueba y modifica workflows)"),
        ("N8N_BASE_URL", ["N8N_BASE_URL", "N8N_API_BASE"], "dirección de n8n"),
    ]),
    ("2. Supabase v3 (base de datos del bot)", [
        ("SUPABASE_V3_URL", ["SUPABASE_V3_URL", "V3_SUPABASE_URL"], "dirección del proyecto"),
        ("SUPABASE_V3_SERVICE_ROLE_KEY", ["SUPABASE_V3_SERVICE_ROLE_KEY", "V3_SUPABASE_SERVICE_KEY"], "clave de servicio: lee y escribe todo (la más delicada)"),
        ("SUPABASE_V3_DB_HOST", ["SUPABASE_V3_DB_HOST"], "Postgres: servidor"),
        ("SUPABASE_V3_DB_PORT", ["SUPABASE_V3_DB_PORT"], "Postgres: puerto"),
        ("SUPABASE_V3_DB_NAME", ["SUPABASE_V3_DB_NAME"], "Postgres: base"),
        ("SUPABASE_V3_DB_USER", ["SUPABASE_V3_DB_USER"], "Postgres: usuario"),
        ("SUPABASE_V3_DB_PASSWORD", ["SUPABASE_V3_DB_PASSWORD"], "Postgres: contraseña"),
    ]),
    ("3. Evolution GO (conexión con WhatsApp) — https://evo.raquelrodriguez.com.ar", [
        ("EVOLUTION_INSTANCE", ["EVOLUTION_INSTANCE"], "nombre de la instancia (hoy: raquel)"),
        ("EVOLUTION_INSTANCE_TOKEN", ["EVOLUTION_INSTANCE_TOKEN", "EVOLUTION_API_KEY"], "token de la instancia (enviar mensajes, pedir fotos)"),
        ("EVOLUTION_GLOBAL_API_KEY", ["EVOLUTION_GLOBAL_API_KEY"], "clave de administración (lista instancias y sus tokens)"),
    ]),
    ("4. Dentalink (agenda y fichas)", [
        ("DENTALINK_BASE_URL", ["DENTALINK_BASE_URL"], "dirección de la API"),
        ("DENTALINK_TOKEN", ["DENTALINK_TOKEN"], "token de la API (límite: 60 pedidos por minuto)"),
    ]),
    ("5. OpenAI", [
        ("OPENAI_API_KEY", ["OPENAI_API_KEY"], "usada por n8n y por el panel"),
    ]),
    ("6. Panel — https://panel.raquelrodriguez.com.ar", [
        ("PANEL_SESSION_SECRET", ["PANEL_SESSION_SECRET"], "firma de las sesiones"),
        ("PANEL_USERS", ["PANEL_USERS"], "usuarios (las contraseñas están cifradas: no se pueden leer, solo reemplazar)"),
        ("PANEL_ADMINS", ["PANEL_ADMINS"], "usuarios administradores"),
        ("N8N_PANEL_WEBHOOK_BASE", ["N8N_PANEL_WEBHOOK_BASE"], "para que el panel mande mensajes y apague/prenda el bot"),
        ("N8N_PANEL_WEBHOOK_SECRET", ["N8N_PANEL_WEBHOOK_SECRET"], "secreto de esos webhooks"),
    ]),
]
FIJOS = """## 7. Servidor (VPS)
- Dirección: 187.127.0.110 · usuario `root` · clave SSH privada `~/.ssh/raquel_vps` (archivo en la computadora de Lucas: hay que entregar una copia por canal seguro).
- Contenedores: `nexora-panel` (panel), `redis-rwlw-redis-1` (Redis), `evolution-go-postgres`, `n8n-traefik-1`. Carpetas: `/opt/nexora-panel` (panel), `/docker/evolution-go` (Evolution).
- El `.env.production` del panel vive en `/opt/nexora-panel/.env.production` (ahí están las claves del panel en producción).

## 8. GitHub
- Repositorios: `nexoragrowth/raquel-n8n` (bot y documentación) y `LucasEzequielSilva/nexora-whatsapp-agent` (panel). Hace falta una cuenta con acceso.

## 9. Datos de operación
- Grupo de derivaciones de WhatsApp ("WhatsApp Clínica Raquel"): `120363407321448469@g.us`.
- Administradores del bot (pueden escribir `/bot off`, `/bot on`, `/bot status` al número de la clínica): ver `.claude/CLAUDE.md`.
- Soporte: Lucas (Nexora), pleno hasta febrero de 2027.

## Si una clave se filtra
Rotarla donde se emite, actualizarla en la MISMA ventana en n8n (credenciales) y en `/opt/nexora-panel/.env.production`, redesplegar el panel (`bash deploy/redeploy.sh`) y verificar con `python scripts/status.py`. Rotar sin actualizar los otros lugares tumba al bot o al panel.
"""


def leer_env(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for linea in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$", linea)
        if m and not linea.lstrip().startswith("#"):
            v = m.group(2).strip().strip('"').strip("'")
            if v:
                out[m.group(1)] = v
    return out


def token_instancia_desde_snapshot() -> str:
    """El token de la instancia está en el nodo 'Enviar WhatsApp' del snapshot local del workflow de Recordatorios (carpeta ignorada por git)."""
    f = ROOT / "workflows" / "current" / "recordatorios_7RqTApkvVavRmq3R.json"
    try:
        w = json.loads(f.read_text(encoding="utf-8"))
        n = next(x for x in w["nodes"] if x["name"] == "Enviar WhatsApp")["parameters"]
        return next(h["value"] for h in n["headerParameters"]["parameters"] if h["name"] == "apikey")
    except Exception:
        return ""


def dentro_de_un_repo(p: Path) -> bool:
    try:
        r = subprocess.run(["git", "-C", str(p), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(Path.home() / "Documents" / "Asiri-Accesos"))
    a = ap.parse_args()
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    if dentro_de_un_repo(salida):
        sys.exit("ABORTO: la carpeta de salida está dentro de un repositorio git. Elegí una fuera (por ejemplo Documents).")

    fuentes = {}
    for p in (ROOT / ".env", PANEL / ".env.local", PANEL / ".env.production"):
        for k, v in leer_env(p).items():
            fuentes.setdefault(k, v)
    if "EVOLUTION_INSTANCE_TOKEN" not in fuentes:
        t = token_instancia_desde_snapshot()
        if t:
            fuentes["EVOLUTION_INSTANCE_TOKEN"] = t

    lineas = [
        "# ACCESOS PRIVADOS — Asiri (Áurea Odontología Estética)",
        "",
        f"> Generado el {date.today().isoformat()}. **CONFIDENCIAL.** No subir a GitHub, no mandar por WhatsApp/mail sin cifrar. Guardar cifrado o en un gestor de contraseñas.",
        "> Para una IA: pasarle este archivo junto con `docs/DIAGNOSTICO_IA.md`. Con esto puede revisar y arreglar el sistema.",
        "",
    ]
    completas, faltan = [], []
    for titulo, claves in SECCIONES:
        lineas += [f"## {titulo}"]
        for nombre, donde, desc in claves:
            valor = next((fuentes[k] for k in donde if k in fuentes), "")
            (completas if valor else faltan).append(nombre)
            lineas.append(f"- `{nombre}` — {desc}\n  ```\n  {valor if valor else '(FALTA: pedirlo o completarlo a mano)'}\n  ```")
        lineas.append("")
    lineas.append(FIJOS)

    destino = salida / "ACCESOS.md"
    destino.write_text("\n".join(lineas), encoding="utf-8")
    # Restringir a tu usuario de Windows (quita la herencia y deja solo permisos para el usuario actual).
    if os.name == "nt":
        usuario = getpass.getuser()
        subprocess.run(["icacls", str(salida), "/inheritance:r", "/grant:r", f"{usuario}:(OI)(CI)F"], capture_output=True)
    print(f"Listo: {destino}")
    print(f"  claves completas ({len(completas)}): {', '.join(completas)}")
    print(f"  claves que faltan ({len(faltan)}): {', '.join(faltan) if faltan else 'ninguna'}")
    print("  (ningún valor se imprimió). Siguiente: guardarlo cifrado y borrar el archivo en claro.")


if __name__ == "__main__":
    main()
