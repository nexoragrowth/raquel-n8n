# -*- coding: utf-8 -*-
"""
etiquetar_contactos_20261020.py — 2026-10-20 · a pedido de Lucas ("acomodá los contactos con el etiquetado"): carga los tipos de contacto que
SILENCIAN al bot para los que no son pacientes, con autor "claude" y la evidencia en la nota (motivo `clasificacion_manual`).

Qué se carga (solo tipos que silencian; cada uno con la red de seguridad salvo `interno`):
  1. Las 14 propuestas de la lista semilla del 14/10 (nombres de comercio: farmacias, American Orthodontics, Tecnodent, limpieza, etc.):
     se toman de data/contactos/lista_semilla_final_2026-10-14.json (gitignored) por su tipo propuesto.
  2. Un dudoso de esa lista que resultó proveedor por sus mensajes (fabricante de ambos), por sufijo.
  3. Los dos contactos de las escalaciones del 20/10 que no son pacientes: 380 (…8700, "Irina" en la lista: insumos y fotos de cajas
     de Odontoland → interno) y 383 (proveedor de insumos al que la clínica le pide hilos, yeso, papel de articular → proveedor).
Ningún teléfono va en este archivo (el repo es público). `contacto_tipo_poner` se niega sola si el contacto tiene ficha (TIENE_FICHA).

USO:  python scripts/etiquetar_contactos_20261020.py            # simulación (solo lee)
      python scripts/etiquetar_contactos_20261020.py --apply    # una transacción: si una falla, no queda ninguna
Deshacer uno: desde el panel ("Paciente / contacto nuevo") o public.contacto_tipo_cerrar(tel, tipo, 'correccion', 'claude').
"""
import argparse, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_migracion_contacto_tipos import conectar

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
LISTA = ROOT / "data" / "contactos" / "lista_semilla_final_2026-10-14.json"
AUTOR = "claude"
NOTA_LUCAS = " Cargado por Claude a pedido de Lucas (20/10)."
DUDOSOS_PROVEEDOR = {"2986": "Dudoso de la lista 14/10: sus mensajes son de un fabricante de ambos/indumentaria ofreciendo productos."}
ESCALACIONES = {380: ("interno", "Escalaciones 380/381 del 20/10: manda nombres de insumos y fotos de cajas de Odontoland; en la lista 14/10 figura «Irina» (celular de la secretaria)."),
                383: ("proveedor", "Escalación 383 del 20/10: proveedor de insumos (la clínica le pide hilos elásticos, papel de articular, yeso)."),
                384: ("proveedor", "Escalaciones 384/385 del 20/10: plomero (arreglo de un grifo que pierde agua en el consultorio); la charla la empezó la clínica."),
                386: ("proveedor", "Escalación 386 del 20/10: técnico/proveedor que manda fotos de un componente para verificar medidas; la charla la empezó la clínica el 29/09.")}


def plan(cur):
    items = json.loads(LISTA.read_text(encoding="utf-8"))
    items = items if isinstance(items, list) else items.get("contactos", [])
    out = []
    for x in items:
        tel = re.sub(r"\D", "", str(x.get("tel") or ""))
        motivo = x.get("motivo") or ""
        if x.get("tipo") in ("proveedor", "no_paciente", "colega") and not motivo.startswith("clasificado por Lucas"):
            out.append((tel, x["tipo"], f"Propuesta de la lista semilla 14/10 por nombre de comercio ({motivo})."))
        elif x.get("tipo") == "dudoso" and tel[-4:] in DUDOSOS_PROVEEDOR:
            out.append((tel, "proveedor", DUDOSOS_PROVEEDOR[tel[-4:]]))
    for lid, (tipo, nota) in ESCALACIONES.items():
        cur.execute("select telefono from public.escalaciones_log where id = %s", (lid,))
        r = cur.fetchone()
        if r:
            out.append((re.sub(r"\D", "", r[0]), tipo, nota))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); a = ap.parse_args()
    c = conectar(solo_lectura=not a.apply); cur = c.cursor()
    p = plan(cur)
    print(f"{len(p)} contactos a etiquetar:")
    for tel, tipo, nota in p:
        cur.execute("select public.contacto_ruta(%s)", (tel,)); ruta = cur.fetchone()[0] or {}
        cur.execute("select count(*) from public.recordatorios_enviados where telefono = %s", (tel,)); ficha = cur.fetchone()[0] > 0
        print(f"  …{tel[-4:]}  {tipo:<12} hoy: {ruta.get('tipo') or 'sin tipo':<10} ficha: {'SÍ' if ficha else 'no'}")
    if not a.apply:
        print("\n[SIMULACIÓN] No se escribió nada. Para cargar: --apply"); return
    res = []
    try:
        for tel, tipo, nota in p:
            cur.execute("select public.contacto_tipo_poner(%s, %s, 'clasificacion_manual', %s, 'script', null, %s, null, false)", (tel, tipo, AUTOR, nota + NOTA_LUCAS))
            r = cur.fetchone()[0]
            if not r.get("ok"):
                raise RuntimeError(f"…{tel[-4:]} {tipo}: {r.get('error')}")
            res.append((tel, tipo, "ya estaba" if r.get("ya_estaba") else "alta", (r.get("ruta") or {}).get("silencia")))
        c.commit()
    except Exception as e:
        c.rollback(); sys.exit(f"ABORTO (no se cargó ninguno): {e}")
    for tel, tipo, que, sil in res:
        print(f"  …{tel[-4:]}  {tipo:<12} {que:<9} silencia={sil}")
    print(f"Listo: {sum(1 for r in res if r[2] == 'alta')} altas, {sum(1 for r in res if r[2] != 'alta')} ya estaban.")


if __name__ == "__main__":
    main()
