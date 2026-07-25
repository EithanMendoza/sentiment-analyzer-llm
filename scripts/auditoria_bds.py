import sqlite3
import chromadb
import os

print("\n" + "="*50)
print("🔍 AUDITORÍA DE BASE DE DATOS RELACIONAL (SQLITE)")
print("="*50)

ruta_sqlite = os.path.join("datos", "base_relacional", "historial_sesiones.db")
try:
    conn = sqlite3.connect(ruta_sqlite)
    c = conn.cursor()
    
    # 1. Ver Productos
    c.execute("SELECT asin, nombre FROM productos")
    productos = c.fetchall()
    print(f"\n📦 PRODUCTOS ENCONTRADOS ({len(productos)}):")
    for p in productos:
        print(f"   - ASIN: {p[0]} | Nombre: {p[1][:40]}...")
        
    # 2. Ver Reseñas
    c.execute("SELECT asin, COUNT(*) FROM resenas GROUP BY asin")
    conteo_resenas = c.fetchall()
    print(f"\n💬 RESEÑAS RESPALDADAS:")
    for r in conteo_resenas:
        print(f"   - ASIN: {r[0]} tiene {r[1]} reseñas crudas guardadas.")
        
    # 3. Ver una muestra de reseña
    if productos:
        c.execute("SELECT author, rating, body FROM resenas LIMIT 1")
        muestra = c.fetchone()
        if muestra:
            print(f"\n📝 MUESTRA DE RESEÑA SQLITE:\n   Autor: {muestra[0]}\n   Estrellas: {muestra[1]}\n   Texto: {muestra[2][:100]}...")
            
    conn.close()
except Exception as e:
    print(f"Error leyendo SQLite: {e}")


print("\n" + "="*50)
print("🧠 AUDITORÍA DE BASE DE DATOS VECTORIAL (CHROMADB)")
print("="*50)

ruta_chroma = os.path.join("datos", "base_vectorial")
try:
    # Nos conectamos directo al motor de Chroma
    cliente_chroma = chromadb.PersistentClient(path=ruta_chroma)
    colecciones = cliente_chroma.list_collections()
    
    if not colecciones:
        print("⚠️ No hay colecciones vectoriales. ChromaDB está vacío.")
    else:
        for col_info in colecciones:
            print(f"\n📂 COLECCIÓN ENCONTRADA: '{col_info.name}'")
            # Extraemos la colección
            coleccion = cliente_chroma.get_collection(col_info.name)
            total_vectores = coleccion.count()
            print(f"   - Total de vectores (fragmentos): {total_vectores}")
            
            if total_vectores > 0:
                # Sacamos 1 vector al azar para ver sus metadatos
                muestra_vector = coleccion.peek(limit=1)
                print("\n🔬 MUESTRA DEL VECTOR EN CHROMADB:")
                print(f"   - ID del Vector: {muestra_vector['ids'][0]}")
                print(f"   - Metadatos ocultos (¡Aquí debe estar el ASIN!): {muestra_vector['metadatas'][0]}")
                print(f"   - Texto asimilado por la IA: {muestra_vector['documents'][0][:150]}...")
                
except Exception as e:
    print(f"Error leyendo ChromaDB: {e}")

print("\n" + "="*50 + "\n")