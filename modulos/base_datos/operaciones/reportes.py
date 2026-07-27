import os
import io
import pandas as pd
from modulos.base_datos.conexion import obtener_conexion
from modulos.base_datos.operaciones.productos import asegurar_columna_usuario
import io
import sqlite3
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from modulos.base_datos.conexion import obtener_conexion
from modulos.base_datos.operaciones.productos import asegurar_columna_usuario

def generar_excel_resenas(asin: str, usuario_id: str) -> io.BytesIO:
    """
    Consulta todas las reseñas de un ASIN en SQLite, las limpia
    y genera un archivo Excel (.xlsx) en memoria usando un buffer binario.
    """
    asin_limpio = str(asin).strip().upper()
    uid_limpio = str(usuario_id).strip()
    
    conn = obtener_conexion()
    c = conn.cursor()
    asegurar_columna_usuario(c)
    
    # 🔍 Consultamos las reseñas cruzando con la tabla productos para validar propiedad
    c.execute('''
        SELECT r.review_id, r.author, r.title, r.body, r.rating, r.fecha, r.verified
        FROM resenas r
        JOIN productos p ON UPPER(TRIM(r.asin)) = UPPER(TRIM(p.asin))
        WHERE UPPER(TRIM(r.asin)) = ? AND (p.usuario_id = ? OR p.usuario_id = 'usuario_default')
        ORDER BY r.rating DESC
    ''', (asin_limpio, uid_limpio))
    
    filas = c.fetchall()
    conn.close()
    
    if not filas:
        raise ValueError(f"No hay reseñas registradas en la base de datos para el ASIN {asin_limpio}")
        
    # Mapeamos las tuplas a un formato estructurado para Pandas
    datos_limpios = []
    for f in filas:
        datos_limpios.append({
            "ID Reseña": f[0],
            "Autor": f[1],
            "Título": f[2],
            "Comentario": f[3],
            "Calificación (Estrellas)": f[4],
            "Fecha": f[5],
            "Compra Verificada": "Sí" if f[6] == 1 else "No"
        })
        
    # Creamos el DataFrame de Pandas
    df = pd.DataFrame(datos_limpios)
    
    # Escribimos el archivo Excel directamente en memoria usando un buffer binario
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Opiniones Clientes', index=False)
        
        # Estilizado rápido automático de anchos de columna
        workbook = writer.book
        worksheet = workbook.active
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = col[0].column_letter
            worksheet.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 50)
            
    output.seek(0)
    return output


def generar_pdf_resumen_ejecutivo(asin: str, usuario_id: str) -> io.BytesIO:
    """Genera un informe PDF ejecutivo en memoria de forma blindada contra valores None/Nulos."""
    asin_limpio = str(asin).strip().upper()
    uid_limpio = str(usuario_id).strip()

    conn = obtener_conexion()
    c = conn.cursor()
    asegurar_columna_usuario(c)

    # 1. Obtenemos información del producto de forma segura
    nombre_prod = f"Producto ASIN: {asin_limpio}"
    try:
        c.execute(
            """
            SELECT nombre FROM productos 
            WHERE UPPER(TRIM(asin)) = ? AND (usuario_id = ? OR usuario_id = 'usuario_default')
            LIMIT 1
        """,
            (asin_limpio, uid_limpio),
        )
        prod = c.fetchone()
        if prod and prod[0]:
            nombre_prod = prod[0]
    except Exception as e:
        print(f"[WARNING PDF] No se pudo leer el nombre del producto: {e}")

    # 2. Obtenemos métricas generales con salvaguarda de valores nulos
    c.execute(
        """
        SELECT 
            COUNT(r.review_id) as total,
            AVG(r.rating) as promedio,
            SUM(CASE WHEN r.rating >= 4 THEN 1 ELSE 0 END) as pos,
            SUM(CASE WHEN r.rating <= 2 THEN 1 ELSE 0 END) as neg
        FROM resenas r
        JOIN productos p ON UPPER(TRIM(r.asin)) = UPPER(TRIM(p.asin))
        WHERE UPPER(TRIM(r.asin)) = ? AND (p.usuario_id = ? OR p.usuario_id = 'usuario_default')
    """,
        (asin_limpio, uid_limpio),
    )

    stats = c.fetchone()
    total_resenas = stats[0] if (stats and stats[0] is not None) else 0
    promedio_rating = stats[1] if (stats and stats[1] is not None) else 0.0
    pos = stats[2] if (stats and stats[2] is not None) else 0
    neg = stats[3] if (stats and stats[3] is not None) else 0

    if total_resenas == 0:
        conn.close()
        raise ValueError(
            f"No hay suficientes reseñas registradas en la base de datos para generar el PDF del ASIN {asin_limpio}."
        )

    # 3. Extraemos la opinión más crítica
    critica = None
    try:
        c.execute(
            """
            SELECT r.author, r.rating, r.body 
            FROM resenas r
            JOIN productos p ON UPPER(TRIM(r.asin)) = UPPER(TRIM(p.asin))
            WHERE UPPER(TRIM(r.asin)) = ? AND (p.usuario_id = ? OR p.usuario_id = 'usuario_default')
            ORDER BY r.rating ASC, LENGTH(r.body) DESC LIMIT 1
        """,
            (asin_limpio, uid_limpio),
        )
        critica = c.fetchone()
    except Exception as e:
        print(f"[WARNING PDF] No se pudo leer la opinión crítica: {e}")
    finally:
        conn.close()

    # ==========================================
    # CONSTRUCCIÓN DEL DOCUMENTO PDF (REPORTLAB)
    # ==========================================
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    story = []
    styles = getSampleStyleSheet()

    estilo_titulo = ParagraphStyle(
        "TituloDoc",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#1E293B"),
    )
    estilo_sub = ParagraphStyle(
        "SubTituloDoc",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#64748B"),
    )
    estilo_h2 = ParagraphStyle(
        "H2Doc",
        parent=styles["Heading2"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=12,
        spaceAfter=6,
    )
    estilo_texto = ParagraphStyle(
        "TextoBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
    )
    estilo_kpi_val = ParagraphStyle(
        "KpiVal",
        parent=styles["Normal"],
        fontSize=13,
        leading=15,
        alignment=1,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0F172A"),
    )
    estilo_kpi_lbl = ParagraphStyle(
        "KpiLbl",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=1,
        textColor=colors.HexColor("#64748B"),
    )

    # Encabezado
    fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")
    story.append(
        Paragraph(
            "<b>INFORME EJECUTIVO DE ANÁLISIS DE MERCADO</b>", estilo_titulo
        )
    )
    story.append(
        Paragraph(
            f"Generado por Agente RAG | Fecha: {fecha_actual} | ASIN: <b>{asin_limpio}</b>",
            estilo_sub,
        )
    )
    story.append(Spacer(1, 10))
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=colors.HexColor("#6366F1"),
            spaceAfter=15,
        )
    )

    # Ficha del producto
    story.append(
        Paragraph("<b>1. Identificación del Producto</b>", estilo_h2)
    )
    story.append(Paragraph(f"<b>Nombre:</b> {nombre_prod}", estilo_texto))
    story.append(Spacer(1, 10))

    # KPIs
    story.append(Paragraph("<b>2. Radiografía Cuantitativa</b>", estilo_h2))

    kpi_data = [
        [
            Paragraph(f"{promedio_rating:.2f} ★", estilo_kpi_val),
            Paragraph(f"{total_resenas}", estilo_kpi_val),
            Paragraph(f"{pos}", estilo_kpi_val),
            Paragraph(f"{neg}", estilo_kpi_val),
        ],
        [
            Paragraph("Calificación Promedio", estilo_kpi_lbl),
            Paragraph("Total de Opiniones", estilo_kpi_lbl),
            Paragraph("Opiniones Positivas", estilo_kpi_lbl),
            Paragraph("Opiniones Críticas", estilo_kpi_lbl),
        ],
    ]

    t_kpis = Table(kpi_data, colWidths=[130, 130, 130, 130])
    t_kpis.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("PADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ])
    )
    story.append(t_kpis)
    story.append(Spacer(1, 15))

    # Reseña Crítica
    if critica:
        story.append(
            Paragraph("<b>3. Análisis de Caso de Uso Crítico</b>", estilo_h2)
        )
        autor_c = critica[0] or "Anónimo"
        estrellas_c = critica[1] if critica[1] is not None else 0
        texto_c = critica[2] or "Sin texto descriptivo."

        box_critica = [
            [
                Paragraph(
                    f"<b>Autor:</b> {autor_c} ({estrellas_c}★)", estilo_texto
                )
            ],
            [Paragraph(f'<i>"{texto_c}"</i>', estilo_texto)],
        ]
        t_crit = Table(box_critica, colWidths=[520])
        t_crit.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#FCA5A5")),
                ("PADDING", (0, 0), (-1, -1), 10),
            ])
        )
        story.append(t_crit)

    # Pie
    story.append(Spacer(1, 20))
    story.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=colors.HexColor("#CBD5E1"),
            spaceAfter=10,
        )
    )
    story.append(
        Paragraph(
            "Este informe ha sido procesado automáticamente aislando los datos de la cuenta en sesión.",
            estilo_sub,
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer