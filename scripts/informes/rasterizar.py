import sys, fitz
pdf, salida, paginas = sys.argv[1], sys.argv[2], sys.argv[3:]
d = fitz.open(pdf)
print("páginas:", d.page_count)
for p in (paginas or range(1, d.page_count + 1)):
    i = int(p) - 1
    d[i].get_pixmap(dpi=int(70)).save(f"{salida}_{i + 1}.png")
