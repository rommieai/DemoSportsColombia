"""
Script de prueba para los nuevos endpoints de análisis
Demuestra procesamiento paralelo y sistema de caché
"""
import requests
import time
from pathlib import Path
import json


BASE_URL = "http://localhost:8000"


def print_separator(title=""):
    """Imprime un separador visual"""
    print("\n" + "="*60)
    if title:
        print(f"  {title}")
        print("="*60)
    print()


def test_health():
    """Verifica el estado del servidor"""
    print_separator("1. HEALTH CHECK")
    
    response = requests.get(f"{BASE_URL}/health")
    
    if response.status_code == 200:
        data = response.json()
        print("✅ Servidor funcionando")
        print(f"\n📊 Estado de Modelos:")
        for model, status in data["models"].items():
            icon = "✅" if status else "❌"
            print(f"  {icon} {model}: {status}")
        
        print(f"\n💾 Caché:")
        cache = data.get("cache", {})
        print(f"  - Tamaño: {cache.get('size', 0)}/{cache.get('max_size', 50)}")
        print(f"  - Uso: {cache.get('usage_percent', 0):.1f}%")
        
        return True
    else:
        print("❌ Servidor no disponible")
        return False


def test_analyze_complete(image_path: str):
    """Prueba el endpoint de análisis completo"""
    print_separator("2. ANÁLISIS COMPLETO (Procesamiento Paralelo)")
    
    if not Path(image_path).exists():
        print(f"❌ Imagen no encontrada: {image_path}")
        return None
    
    print(f"📸 Procesando: {image_path}")
    
    start_time = time.time()
    
    with open(image_path, "rb") as f:
        files = {"file": f}
        response = requests.post(
            f"{BASE_URL}/analyze-complete",
            files=files
        )
    
    elapsed = time.time() - start_time
    
    if response.status_code == 200:
        data = response.json()
        
        print(f"\n✅ Análisis completado en {elapsed:.3f}s")
        print(f"\n📊 Resultados:")
        print(f"  - Tiempo del partido: {data.get('match_time', 'No detectado')}")
        print(f"  - Caras detectadas: {data['num_faces']}")
        print(f"  - Camisetas ARG: {data['argentina_count']}")
        print(f"  - Camisetas FRA: {data['france_count']}")
        print(f"  - Total detecciones: {data['total_detections']}")
        
        times = data.get('processing_times', {})
        print(f"\n⏱️  Tiempos de Procesamiento:")
        print(f"  - Caras:      {times.get('faces', 0):.3f}s")
        print(f"  - Camisetas:  {times.get('jerseys', 0):.3f}s")
        print(f"  - Tiempo OCR: {times.get('time_ocr', 0):.3f}s")
        print(f"  - TOTAL:      {times.get('total', 0):.3f}s")
        
        return data
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None


def test_analyze_time(image_path: str):
    """Prueba el endpoint de análisis con caché"""
    print_separator("3. ANÁLISIS CON CACHÉ")
    
    if not Path(image_path).exists():
        print(f"❌ Imagen no encontrada: {image_path}")
        return None
    
    print(f"📸 Procesando: {image_path}")
    
    start_time = time.time()
    
    with open(image_path, "rb") as f:
        files = {"file": f}
        response = requests.post(
            f"{BASE_URL}/analyze-time",
            files=files
        )
    
    elapsed = time.time() - start_time
    
    if response.status_code == 200:
        data = response.json()
        source = data.get('source', 'unknown')
        
        if source == "cache":
            print(f"\n✅ ¡HIT DE CACHÉ! Resultado en {elapsed:.3f}s (instantáneo)")
            print(f"   💾 Datos recuperados de caché")
        else:
            print(f"\n✅ Análisis nuevo completado en {elapsed:.3f}s")
            print(f"   🔄 Datos guardados en caché")
        
        print(f"\n📊 Resultados:")
        print(f"  - Fuente: {source}")
        print(f"  - Tiempo del partido: {data['match_time']}")
        print(f"  - Caras: {data['num_faces']}")
        print(f"  - Camisetas ARG: {data['argentina_count']}")
        print(f"  - Camisetas FRA: {data['france_count']}")
        
        if data.get('processing_times'):
            print(f"\n⏱️  Tiempos: {data['processing_times']}")
        
        return data
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None


def test_cache_stats():
    """Obtiene estadísticas del caché"""
    print_separator("4. ESTADÍSTICAS DEL CACHÉ")
    
    response = requests.get(f"{BASE_URL}/cache/stats")
    
    if response.status_code == 200:
        data = response.json()
        
        print("📊 Estado del Caché:")
        print(f"  - Elementos: {data['size']}/{data['max_size']}")
        print(f"  - Uso: {data['usage_percent']:.1f}%")
        
        if data['times_cached']:
            print(f"\n⏰ Tiempos Almacenados:")
            for i, t in enumerate(data['times_cached'][:10], 1):
                print(f"  {i}. {t}")
            
            if len(data['times_cached']) > 10:
                print(f"  ... y {len(data['times_cached']) - 10} más")
        
        print(f"\n📌 Más viejo: {data['oldest_time']}")
        print(f"📌 Más nuevo: {data['newest_time']}")
        
        return data
    else:
        print(f"❌ Error: {response.status_code}")
        return None


def test_cache_hit_demo(image_path: str):
    """Demuestra el beneficio del caché procesando la misma imagen 2 veces"""
    print_separator("5. DEMOSTRACIÓN DE CACHÉ")
    
    print("🎯 Procesando la misma imagen 2 veces para demostrar el caché\n")
    
    # Primera vez
    print("📍 Intento 1 (nueva imagen):")
    time1 = time.time()
    result1 = test_analyze_time(image_path)
    elapsed1 = time.time() - time1
    
    if not result1:
        return
    
    time.sleep(1)
    
    # Segunda vez (debería ser instantánea si tiene el mismo tiempo)
    print("\n📍 Intento 2 (misma imagen):")
    time2 = time.time()
    result2 = test_analyze_time(image_path)
    elapsed2 = time.time() - time2
    
    if not result2:
        return
    
    # Comparación
    print_separator("COMPARACIÓN")
    print(f"Intento 1: {elapsed1:.3f}s ({result1['source']})")
    print(f"Intento 2: {elapsed2:.3f}s ({result2['source']})")
    
    if result2['source'] == 'cache':
        speedup = elapsed1 / elapsed2
        print(f"\n🚀 Aceleración: {speedup:.1f}x más rápido con caché!")
    else:
        print("\n⚠️  Ambos fueron análisis nuevos (tiempos diferentes)")


def clear_cache():
    """Limpia el caché"""
    print_separator("6. LIMPIAR CACHÉ")
    
    response = requests.post(f"{BASE_URL}/cache/clear")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ {data['message']}")
        print(f"   Elementos eliminados: {data['elements_removed']}")
    else:
        print(f"❌ Error: {response.status_code}")


def main():
    """Ejecuta todos los tests"""
    print("\n" + "🎬" * 30)
    print("  SCRIPT DE PRUEBA - Sistema de Análisis v2.0")
    print("🎬" * 30)
    
    # 1. Health check
    if not test_health():
        print("\n❌ Servidor no disponible. Asegúrate de que esté corriendo.")
        return
    
    # Solicitar ruta de imagen
    print("\n📂 Por favor, proporciona una imagen de prueba:")
    image_path = input("   Ruta de la imagen: ").strip()
    
    if not image_path:
        print("\n⚠️  No se proporcionó imagen. Usando ruta por defecto...")
        image_path = "test_image.jpg"
    
    # 2. Análisis completo
    result = test_analyze_complete(image_path)
    
    if not result:
        print("\n❌ No se pudo completar el análisis.")
        return
    
    # 3. Estadísticas de caché
    test_cache_stats()
    
    # 4. Demo de caché (procesar 2 veces)
    test_cache_hit_demo(image_path)
    
    # 5. Estadísticas finales
    test_cache_stats()
    
    # 6. Opción de limpiar caché
    print("\n")
    respuesta = input("¿Deseas limpiar el caché? (s/n): ").strip().lower()
    if respuesta == 's':
        clear_cache()
        test_cache_stats()
    
    print("\n✅ Pruebas completadas!")
    print("\n💡 Tips:")
    print("  - Usa /analyze-complete para análisis único")
    print("  - Usa /analyze-time para streams/videos (aprovecha caché)")
    print("  - Revisa /cache/stats para monitorear uso")
    print("\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrumpido por el usuario")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
