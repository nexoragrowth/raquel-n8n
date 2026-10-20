# -*- coding: utf-8 -*-
"""Arma un documento para la Dra. (markdown → HTML imprimible → PDF con Edge headless).
v2 (14/10): portada desde el comentario <!-- portada: {...} --> de la línea 2, esquemas [DIAGRAMA: id], diálogos como chat,
colores forzados en la impresión y números de página. Reutiliza los gráficos del generador del 13/10.

USO: python scripts/informes/armar_pdf.py <archivo.md> "<nombre del pdf>.pdf"     (el PDF queda en data/informes/, que está en .gitignore)
     Antes: python scripts/informes/verificar_md.py <archivo.md>   ·   Para revisar páginas: python scripts/informes/rasterizar.py <pdf> <prefijo_png>
     Portada (línea 2 del md): <!-- portada: {"sub": "...", "para": "...", "fecha": "dd/mm/aaaa", "compacto": true} -->  (compacto: cuestionarios)
"""
import html, json, re, subprocess, sys
from pathlib import Path

import markdown

sys.path.insert(0, str(Path(__file__).resolve().parent))
import armar_informe_pdf as base   # hbar, vbar, linea, grafico, limpiar, colores

sys.stdout.reconfigure(encoding="utf-8")
R = Path(r"C:\Users\not\Desktop\proyectos\raquel-n8n")
DATOS = R / "docs" / "informe-dra-raquel-2026-10-13-datos.json"
OUT = R / "data" / "informes"            # data/ está en .gitignore
ACENTO, ACENTO_2, TEXTO, SUAVE, GRILLA, ALERTA = base.ACENTO, base.ACENTO_2, base.TEXTO, base.SUAVE, base.GRILLA, base.ALERTA
esc = html.escape


def caja(titulo, cuerpo="", cls=""):
    return f'<div class="dg-caja {cls}"><b>{titulo}</b>{f"<span>{cuerpo}</span>" if cuerpo else ""}</div>'


FLECHA_V = '<div class="dg-flecha">↓</div>'


def columna(titulo, pasos, cls):
    partes = []
    for i, p in enumerate(pasos):
        if i: partes.append(FLECHA_V)
        partes.append(p)
    return f'<div class="dg-col {cls}"><div class="dg-tit">{titulo}</div>{"".join(partes)}</div>'


DIAGRAMAS = {
    "antes_y_ahora": lambda: (
        '<div class="dg dg-2col">'
        + columna("Asiri actual", [
            caja("Llega el mensaje"),
            caja("Elige UN solo tema", "de una lista fija"),
            caja("Responde el asistente de ese tema", "cada uno trabaja por su lado"),
            caja("Si no encaja en ningún tema", "pasa a la secretaria", "dg-gris"),
        ], "dg-antes")
        + columna("Asiri nueva", [
            caja("Llega el mensaje"),
            caja("El coordinador lee todo", "y arma la lista de pedidos"),
            '<div class="dg-chips"><span>Turnos</span><span>Pagos</span><span>Información</span><span>Urgencias</span></div>',
            caja("Control final", "contra la agenda real"),
            caja("Una sola respuesta, clara", "", "dg-fuerte"),
        ], "dg-ahora")
        + "</div>"),
    "tipos_contacto": lambda: (
        '<div class="dg"><div class="dg-2col">'
        '<div class="dg-col dg-ahora"><div class="dg-tit">Asiri responde</div>'
        + caja("Pacientes") + caja("Familiares", "mamá, papá o tutor que escribe por un paciente") + caja("Contactos nuevos", "personas que consultan por primera vez")
        + '</div><div class="dg-col dg-antes"><div class="dg-tit">Asiri no responde: quedan para la secretaria</div>'
        + caja("La Dra. y el equipo", "", "dg-gris") + caja("Colegas y centros de imágenes", "", "dg-gris") + caja("Proveedores y laboratorios", "", "dg-gris")
        + caja("Otros que no son pacientes", "conocidos, empresas, números equivocados", "dg-gris")
        + '</div></div><div class="dg-nota"><b>Red de seguridad:</b> si un colega, un proveedor u otro contacto que no es paciente escribe algo urgente, Asiri no le contesta, pero avisa al grupo. Con la Dra. y el equipo no se usa.</div></div>'),
    "sistema_unico": lambda: (
        '<div class="dg dg-2col">'
        '<div class="dg-col dg-antes"><div class="dg-tit">Hoy</div>'
        + caja("WhatsApp → Asiri") + FLECHA_V + caja("Asiri le pregunta a Dentalink en cada paso", "si Dentalink falla, pasa a la secretaria", "dg-gris")
        + caja("El panel y Dentalink van por separado", "", "dg-gris") + caja("Contactos sin tipo", "todos figuran igual", "dg-gris")
        + '</div><div class="dg-col dg-ahora"><div class="dg-tit">Horizonte</div>'
        + '<div class="dg-chips"><span>Asiri</span><span>Panel</span></div>' + FLECHA_V
        + '<div class="dg-base"><div class="dg-tit2">Una sola base</div>'
        + caja("Contactos y familias") + caja("Agenda") + caja("Recorrido de cada paciente") + "</div>"
        + caja("Dentalink", "de respaldo hasta que todo coincida", "dg-gris")
        + "</div></div>"),
    "recorrido_paciente": lambda: (
        '<div class="dg"><div class="dg-fila">'
        + "".join(f'<div class="dg-etapa">{e}</div>' for e in
            ("Consultó", "Turno agendado", "Vino a la primera consulta", "Presupuesto", "En tratamiento", "Contención o alta"))
        + '</div><div class="dg-desvios"><span class="dg-etiq">Desvíos:</span>'
        + '<div class="dg-desvio">No vino <small>tenía turno y no asistió</small></div><div class="dg-desvio">Perdido <small>dijo que no o dejó de responder</small></div>'
        + '<div class="dg-desvio">Dormido <small>paciente que no viene hace meses</small></div></div>'
        + '<div class="dg-nota">Cada paso avanza solo, con hechos: un turno reservado, un recordatorio confirmado, una cita marcada "Atendido".</div></div>'),
}


def chats(cuerpo):
    """Bloques de cita con **Paciente:** / **Asiri:** → burbujas de chat."""
    def conv(m):
        dentro = m.group(1)
        if not re.search(r"<p><strong>(Paciente|Asiri):</strong>", dentro):
            return m.group(0)
        burbujas, cur = [], None
        for el in re.finditer(r"<(p|ol|ul)>(.*?)</\1>", dentro, re.S):
            tag, txt = el.group(1), el.group(2)
            q = re.match(r"<strong>(Paciente|Asiri):</strong>\s*(.*)", txt, re.S) if tag == "p" else None
            if q:
                cur = {"quien": q.group(1), "html": f"<p>{q.group(2)}</p>" if q.group(2).strip() else ""}
                burbujas.append(cur)
            elif cur is not None:
                cur["html"] += f"<{tag}>{txt}</{tag}>"
        return '<div class="chat">' + "".join(
            f'<div class="burbuja {b["quien"].lower()}"><span class="quien">{b["quien"]}</span>{b["html"]}</div>' for b in burbujas) + "</div>"
    return re.sub(r"<blockquote>(.*?)</blockquote>", conv, cuerpo, flags=re.S)


def recuadros(cuerpo):
    """Citas que empiezan con **En una página** o **Si sos la Dra.…** → recuadro destacado (resumen para leer en el celular)."""
    return re.sub(r"<blockquote>\s*<p><strong>(En una página|Si sos la Dra\.[^<]*)</strong>\s*</p>",
                  lambda m: f'<blockquote class="recuadro"><p class="rq-tit">{m.group(1)}</p>', cuerpo)


CSS = f"""
@page {{ size: A4; margin: 17mm 16mm 18mm 16mm; @bottom-right {{ content: counter(page); font: 8.5pt "Segoe UI", Arial, sans-serif; color: {SUAVE}; }} }}
@page :first {{ @bottom-right {{ content: none; }} }}
* {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: {TEXTO}; font-size: 10.6pt; line-height: 1.5; margin: 0; background: #fff; }}
.portada {{ height: 255mm; display: flex; flex-direction: column; justify-content: space-between; page-break-after: always; }}
.portada .marca {{ font-size: 10pt; letter-spacing: .14em; text-transform: uppercase; color: {ACENTO}; font-weight: 600; }}
.portada h1 {{ font-family: Georgia, "Times New Roman", serif; font-size: 33pt; line-height: 1.12; margin: 58mm 0 6mm; color: {TEXTO}; font-weight: 600; text-wrap: balance; }}
.portada .sub {{ font-size: 13pt; color: {SUAVE}; max-width: 140mm; }}
.portada .pie {{ border-top: 2px solid {ACENTO}; padding-top: 5mm; font-size: 10pt; color: {SUAVE}; display: flex; justify-content: space-between; }}
h2 {{ font-family: Georgia, "Times New Roman", serif; font-size: 18.5pt; color: {ACENTO}; margin: 8mm 0 3mm; font-weight: 600; text-wrap: balance; page-break-after: avoid; }}
h2.salto {{ page-break-before: always; margin-top: 0; padding-top: 2mm; border-bottom: 2px solid {ACENTO}; padding-bottom: 2mm; }}
h3 {{ font-size: 12.3pt; margin: 6.5mm 0 2mm; color: {TEXTO}; page-break-after: avoid; text-wrap: balance; }}
h4 {{ font-size: 11pt; margin: 5mm 0 1.5mm; page-break-after: avoid; }}
p {{ margin: 0 0 2.6mm; }}
ul, ol {{ margin: 0 0 3mm; padding-left: 6mm; }}
li {{ margin: 0 0 1.2mm; }}
strong {{ color: #0b1a1d; }}
blockquote {{ margin: 2.5mm 0 4.5mm; padding: 3mm 5mm; background: #eef6f5; border-left: 3px solid {ACENTO}; color: {TEXTO}; font-size: 10pt; page-break-inside: avoid; border-radius: 0 4px 4px 0; }}
blockquote p:last-child {{ margin-bottom: 0; }}
blockquote.recuadro {{ background: #f3f9f8; border: 2px solid {ACENTO}; border-radius: 6px; padding: 5mm 6mm; font-size: 11pt; line-height: 1.5; margin: 0 0 5mm; page-break-inside: auto; }}
blockquote.recuadro .rq-tit {{ font-family: Georgia, "Times New Roman", serif; font-size: 17pt; color: {ACENTO}; font-weight: 600; margin: 0 0 3mm; }}
blockquote.recuadro ul, blockquote.recuadro ol {{ margin-bottom: 2.5mm; }}
blockquote.recuadro li {{ margin-bottom: 1.4mm; }}
table {{ width: 100%; border-collapse: collapse; margin: 2mm 0 5mm; font-size: 9.1pt; page-break-inside: auto; }}
th {{ text-align: left; background: #eef3f3; color: {TEXTO}; font-weight: 600; padding: 2mm 2.2mm; border-bottom: 1.5px solid {ACENTO_2}; }}
td {{ padding: 1.8mm 2.2mm; border-bottom: 1px solid {GRILLA}; vertical-align: top; }}
tr {{ page-break-inside: avoid; }}
.box {{ font-size: 11pt; color: {ACENTO}; }}
figure.graf {{ margin: 4mm 0 6mm; padding: 4mm 4mm 2mm; border: 1px solid {GRILLA}; border-radius: 4px; page-break-inside: avoid; }}
figure.graf figcaption {{ font-weight: 600; font-size: 10.5pt; margin-bottom: 2mm; color: {TEXTO}; }}
.fuente {{ font-size: 8pt; color: {SUAVE}; margin: 1.5mm 0 0; line-height: 1.35; }}
svg text.lab {{ font-size: 11.5px; fill: {TEXTO}; }} svg text.val {{ font-size: 11.5px; fill: {TEXTO}; font-weight: 600; }}
svg text.valsm {{ font-size: 10px; fill: {TEXTO}; }} svg text.ax {{ font-size: 10px; fill: {SUAVE}; }}
em {{ color: {SUAVE}; }}
/* esquemas */
.dg {{ margin: 4mm 0 6mm; page-break-inside: avoid; font-size: 9.6pt; }}
.dg-2col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6mm; }}
.dg.dg-2col {{ margin: 4mm 0 6mm; }}
.dg-col {{ border: 1px solid {GRILLA}; border-radius: 6px; padding: 3.5mm; display: flex; flex-direction: column; gap: 2mm; align-items: stretch; }}
.dg-ahora {{ border-color: {ACENTO_2}; background: #f3f9f8; }}
.dg-tit {{ font-weight: 700; font-size: 10.5pt; color: {ACENTO}; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 1mm; }}
.dg-antes .dg-tit {{ color: {SUAVE}; }}
.dg-tit2 {{ font-weight: 700; color: {ACENTO}; text-align: center; margin-bottom: 1mm; }}
.dg-caja {{ border: 1px solid {ACENTO_2}; background: #fff; border-radius: 5px; padding: 2mm 3mm; text-align: center; }}
.dg-caja b {{ display: block; }} .dg-caja span {{ display: block; color: {SUAVE}; font-size: 8.8pt; }}
.dg-gris {{ border-color: {GRILLA}; background: #f6f7f7; color: {SUAVE}; }} .dg-gris b {{ color: {TEXTO}; font-weight: 600; }}
.dg-fuerte {{ background: {ACENTO}; border-color: {ACENTO}; }} .dg-fuerte b {{ color: #fff; }}
.dg-flecha {{ text-align: center; color: {ACENTO_2}; font-size: 12pt; line-height: 1; }}
.dg-chips {{ display: flex; flex-wrap: wrap; gap: 1.5mm; justify-content: center; }}
.dg-chips span {{ border: 1px solid {ACENTO}; color: {ACENTO}; border-radius: 99px; padding: .8mm 3mm; font-weight: 600; background: #fff; }}
.dg-base {{ border: 2px solid {ACENTO}; border-radius: 6px; padding: 2.5mm; display: flex; flex-direction: column; gap: 1.5mm; background: #fff; }}
.dg-nota {{ margin-top: 3mm; font-size: 9.2pt; color: {TEXTO}; background: #fbf3ee; border-left: 3px solid {ALERTA}; padding: 2mm 3mm; border-radius: 0 4px 4px 0; }}
.dg-fila {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 5mm; align-items: stretch; }}
.dg-etapa {{ position: relative; border: 1px solid {ACENTO}; background: #f3f9f8; border-radius: 5px; padding: 2mm 1.5mm; font-weight: 600; text-align: center; font-size: 9pt; display: flex; align-items: center; justify-content: center; }}
.dg-etapa:not(:last-child)::after {{ content: "→"; position: absolute; right: -4.3mm; top: 50%; transform: translateY(-50%); color: {ACENTO}; font-weight: 400; }}
.dg-desvio {{ border: 1px dashed {ALERTA}; background: #fbf3ee; border-radius: 5px; padding: 1.5mm 3mm; font-weight: 600; font-size: 9pt; text-align: center; }}
.dg-desvio small {{ display: block; font-weight: 400; color: {SUAVE}; font-size: 8pt; }}
.dg-desvios {{ display: flex; flex-wrap: wrap; align-items: center; gap: 2mm; margin-top: 3mm; }}
.dg-etiq {{ color: {SUAVE}; font-size: 9pt; text-transform: uppercase; letter-spacing: .06em; }}
/* chat */
.chat {{ margin: 3mm 0 5mm; padding: 4mm; background: #efeae2; border-radius: 6px; display: flex; flex-direction: column; gap: 2.2mm; page-break-inside: avoid; }}
.burbuja {{ max-width: 80%; padding: 2mm 3.2mm; border-radius: 6px; font-size: 9.8pt; box-shadow: 0 .3mm .6mm rgba(0,0,0,.12); }}
.burbuja p {{ margin: 0 0 1mm; }} .burbuja p:last-child {{ margin: 0; }} .burbuja ol, .burbuja ul {{ margin: 0 0 1mm; padding-left: 5mm; }}
.burbuja .quien {{ display: block; font-size: 7.8pt; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; margin-bottom: .6mm; }}
.burbuja.paciente {{ align-self: flex-end; background: #d9fdd3; }} .burbuja.paciente .quien {{ color: #2b6b3a; }}
.burbuja.asiri {{ align-self: flex-start; background: #fff; }} .burbuja.asiri .quien {{ color: {ACENTO}; }}
p:has(+ .chat), p:has(+ figure), p:has(+ .dg) {{ break-after: avoid; page-break-after: avoid; }}
"""

# Modo compacto (cuestionarios y documentos de trabajo): misma estética, más contenido por hoja.
CSS_COMPACTO = f"""
@page {{ margin: 14mm 14mm 15mm 14mm; }}
body {{ font-size: 9.8pt; line-height: 1.42; }}
h2 {{ font-size: 16.5pt; margin: 6mm 0 2.5mm; }}
h3 {{ font-size: 11.3pt; margin: 5mm 0 1.6mm; }}
p {{ margin: 0 0 2mm; }} li {{ margin: 0 0 .8mm; }}
table {{ font-size: 8.5pt; margin: 1.5mm 0 4mm; }} th {{ padding: 1.5mm 1.8mm; }} td {{ padding: 1.3mm 1.8mm; }}
.chat {{ padding: 3mm; gap: 1.6mm; margin: 2mm 0 4mm; }} .burbuja {{ font-size: 9.2pt; padding: 1.6mm 2.8mm; }}
blockquote.recuadro {{ font-size: 10.2pt; }}
"""


def main():
    md_path = Path(sys.argv[1])
    pdf_out = OUT / sys.argv[2]
    datos = {g["id"]: g for g in json.loads(DATOS.read_text(encoding="utf-8"))["graficos"]}
    lineas = md_path.read_text(encoding="utf-8").splitlines()
    titulo = lineas[0].lstrip("# ").strip()
    portada = {"sub": "", "para": "Para la Dra. Raquel Rodríguez", "fecha": "14/10/2026"}
    resto = lineas[1:]
    m = re.match(r"\s*<!--\s*portada:\s*(\{.*\})\s*-->\s*$", resto[0] if resto else "")
    if m:
        portada.update(json.loads(m.group(1))); resto = resto[1:]
    sep = []
    for i, l in enumerate(resto):   # una línea en blanco entre dos citas las separa (Python-Markdown las fusiona)
        if not l.strip() and sep and sep[-1].lstrip().startswith(">") and i + 1 < len(resto) and resto[i + 1].lstrip().startswith(">"):
            sep += ["", "<!-- -->", ""]
        else:
            sep.append(l)
    cuerpo = markdown.markdown("\n".join(sep), extensions=["tables", "sane_lists"])
    usados, problemas = [], []

    def poner_g(mm):
        gid = mm.group(1).strip()
        if gid in datos:
            usados.append(gid); return base.grafico(datos[gid])
        problemas.append("gráfico " + gid); return f'<p class="fuente">[gráfico no encontrado: {esc(gid)}]</p>'

    def poner_d(mm):
        did = mm.group(1).strip()
        if did in DIAGRAMAS:
            usados.append(did); return DIAGRAMAS[did]()
        problemas.append("diagrama " + did); return f'<p class="fuente">[esquema no encontrado: {esc(did)}]</p>'

    cuerpo = re.sub(r"<p>\[GRAFICO:\s*([^\]]+)\]</p>", poner_g, cuerpo)
    cuerpo = re.sub(r"<p>\[DIAGRAMA:\s*([^\]]+)\]</p>", poner_d, cuerpo)
    cuerpo = recuadros(chats(cuerpo))
    cuerpo = re.sub(r'</div>\s*<!-- -->\s*<div class="chat">', "", cuerpo)   # un diálogo partido en varias citas = un solo chat
    cuerpo = re.sub(r"<h2>(Parte |Anexo)", r'<h2 class="salto">\1', cuerpo)
    cuerpo = cuerpo.replace("<hr />", "").replace("☐", '<span class="box">☐</span>')
    pagina = f"""<section class="portada">
      <div><div class="marca">Áurea Odontología Estética · Asiri</div><h1>{esc(titulo)}</h1><div class="sub">{esc(portada['sub'])}</div></div>
      <div class="pie"><span>{esc(portada['para'])}</span><span>Nexora · {esc(portada['fecha'])}</span></div></section>"""
    css = CSS + (CSS_COMPACTO if portada.get("compacto") else "")
    doc = f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{esc(titulo)}</title><style>{css}</style></head><body>{pagina}<main>{cuerpo}</main></body></html>'
    html_out = OUT / (md_path.stem + ".html")
    html_out.write_text(doc, encoding="utf-8")
    sueltos = re.findall(r"\[(?:GRAFICO|DIAGRAMA):[^\]]*\]", cuerpo)
    print("html ok", html_out.name, "| usados:", usados, "| problemas:", problemas + sueltos)
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    r = subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf_out}", html_out.as_uri()],
                       capture_output=True, text=True, timeout=180)
    print("edge rc", r.returncode, (r.stderr or "")[-300:])
    print("pdf", pdf_out, pdf_out.exists() and pdf_out.stat().st_size)


if __name__ == "__main__":
    main()
