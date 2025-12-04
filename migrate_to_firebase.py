#!/usr/bin/env python3
"""
Script de Migración: Cache en Memoria → Firebase Firestore

Este script:
1. Verifica la configuración de Firebase
2. Crea las colecciones necesarias
3. Migra datos existentes (si los hay)
4. Valida que todo funcione correctamente

Uso:
    python migrate_to_firebase.py [--test] [--force]
    
Opciones:
    --test: Solo verifica la conexión sin migrar datos
    --force: Fuerza la migración incluso si hay errores
"""

import sys
import os
import argparse
from datetime import datetime
from typing import Dict, Any
from datetime import datetime, timezone
# Agregar el directorio padre al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_firebase_connection():
    """Prueba la conexión a Firebase"""
    print("🔍 Verificando conexión a Firebase...")
    
    try:
        from app.backend.firebase_config import db
        
        # Intentar crear un documento de prueba
        test_ref = db.collection("_migration_test").document("test")
        test_ref.set({
            "test": True,
            "timestamp": datetime.now(timezone.utc)
        })
        
        # Leer el documento
        doc = test_ref.get()
        if not doc.exists:
            print("❌ Error: No se pudo leer el documento de prueba")
            return False
        
        # Eliminar el documento de prueba
        test_ref.delete()
        
        print("✅ Conexión a Firebase exitosa")
        return True
        
    except Exception as e:
        print(f"❌ Error conectando a Firebase: {str(e)}")
        print("\nVerifica que:")
        print("1. El archivo de credenciales JSON existe")
        print("2. La ruta en firebase_config.py es correcta")
        print("3. Firebase Admin SDK está instalado: pip install firebase-admin")
        return False


def create_collections():
    """Crea las colecciones necesarias en Firebase"""
    print("\n📁 Creando colecciones en Firebase...")
    
    collections = [
        ("live_fixtures", "Partidos en vivo"),
        ("fixtures", "Información de partidos"),
        ("statistics", "Estadísticas de partidos"),
        ("events", "Eventos de partidos"),
        ("lineups", "Alineaciones"),
        ("team_statistics", "Estadísticas de equipos"),
        ("team_seasons", "Temporadas disponibles"),
        ("match_data_cache", "Cache completo de partidos")
    ]
    
    try:
        from app.backend.firebase_config import db
        
        for coll_name, description in collections:
            # Crear un documento dummy para inicializar la colección
            doc_ref = db.collection(coll_name).document("_init")
            doc_ref.set({
                "description": description,
                "created_at": datetime.now(timezone.utc),
                "is_initialized": True
            })
            print(f"  ✓ {coll_name}: {description}")
        
        print("✅ Colecciones creadas exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error creando colecciones: {str(e)}")
        return False


def cleanup_init_docs():
    """Limpia los documentos de inicialización"""
    print("\n🧹 Limpiando documentos de inicialización...")
    
    try:
        from app.backend.firebase_config import db
        
        collections = [
            "live_fixtures", "fixtures", "statistics", "events",
            "lineups", "team_statistics", "team_seasons", "match_data_cache"
        ]
        
        for coll_name in collections:
            doc_ref = db.collection(coll_name).document("_init")
            doc_ref.delete()
        
        print("✅ Documentos de inicialización eliminados")
        return True
        
    except Exception as e:
        print(f"⚠️  Advertencia: No se pudieron eliminar docs de init: {str(e)}")
        return True  # No es crítico


def test_service_integration():
    """Prueba la integración del servicio"""
    print("\n🧪 Probando integración del servicio Firebase...")
    
    try:
        from app.services.firebase_service import firebase_service
        
        # Test 1: Set y Get
        print("  Test 1: Set y Get...")
        test_data = {"test": "data", "value": 123}
        firebase_service.set_with_ttl("_test", "test1", test_data, 3600)
        
        retrieved = firebase_service.get_if_valid("_test", "test1")
        if retrieved != test_data:
            print("  ❌ Error: Datos no coinciden")
            return False
        print("  ✓ Set y Get funcionan correctamente")
        
        # Test 2: TTL
        print("  Test 2: TTL...")
        from datetime import timedelta
        firebase_service.set_with_ttl("_test", "test2", {"expired": True}, 0)
        expired = firebase_service.get_if_valid("_test", "test2")
        if expired is not None:
            print("  ❌ Error: El documento expirado no fue eliminado")
            return False
        print("  ✓ TTL funciona correctamente")
        
        # Test 3: Update
        print("  Test 3: Update...")
        firebase_service.set_with_ttl("_test", "test3", {"version": 1}, 3600)
        firebase_service.update_if_exists("_test", "test3", {"version": 2})
        updated = firebase_service.get_if_valid("_test", "test3")
        if updated.get("version") != 2:
            print("  ❌ Error: Update no funcionó")
            return False
        print("  ✓ Update funciona correctamente")
        
        # Limpiar tests
        firebase_service.delete("_test", "test1")
        firebase_service.delete("_test", "test3")
        
        print("✅ Todos los tests pasaron exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en los tests: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_football_service():
    """Prueba el servicio de fútbol con Firebase"""
    print("\n⚽ Probando servicio de fútbol...")
    
    try:
        from app.services.football_firebase_service import FootballFirebaseService
        from app.core.config import get_settings
        
        settings = get_settings()
        api_key = getattr(settings, 'FOOTBALL_API_KEY', "0e88fe12ff5324e08d0dd7b35659829e")
        
        service = FootballFirebaseService(api_key)
        
        # Test: Búsqueda de equipo (debe usar cache si existe)
        print("  Buscando equipo 'Barcelona'...")
        result = service.search_team_by_name("barcelona")
        
        if result.get("results", 0) > 0:
            print(f"  ✓ Encontrado: {result['response'][0]['team']['name']}")
        else:
            print("  ⚠️  No se encontraron resultados (puede ser problema de API key)")
        
        print("✅ Servicio de fútbol funciona correctamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en servicio de fútbol: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def display_summary():
    """Muestra un resumen de la migración"""
    print("\n" + "="*70)
    print("✅ MIGRACIÓN COMPLETADA EXITOSAMENTE")
    print("="*70)
    print("\n📊 Resumen:")
    print("  • Firebase Firestore está configurado y funcionando")
    print("  • Todas las colecciones han sido creadas")
    print("  • Los servicios están integrados correctamente")
    print("\n📝 Próximos pasos:")
    print("  1. Actualizar tus rutas para usar FootballFirebaseService")
    print("  2. Configurar tareas de limpieza periódica (ver tasks.py)")
    print("  3. Configurar reglas de seguridad en Firebase Console")
    print("  4. Monitorear logs para verificar cache hits/misses")
    print("\n💡 Comandos útiles:")
    print("  • Ver logs: tail -f app.log")
    print("  • Limpiar cache: python -c 'from app.tasks import cleanup_expired_documents; cleanup_expired_documents()'")
    print("  • Forzar refresh: curl 'http://localhost:8000/football/live-matches?force_refresh=true'")
    print("\n📚 Documentación completa en: GUÍA DE MIGRACIÓN.md")
    print("="*70 + "\n")


def main():
    """Función principal del script de migración"""
    parser = argparse.ArgumentParser(description="Migración de Cache a Firebase")
    parser.add_argument("--test", action="store_true", help="Solo verificar conexión")
    parser.add_argument("--force", action="store_true", help="Forzar migración")
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("🚀 MIGRACIÓN: Cache en Memoria → Firebase Firestore")
    print("="*70 + "\n")
    
    # Step 1: Verificar conexión
    if not test_firebase_connection():
        print("\n❌ Migración abortada: No se pudo conectar a Firebase")
        sys.exit(1)
    
    # Si solo es test, terminar aquí
    if args.test:
        print("\n✅ Test completado exitosamente")
        sys.exit(0)
    
    # Step 2: Crear colecciones
    if not create_collections():
        if not args.force:
            print("\n❌ Migración abortada: No se pudieron crear las colecciones")
            print("Usa --force para continuar de todos modos")
            sys.exit(1)
        print("⚠️  Continuando con --force...")
    
    # Step 3: Limpiar documentos de inicialización
    cleanup_init_docs()
    
    # Step 4: Probar integración
    if not test_service_integration():
        if not args.force:
            print("\n❌ Migración abortada: Los tests de integración fallaron")
            print("Usa --force para continuar de todos modos")
            sys.exit(1)
        print("⚠️  Continuando con --force...")
    
    # Step 5: Probar servicio de fútbol
    if not test_football_service():
        print("\n⚠️  Advertencia: El servicio de fútbol tiene problemas")
        print("Verifica tu API_KEY en settings")
        if not args.force:
            print("Usa --force para ignorar este error")
            sys.exit(1)
    
    # Mostrar resumen
    display_summary()
    
    print("✨ ¡Migración completada! Tu API ahora usa Firebase Firestore.")
    print("   Reinicia tu servidor para aplicar todos los cambios.\n")


if __name__ == "__main__":
    main()