# -*- coding: utf-8 -*-
"""Arma el informe para la Dra. (markdown + datos de gráficos) como HTML imprimible y lo pasa a PDF con Edge headless."""
import html, json, re, subprocess, sys
from pathlib import Path
import markdown

sys.stdout.reconfigure(encoding="utf-8")
R = Path(r"C:\Users\not\Desktop\proyectos\raquel-n8n")
MD = Path(sys.argv[1]) if len(sys.argv) > 1 else R / "docs" / "informe-dra-raquel-2026-10-13.md"
DATOS = R / "docs" / "informe-dra-raquel-2026-10-13-datos.json"
OUT = R / "data" / "informes"            # data/ está en .gitignore (el repo es público)
OUT.mkdir(parents=True, exist_ok=True)
HTML_OUT = OUT / (MD.stem + ".html")
PDF_OUT = OUT / (sys.argv[2] if len(sys.argv) > 2 else "Asiri - informe para la Dra. Raquel (borrador 13-10-2026).pdf")

ACENTO, ACENTO_2, TEXTO, SUAVE, GRILLA, ALERTA = "#0e6b67", "#7fb8b3", "#1d2a2e", "#5b6b70", "#e2e8e8", "#b4532a"
esc = html.escape


def wrap(txt, n):
    palabras, lineas, cur = str(txt).split(), [], ""
    for p in palabras:
        if len(cur) + len(p) + 1 > n and cur:
            lineas.append(cur); cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur: lineas.append(cur)
    return lineas[:3]


def fmt(v, pct=False):
    if pct: return f"{v:.0f} %"
    return f"{v:,.0f}".replace(",", ".") if float(v).is_integer() else f"{v:.1f}".replace(".", ",")


def hbar(etiquetas, valores, pct_de_total=False, sufijo_pct=False, resaltar=()):
    total = sum(valores) or 1
    W, LAB, ROW = 680, 270, 30
    alto_filas = [max(1, len(wrap(e, 38))) for e in etiquetas]
    H = sum(max(ROW, 14 * a + 12) for a in alto_filas) + 10
    vmax = max(valores) or 1
    barra_max = W - LAB - 90
    y, partes = 6, []
    for e, v, a in zip(etiquetas, valores, alto_filas):
        h = max(ROW, 14 * a + 12)
        cy = y + h / 2
        lineas = wrap(e, 38)
        for i, l in enumerate(lineas):
            ly = cy - (len(lineas) - 1) * 7 + i * 14 + 4
            partes.append(f'<text x="{LAB - 10}" y="{ly:.1f}" text-anchor="end" class="lab">{esc(l)}</text>')
        bw = max(2, barra_max * v / vmax)
        color = ALERTA if e in resaltar else ACENTO
        partes.append(f'<rect x="{LAB}" y="{cy - 9:.1f}" width="{bw:.1f}" height="18" rx="3" fill="{color}"/>')
        txt = fmt(v, sufijo_pct)
        if pct_de_total: txt = f"{fmt(v)} · {100 * v / total:.0f} %"
        partes.append(f'<text x="{LAB + bw + 6:.1f}" y="{cy + 4:.1f}" class="val">{esc(txt)}</text>')
        y += h
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img">{"".join(partes)}</svg>'


def vbar(etiquetas, valores, resaltar=()):
    W, H, PADL, PADB, PADT = 680, 230, 36, 46, 16
    n = len(valores); crudo = max(valores) or 1
    paso = 10 if crudo <= 100 else 20 if crudo <= 200 else 50
    vmax = paso * -(-crudo // paso)   # techo al múltiplo de 'paso'
    ancho = (W - PADL - 10) / n
    partes = []
    for t in (0, 0.5, 1):
        gy = PADT + (H - PADT - PADB) * (1 - t)
        partes.append(f'<line x1="{PADL}" x2="{W - 6}" y1="{gy:.1f}" y2="{gy:.1f}" stroke="{GRILLA}"/>')
        partes.append(f'<text x="{PADL - 6}" y="{gy + 4:.1f}" text-anchor="end" class="ax">{fmt(vmax * t)}</text>')
    for i, (e, v) in enumerate(zip(etiquetas, valores)):
        bh = (H - PADT - PADB) * v / vmax
        x = PADL + i * ancho + ancho * 0.15
        y = H - PADB - bh
        color = ALERTA if e in resaltar else ACENTO
        partes.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{ancho * 0.7:.1f}" height="{max(bh, 1):.1f}" rx="2" fill="{color}"/>')
        partes.append(f'<text x="{x + ancho * 0.35:.1f}" y="{y - 4:.1f}" text-anchor="middle" class="valsm">{fmt(v)}</text>')
        partes.append(f'<text x="{x + ancho * 0.35:.1f}" y="{H - PADB + 16}" text-anchor="middle" class="ax">{esc(e)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img">{"".join(partes)}</svg>'


def linea(etiquetas, valores):
    W, H, PADL, PADB, PADT = 680, 220, 44, 40, 20
    n = len(valores)
    xs = [PADL + 30 + i * (W - PADL - 80) / max(n - 1, 1) for i in range(n)]
    ys = [PADT + (H - PADT - PADB) * (1 - v / 100) for v in valores]
    partes = []
    for t in (50, 75, 100):
        gy = PADT + (H - PADT - PADB) * (1 - t / 100)
        partes.append(f'<line x1="{PADL}" x2="{W - 6}" y1="{gy:.1f}" y2="{gy:.1f}" stroke="{GRILLA}"/><text x="{PADL - 6}" y="{gy + 4:.1f}" text-anchor="end" class="ax">{t} %</text>')
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    partes.append(f'<polyline points="{pts}" fill="none" stroke="{ACENTO}" stroke-width="3"/>')
    for x, y, v, e in zip(xs, ys, valores, etiquetas):
        partes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{ACENTO}"/><text x="{x:.1f}" y="{y - 10:.1f}" text-anchor="middle" class="val">{fmt(v, True)}</text>')
        partes.append(f'<text x="{x:.1f}" y="{H - PADB + 18}" text-anchor="middle" class="ax">{esc(e)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img">{"".join(partes)}</svg>'


LIMPIEZA = [
    ("tabla recordatorios_enviados (enviado_at y confirmado_at)", "registro de recordatorios"),
    ("mensajes_entrantes_live (from_me = false)", "Mensajes recibidos"),
    ("Mensajes entrantes de mensajes_entrantes_live", "Mensajes recibidos"),
    ("mensajes_entrantes_live", "registro de mensajes recibidos"),
    ("de escalaciones_log", "del registro de avisos"),
    ("escalaciones_log", "registro de avisos"),
    ("tests/examen_v7.py:", "Examen automático:"),
    (" (gpt-5-mini)", ""),
]


def limpiar(t):
    for a, b in LIMPIEZA:
        t = t.replace(a, b)
    return t


def grafico(g):
    t, e, v = g["tipo"], g["etiquetas"], g["valores"]
    if g["id"] == "mensajes_por_dia":
        svg = vbar(e, v, resaltar=("06/10", "07/10", "08/10"))
    elif t == "linea":
        svg = linea(e, v)
    elif t == "barras" and g["id"] == "resueltas_sin_persona":
        svg = hbar(e, v, sufijo_pct=True)
    elif t == "torta":
        svg = hbar(e, v, pct_de_total=True)
    else:
        svg = hbar(e, v)
    return (f'<figure class="graf"><figcaption>{esc(g["titulo"])}</figcaption>{svg}'
            f'<p class="fuente">{esc(limpiar(g.get("nota_fuente", "")))}</p></figure>')


def main():
    datos = {g["id"]: g for g in json.loads(DATOS.read_text(encoding="utf-8"))["graficos"]}
    md = MD.read_text(encoding="utf-8")
    titulo = md.splitlines()[0].lstrip("# ").strip()
    cuerpo_md = "\n".join(l for l in md.splitlines()[1:] if not l.startswith("**Informe para la Dra.") and not l.startswith("Preparado por Nexora"))
    cuerpo = markdown.markdown(cuerpo_md, extensions=["tables", "sane_lists"])
    usados = []
    def poner(m):
        gid = m.group(1).strip()
        if gid in datos:
            usados.append(gid); return grafico(datos[gid])
        return f'<p class="fuente">[gráfico no encontrado: {esc(gid)}]</p>'
    cuerpo = re.sub(r"<p>\[GRAFICO:\s*([^\]]+)\]</p>", poner, cuerpo)
    # Cada parte y el anexo empiezan en página nueva
    cuerpo = re.sub(r"<h2>(Parte |Anexo)", r'<h2 class="salto">\1', cuerpo)
    cuerpo = cuerpo.replace("<hr />", "")
    cuerpo = cuerpo.replace("☐", '<span class="box">☐</span>')
    css = f"""
    @page {{ size: A4; margin: 18mm 17mm 18mm 17mm; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: {TEXTO}; font-size: 10.6pt; line-height: 1.5; margin: 0; background: #fff; }}
    .portada {{ height: 255mm; display: flex; flex-direction: column; justify-content: space-between; page-break-after: always; }}
    .portada .marca {{ font-size: 10pt; letter-spacing: .14em; text-transform: uppercase; color: {ACENTO}; font-weight: 600; }}
    .portada h1 {{ font-family: Georgia, "Times New Roman", serif; font-size: 34pt; line-height: 1.12; margin: 60mm 0 6mm; color: {TEXTO}; font-weight: 600; }}
    .portada .sub {{ font-size: 13pt; color: {SUAVE}; max-width: 135mm; }}
    .portada .pie {{ border-top: 2px solid {ACENTO}; padding-top: 5mm; font-size: 10pt; color: {SUAVE}; display: flex; justify-content: space-between; }}
    .borrador {{ display: inline-block; margin-top: 8mm; padding: 2mm 4mm; border: 1px solid {ALERTA}; color: {ALERTA}; border-radius: 3px; font-size: 9.5pt; font-weight: 600; letter-spacing: .04em; }}
    h2 {{ font-family: Georgia, "Times New Roman", serif; font-size: 19pt; color: {ACENTO}; margin: 9mm 0 3mm; font-weight: 600; text-wrap: balance; }}
    h2.salto {{ page-break-before: always; margin-top: 0; padding-top: 2mm; border-bottom: 2px solid {ACENTO}; padding-bottom: 2mm; }}
    h3 {{ font-size: 12.5pt; margin: 7mm 0 2mm; color: {TEXTO}; page-break-after: avoid; }}
    p {{ margin: 0 0 2.6mm; }}
    ul, ol {{ margin: 0 0 3mm; padding-left: 6mm; }}
    li {{ margin: 0 0 1.2mm; }}
    strong {{ color: #0b1a1d; }}
    blockquote {{ margin: 3mm 0 5mm; padding: 3mm 5mm; background: #eef6f5; border-left: 3px solid {ACENTO}; color: {TEXTO}; font-size: 10pt; }}
    blockquote p:last-child {{ margin-bottom: 0; }}
    table {{ width: 100%; border-collapse: collapse; margin: 2mm 0 5mm; font-size: 9.2pt; page-break-inside: auto; }}
    th {{ text-align: left; background: #eef3f3; color: {TEXTO}; font-weight: 600; padding: 2mm 2.2mm; border-bottom: 1.5px solid {ACENTO_2}; }}
    td {{ padding: 1.8mm 2.2mm; border-bottom: 1px solid {GRILLA}; vertical-align: top; }}
    tr {{ page-break-inside: avoid; }}
    code {{ font-family: Consolas, monospace; font-size: 9pt; background: #f1f4f4; padding: 0 1mm; border-radius: 2px; }}
    .box {{ font-size: 11pt; color: {ACENTO}; }}
    figure.graf {{ margin: 4mm 0 6mm; padding: 4mm 4mm 2mm; border: 1px solid {GRILLA}; border-radius: 4px; page-break-inside: avoid; }}
    figure.graf figcaption {{ font-weight: 600; font-size: 10.5pt; margin-bottom: 2mm; color: {TEXTO}; }}
    .fuente {{ font-size: 8pt; color: {SUAVE}; margin: 1.5mm 0 0; line-height: 1.35; }}
    svg text.lab {{ font-size: 11.5px; fill: {TEXTO}; }}
    svg text.val {{ font-size: 11.5px; fill: {TEXTO}; font-weight: 600; }}
    svg text.valsm {{ font-size: 10px; fill: {TEXTO}; }}
    svg text.ax {{ font-size: 10px; fill: {SUAVE}; }}
    em {{ color: {SUAVE}; }}
    """
    ejecutivo = "ejecutivo" in MD.stem
    SUB = "Qué hace hoy por la clínica, dónde puede ayudar más y el próximo paso." if ejecutivo else "Cómo viene la secretaria virtual, qué preguntan los pacientes, qué información necesitamos de la clínica y la propuesta de Asiri nueva."
    BADGE = "" if ejecutivo else '<div class="borrador">BORRADOR PARA REVISIÓN INTERNA — no enviar todavía</div>'
    FECHA = "14/10/2026" if ejecutivo else "13/10/2026"
    portada = f"""<section class="portada">
      <div><div class="marca">Áurea Odontología Estética · Asiri</div>
        <h1>{esc(titulo)}</h1>
        <div class="sub">{SUB}</div>
        {BADGE}</div>
      <div class="pie"><span>Para la Dra. Raquel Rodríguez</span><span>Nexora · {FECHA}</span></div>
    </section>"""
    doc = f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{esc(titulo)}</title><style>{css}</style></head><body>{portada}<main>{cuerpo}</main></body></html>'
    HTML_OUT.write_text(doc, encoding="utf-8")
    faltan = [g for g in datos if g not in usados]
    print("html ok", HTML_OUT, "| gráficos usados", len(usados), "| sin usar", faltan)
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    r = subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={PDF_OUT}", HTML_OUT.as_uri()], capture_output=True, text=True, timeout=180)
    print("edge rc", r.returncode, (r.stderr or "")[-300:])
    print("pdf", PDF_OUT, PDF_OUT.exists() and PDF_OUT.stat().st_size)


if __name__ == "__main__":
    main()
