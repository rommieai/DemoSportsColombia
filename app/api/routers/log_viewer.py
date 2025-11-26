"""
Endpoints para visualizar y consultar logs guardados
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from datetime import datetime, timedelta
import sqlite3
import json
from pathlib import Path

router = APIRouter(prefix="/logs", tags=["API Logs"])


def get_db_connection(db_path: str = "logs/api_responses.db"):
    """Helper para conexión a SQLite"""
    return sqlite3.connect(db_path)


@router.get("/stats")
async def get_logs_statistics(
    days: int = Query(7, ge=1, le=90, description="Días hacia atrás")
):
    """
    Estadísticas generales de logs.
    
    - Total de requests por endpoint
    - Promedio de tiempo de respuesta
    - Códigos de estado más frecuentes
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    since_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    # Total requests por ruta
    cursor.execute("""
        SELECT path, COUNT(*) as total, 
               AVG(duration_ms) as avg_duration,
               MIN(duration_ms) as min_duration,
               MAX(duration_ms) as max_duration
        FROM api_logs 
        WHERE timestamp >= ?
        GROUP BY path
        ORDER BY total DESC
    """, (since_date,))
    
    routes_stats = []
    for row in cursor.fetchall():
        routes_stats.append({
            "path": row[0],
            "total_requests": row[1],
            "avg_duration_ms": round(row[2], 2),
            "min_duration_ms": round(row[3], 2),
            "max_duration_ms": round(row[4], 2)
        })
    
    # Status codes distribution
    cursor.execute("""
        SELECT status_code, COUNT(*) as count
        FROM api_logs
        WHERE timestamp >= ?
        GROUP BY status_code
        ORDER BY count DESC
    """, (since_date,))
    
    status_codes = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Total general
    cursor.execute("""
        SELECT COUNT(*) as total,
               AVG(duration_ms) as avg_duration,
               SUM(response_size) as total_size
        FROM api_logs
        WHERE timestamp >= ?
    """, (since_date,))
    
    total_row = cursor.fetchone()
    
    conn.close()
    
    return {
        "period_days": days,
        "total_requests": total_row[0],
        "avg_duration_ms": round(total_row[1], 2) if total_row[1] else 0,
        "total_data_transferred_mb": round(total_row[2] / (1024*1024), 2) if total_row[2] else 0,
        "routes_stats": routes_stats,
        "status_codes": status_codes
    }


@router.get("/recent")
async def get_recent_logs(
    limit: int = Query(50, ge=1, le=500, description="Cantidad de logs"),
    path_filter: Optional[str] = Query(None, description="Filtrar por ruta"),
    status_code: Optional[int] = Query(None, description="Filtrar por código de estado")
):
    """
    Obtiene los logs más recientes.
    
    - **limit**: Cantidad máxima de resultados (default: 50)
    - **path_filter**: Filtrar por ruta específica
    - **status_code**: Filtrar por código HTTP
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT id, timestamp, method, path, query_params, 
               status_code, response_size, duration_ms, client_ip
        FROM api_logs
        WHERE 1=1
    """
    params = []
    
    if path_filter:
        query += " AND path LIKE ?"
        params.append(f"%{path_filter}%")
    
    if status_code:
        query += " AND status_code = ?"
        params.append(status_code)
    
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    
    logs = []
    for row in cursor.fetchall():
        logs.append({
            "id": row[0],
            "timestamp": row[1],
            "method": row[2],
            "path": row[3],
            "query_params": json.loads(row[4]) if row[4] else {},
            "status_code": row[5],
            "response_size_bytes": row[6],
            "duration_ms": round(row[7], 2),
            "client_ip": row[8]
        })
    
    conn.close()
    
    return {
        "total": len(logs),
        "logs": logs
    }


@router.get("/detail/{log_id}")
async def get_log_detail(log_id: int):
    """
    Obtiene el detalle completo de un log específico.
    
    - **log_id**: ID del log
    - **Incluye**: Response body completo
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT timestamp, method, path, query_params, 
               status_code, response_body, response_size, 
               duration_ms, client_ip, user_agent, created_at
        FROM api_logs
        WHERE id = ?
    """, (log_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(404, f"Log {log_id} no encontrado")
    
    # ✅ Mejorar parseo del response body
    response_body_raw = row[5] or ""
    
    # Intentar parsear response body como JSON
    try:
        response_data = json.loads(response_body_raw)
    except:
        # Si no es JSON válido, retornar como string
        response_data = response_body_raw
    
    # ✅ Validar si el body está vacío o es placeholder
    if response_body_raw in ["<empty_response>", "<decode_error>", ""]:
        response_data = {
            "warning": "Response body no capturado correctamente",
            "raw": response_body_raw
        }
    
    return {
        "id": log_id,
        "timestamp": row[0],
        "method": row[1],
        "path": row[2],
        "query_params": json.loads(row[3]) if row[3] else {},
        "status_code": row[4],
        "response_body": response_data,
        "response_body_length": len(response_body_raw),
        "response_size_bytes": row[6],
        "duration_ms": round(row[7], 2),
        "client_ip": row[8],
        "user_agent": row[9],
        "created_at": row[10]
    }


@router.get("/search")
async def search_logs(
    path: Optional[str] = Query(None, description="Buscar en path"),
    method: Optional[str] = Query(None, description="GET, POST, etc."),
    status_code: Optional[int] = Query(None, description="Código HTTP"),
    min_duration: Optional[float] = Query(None, description="Duración mínima (ms)"),
    from_date: Optional[str] = Query(None, description="Desde fecha (ISO)"),
    to_date: Optional[str] = Query(None, description="Hasta fecha (ISO)"),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Búsqueda avanzada de logs.
    
    - Todos los filtros son opcionales
    - Se combinan con AND
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM api_logs WHERE 1=1"
    params = []
    
    if path:
        query += " AND path LIKE ?"
        params.append(f"%{path}%")
    
    if method:
        query += " AND method = ?"
        params.append(method.upper())
    
    if status_code:
        query += " AND status_code = ?"
        params.append(status_code)
    
    if min_duration:
        query += " AND duration_ms >= ?"
        params.append(min_duration)
    
    if from_date:
        query += " AND timestamp >= ?"
        params.append(from_date)
    
    if to_date:
        query += " AND timestamp <= ?"
        params.append(to_date)
    
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    
    columns = [desc[0] for desc in cursor.description]
    results = []
    
    for row in cursor.fetchall():
        log_dict = dict(zip(columns, row))
        # Parsear campos JSON
        if log_dict.get("query_params"):
            log_dict["query_params"] = json.loads(log_dict["query_params"])
        results.append(log_dict)
    
    conn.close()
    
    return {
        "total": len(results),
        "filters_applied": {
            "path": path,
            "method": method,
            "status_code": status_code,
            "min_duration": min_duration,
            "from_date": from_date,
            "to_date": to_date
        },
        "results": results
    }


@router.get("/endpoint-history")
async def get_endpoint_history(
    path: str = Query(..., description="Ruta del endpoint"),
    days: int = Query(7, ge=1, le=30)
):
    """
    Historial de un endpoint específico.
    
    - Útil para debugging
    - Muestra evolución de tiempos de respuesta
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    since_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    cursor.execute("""
        SELECT timestamp, status_code, duration_ms, response_size
        FROM api_logs
        WHERE path = ? AND timestamp >= ?
        ORDER BY timestamp DESC
    """, (path, since_date))
    
    history = []
    for row in cursor.fetchall():
        history.append({
            "timestamp": row[0],
            "status_code": row[1],
            "duration_ms": round(row[2], 2),
            "response_size_bytes": row[3]
        })
    
    conn.close()
    
    if not history:
        raise HTTPException(404, f"No hay historial para {path} en los últimos {days} días")
    
    # Calcular métricas
    durations = [h["duration_ms"] for h in history]
    
    return {
        "endpoint": path,
        "period_days": days,
        "total_calls": len(history),
        "metrics": {
            "avg_duration_ms": round(sum(durations) / len(durations), 2),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations)
        },
        "history": history
    }


@router.delete("/cleanup")
async def cleanup_old_logs(
    days: int = Query(30, ge=7, description="Borrar logs más antiguos que N días")
):
    """
    Limpia logs antiguos.
    
    - **days**: Mantiene solo logs de los últimos N días
    - **Mínimo**: 7 días
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    # Contar cuántos se borrarán
    cursor.execute("SELECT COUNT(*) FROM api_logs WHERE timestamp < ?", (cutoff_date,))
    count_to_delete = cursor.fetchone()[0]
    
    # Borrar
    cursor.execute("DELETE FROM api_logs WHERE timestamp < ?", (cutoff_date,))
    
    conn.commit()
    conn.close()
    
    return {
        "deleted": count_to_delete,
        "kept_days": days,
        "cutoff_date": cutoff_date
    }


@router.get("/export")
async def export_logs(
    from_date: Optional[str] = Query(None, description="Desde (ISO)"),
    to_date: Optional[str] = Query(None, description="Hasta (ISO)"),
    format: str = Query("json", regex="^(json|csv)$")
):
    """
    Exporta logs en JSON o CSV.
    
    - **from_date**: Fecha inicio
    - **to_date**: Fecha fin
    - **format**: json o csv
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM api_logs WHERE 1=1"
    params = []
    
    if from_date:
        query += " AND timestamp >= ?"
        params.append(from_date)
    
    if to_date:
        query += " AND timestamp <= ?"
        params.append(to_date)
    
    query += " ORDER BY timestamp DESC"
    
    cursor.execute(query, params)
    
    columns = [desc[0] for desc in cursor.description]
    results = []
    
    for row in cursor.fetchall():
        results.append(dict(zip(columns, row)))
    
    conn.close()
    
    if format == "json":
        return {
            "total": len(results),
            "logs": results
        }
    else:
        # CSV simple
        import io
        import csv
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(results)
        
        return {
            "total": len(results),
            "csv": output.getvalue()
        }


@router.get("/debug/check-bodies")
async def debug_check_response_bodies():
    """
    🔍 DEBUG: Verifica si los response bodies se están guardando.
    
    Retorna stats sobre el contenido de los logs.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Últimos 10 logs
    cursor.execute("""
        SELECT id, path, status_code, 
               LENGTH(response_body) as body_length,
               CASE 
                   WHEN response_body LIKE '<empty%' THEN 'empty'
                   WHEN response_body LIKE '<decode%' THEN 'decode_error'
                   WHEN LENGTH(response_body) = 0 THEN 'null'
                   WHEN LENGTH(response_body) < 50 THEN 'too_short'
                   ELSE 'ok'
               END as body_status,
               SUBSTR(response_body, 1, 100) as preview
        FROM api_logs 
        ORDER BY id DESC 
        LIMIT 20
    """)
    
    logs = []
    stats = {
        "empty": 0,
        "decode_error": 0,
        "null": 0,
        "too_short": 0,
        "ok": 0
    }
    
    for row in cursor.fetchall():
        log_info = {
            "id": row[0],
            "path": row[1],
            "status_code": row[2],
            "body_length": row[3],
            "body_status": row[4],
            "preview": row[5]
        }
        logs.append(log_info)
        stats[row[4]] += 1
    
    conn.close()
    
    return {
        "message": "Diagnóstico de response bodies",
        "total_checked": len(logs),
        "stats": stats,
        "recommendations": {
            "empty": "Response body está vacío - revisar middleware",
            "decode_error": "Error al decodificar - puede ser binario",
            "null": "Response body es NULL - no se capturó",
            "too_short": "Response muy corto - verificar",
            "ok": "Todo bien ✅"
        },
        "recent_logs": logs
    }