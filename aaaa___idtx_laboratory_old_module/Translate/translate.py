import polib
from deep_translator import GoogleTranslator
import math
import re

# -----------------------------
# Utilidades
# -----------------------------
def dividir_texto_en_lineas(texto, lineas_originales):
    texto = texto.strip()
    num_lineas = len(lineas_originales)
    if num_lineas == 1:
        return [texto]

    largo_total = len(texto)
    partes, inicio = [], 0
    for i in range(num_lineas - 1):
        proporcion = len(lineas_originales[i]) / sum(len(l) for l in lineas_originales)
        fin = inicio + math.floor(proporcion * largo_total)
        partes.append(texto[inicio:fin].strip())
        inicio = fin
    partes.append(texto[inicio:].strip())
    return partes

def ajustar_mayusculas(original, traducido):
    if not original or not traducido:
        return traducido
    if original.isupper():
        return traducido.upper()
    if original[0].isupper():
        return traducido[0].upper() + traducido[1:]
    return traducido

# -----------------------------
# Traducción protegida
# -----------------------------
def traducir_segmentado(texto, traductor):
    """
    Traduce solo fragmentos de texto real,
    dejando intactos los placeholders y etiquetas HTML.
    """
    patron = re.compile(
        r"%\([a-zA-Z0-9_]+\)s"      # %(name)s
        r"|%s"                      # %s
        r"|\{[a-zA-Z0-9_]+\}"       # {variable}
        r"|[a-zA-Z_]+\.[a-zA-Z_]+"  # object.name, field.model
        r"|</?[^>]+?>"              # etiquetas HTML
    )

    partes = []
    ultimo = 0
    for m in patron.finditer(texto):
        if m.start() > ultimo:
            partes.append(("texto", texto[ultimo:m.start()]))
        partes.append(("no_trad", m.group(0)))
        ultimo = m.end()

    if ultimo < len(texto):
        partes.append(("texto", texto[ultimo:]))

    traducido = []
    for tipo, frag in partes:
        if tipo == "texto" and frag.strip():
            try:
                frag_trad = traductor.translate(frag)
                if frag_trad is None:
                    frag_trad = frag
                traducido.append(frag_trad)
            except Exception:
                traducido.append(frag)
        else:
            traducido.append(frag)  # mantener etiqueta/placeholder intacto

    return "".join(traducido)

# -----------------------------
# Traducción del archivo PO
# -----------------------------
def traducir_po(archivo_entrada, archivo_salida, destino="es-PE"):
    po = polib.pofile(archivo_entrada)
    traductor = GoogleTranslator(source="en", target=destino)

    total = len(po)
    for idx, entrada in enumerate(po, start=1):
        if entrada.msgid.strip() and not entrada.msgstr.strip():
            try:
                lineas_originales = entrada.msgid.split("\n")
                texto_original = " ".join(lineas_originales).strip()

                # Si es SOLO placeholders → copiar tal cual
                if re.fullmatch(
                    r"(?:\s*(?:%\([a-zA-Z0-9_]+\)s|%s|\{[a-zA-Z0-9_]+\}|[a-zA-Z_]+\.[a-zA-Z_]+|</?[^>]+?>)\s*)+",
                    texto_original
                ):
                    entrada.msgstr = texto_original
                else:
                    traduccion = traducir_segmentado(texto_original, traductor)
                    traduccion = ajustar_mayusculas(lineas_originales[0], traduccion)

                    if len(lineas_originales) > 1:
                        lineas_traducidas = dividir_texto_en_lineas(traduccion, lineas_originales)
                        entrada.msgstr = "\n".join(lineas_traducidas)
                    else:
                        entrada.msgstr = traduccion

            except Exception as e:
                print(f"⚠️ Error al traducir '{entrada.msgid}': {e}")
                entrada.msgstr = entrada.msgid  # fallback: copiar original

        porcentaje = (idx / total) * 100
        print(f"\rTraduciendo: {porcentaje:.2f}% ({idx}/{total})", end="")

    po.save(archivo_salida)
    print(f"\n✅ Archivo traducido guardado en: {archivo_salida}")


if __name__ == "__main__":
    archivo_entrada = "/home/jpc/odoo/odoo18/extra-addons/idetex/idtx_laboratory/i18n/es_PE.po"
    archivo_salida = "/home/jpc/odoo/odoo18/extra-addons/idetex/idtx_laboratory/i18n/es_PE_translated.po"
    traducir_po(archivo_entrada, archivo_salida, destino="es")
