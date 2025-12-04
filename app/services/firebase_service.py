"""Servicio base para interactuar con Firebase Firestore"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List
from firebase_admin import firestore
from app.backend.firebase_config import db
import json
from datetime import datetime, timezone
from datetime import datetime, timezone
class FirebaseService:
    """Servicio para operaciones CRUD en Firebase con soporte de TTL"""
    
    def __init__(self):
        self.db = db
    
    def _get_collection(self, collection_name: str):
        """Obtiene una referencia a una colección"""
        return self.db.collection(collection_name)
    
    def set_with_ttl(
        self, 
        collection: str, 
        doc_id: str, 
        data: Dict[str, Any], 
        ttl_seconds: int
    ) -> bool:
        """
        Guarda un documento con TTL (Time To Live)
        
        Args:
            collection: Nombre de la colección
            doc_id: ID del documento
            data: Datos a guardar
            ttl_seconds: Tiempo de vida en segundos
        
        Returns:
            True si se guardó exitosamente
        """
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            
            doc_data = {
                "data": data,
                "created_at": datetime.now(timezone.utc),
                "expires_at": expires_at,
                "ttl_seconds": ttl_seconds
            }
            
            self._get_collection(collection).document(doc_id).set(doc_data)
            return True
        except Exception as e:
            print(f"Error guardando en Firebase: {str(e)}")
            return False
    
    def get_if_valid(
        self, 
        collection: str, 
        doc_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene un documento solo si no ha expirado
        
        Args:
            collection: Nombre de la colección
            doc_id: ID del documento
        
        Returns:
            Los datos si están vigentes, None si expiraron o no existen
        """
        try:
            doc_ref = self._get_collection(collection).document(doc_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return None
            
            doc_data = doc.to_dict()
            expires_at = doc_data.get("expires_at")
            
            # Verificar si expiró
            if expires_at and datetime.now(timezone.utc) > expires_at:
                # Eliminar documento expirado
                doc_ref.delete()
                return None
            
            return doc_data.get("data")
        
        except Exception as e:
            print(f"Error obteniendo de Firebase: {str(e)}")
            return None
    
    def delete(self, collection: str, doc_id: str) -> bool:
        """Elimina un documento"""
        try:
            self._get_collection(collection).document(doc_id).delete()
            return True
        except Exception as e:
            print(f"Error eliminando de Firebase: {str(e)}")
            return False
    
    def get_all_valid(self, collection: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los documentos válidos (no expirados) de una colección
        
        Returns:
            Lista de documentos válidos con sus IDs
        """
        try:
            docs = self._get_collection(collection).stream()
            valid_docs = []
            now = datetime.now(timezone.utc)
            
            for doc in docs:
                doc_data = doc.to_dict()
                expires_at = doc_data.get("expires_at")
                
                # Si no ha expirado, agregarlo
                if not expires_at or now <= expires_at:
                    valid_docs.append({
                        "id": doc.id,
                        "data": doc_data.get("data"),
                        "created_at": doc_data.get("created_at"),
                        "expires_at": expires_at
                    })
                else:
                    # Eliminar si expiró
                    self._get_collection(collection).document(doc.id).delete()
            
            return valid_docs
        
        except Exception as e:
            print(f"Error obteniendo todos los documentos: {str(e)}")
            return []
    
    def update_if_exists(
        self, 
        collection: str, 
        doc_id: str, 
        data: Dict[str, Any],
        extend_ttl: bool = True
    ) -> bool:
        """
        Actualiza un documento existente
        
        Args:
            collection: Nombre de la colección
            doc_id: ID del documento
            data: Nuevos datos
            extend_ttl: Si True, renueva el TTL desde ahora
        
        Returns:
            True si se actualizó exitosamente
        """
        try:
            doc_ref = self._get_collection(collection).document(doc_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return False
            
            doc_data = doc.to_dict()
            update_data = {"data": data}
            
            if extend_ttl:
                ttl_seconds = doc_data.get("ttl_seconds", 60)
                update_data["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
                update_data["updated_at"] = datetime.now(timezone.utc)
            
            doc_ref.update(update_data)
            return True
        
        except Exception as e:
            print(f"Error actualizando documento: {str(e)}")
            return False
    
    def cleanup_expired(self, collection: str) -> int:
        """
        Limpia documentos expirados de una colección
        
        Returns:
            Número de documentos eliminados
        """
        try:
            docs = self._get_collection(collection).where(
                "expires_at", "<=", datetime.now(timezone.utc)
            ).stream()
            
            count = 0
            for doc in docs:
                doc.reference.delete()
                count += 1
            
            return count
        
        except Exception as e:
            print(f"Error limpiando documentos expirados: {str(e)}")
            return 0


# Instancia global del servicio
firebase_service = FirebaseService()