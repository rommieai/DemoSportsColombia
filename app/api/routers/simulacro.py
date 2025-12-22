"""Endpoints para simulación de eventos de partidos con precisión de segundos"""
from fastapi import APIRouter, HTTPException, Query, Depends, Body, Path
from typing import List
from app.schemas.simulacro import (
    EventosResponse,
    UsuarioResponse,
    CrearUsuarioRequest,
    ActualizarTiempoRequest,
    ActualizarVelocidadRequest,
    EstadisticasSimulacroResponse,
    ConfiguracionSimulacroResponse,
    EventoPartido,
    TiempoActualInfo
)
from app.services.simulacro_service import (
    SimulacroService,
    get_simulacro_service
)

router = APIRouter(prefix="/simulacro", tags=["Simulacro"])


# ===== ENDPOINTS PRINCIPALES =====

@router.post("/usuarios/crear", response_model=UsuarioResponse)
async def crear_usuario(
    request: CrearUsuarioRequest = Body(...),
    service: SimulacroService = Depends(get_simulacro_service)
):
    """
    Registra un nuevo usuario en el simulacro con tiempo preciso.
    
    **Args:**
    - **usuario_id**: ID único del usuario (ej: "user_123", "sesion_abc")
    - **tiempo_inicial_minuto**: Minuto inicial del partido (0-120)
    - **tiempo_inicial_segundo**: Segundo inicial (0-59)
    - **velocidad**: Velocidad de simulación (1.0 = tiempo real, 2.0 = doble velocidad)
    
    **Ejemplo:**
    ```json
    {
        "usuario_id": "user_123",
        "tiempo_inicial_minuto": 80,
        "tiempo_inicial_segundo": 45,
        "velocidad": 1.0
    }
    ```
    
    **Nota**: Si el usuario ya existe, se actualizará su configuración.
    """
    try:
        usuario = service.crear_usuario(
            usuario_id=request.usuario_id,
            tiempo_inicial_segundos=request.tiempo_inicial_segundos,
            velocidad=request.velocidad
        )
        
        tiempo_info = service._formato_tiempo(usuario.tiempo_actual_segundos)
        
        return UsuarioResponse(
            usuario_id=usuario.usuario_id,
            tiempo_actual=tiempo_info,
            velocidad=usuario.velocidad,
            ultimo_request=usuario.ultimo_request,
            eventos_mostrados_count=len(usuario.eventos_mostrados),
            mensaje=f"Usuario '{usuario.usuario_id}' registrado. Tiempo inicial: {tiempo_info.formato}"
        )
    
    except Exception as e:
        raise HTTPException(500, f"Error al crear usuario: {str(e)}")


@router.get("/eventos/{usuario_id}", response_model=EventosResponse)
async def obtener_eventos(
    usuario_id: str = Path(..., description="ID del usuario"),
    service: SimulacroService = Depends(get_simulacro_service)
):
    """
    Obtiene los eventos del partido para un usuario específico.
    
    **Comportamiento:**
    1. Verifica que hayan pasado 5 segundos desde el último request
    2. Avanza el tiempo del usuario según su velocidad
    3. Retorna eventos que ocurrieron hasta el tiempo actual y no han sido mostrados
    
    **Rate Limit:** 1 request cada 5 segundos por usuario
    
    **Ejemplo de uso desde frontend:**
    ```javascript
    // Hacer request cada 5 segundos
    setInterval(async () => {
        const response = await fetch('/simulacro/eventos/user_123');
        const data = await response.json();
        
        if (data.eventos.length > 0) {
            console.log('Nuevos eventos:', data.eventos);
            data.eventos.forEach(evento => {
                console.log(`[${evento.minuto}:${evento.segundo}] ${evento.jugador} - ${evento.detalle}`);
            });
        }
        
        console.log(`Tiempo actual: ${data.tiempo_actual.formato}`);
    }, 5000);
    ```
    
    **Velocidades:**
    - 1.0 = Tiempo real (5 segundos reales = 5 segundos de partido)
    - 2.0 = Doble velocidad (5 segundos reales = 10 segundos de partido)
    - 0.5 = Media velocidad (5 segundos reales = 2.5 segundos de partido)
    """
    try:
        # Verificar rate limit (5 segundos)
        puede_hacer_request, mensaje_error = service.verificar_puede_hacer_request(usuario_id)
        if not puede_hacer_request:
            raise HTTPException(429, mensaje_error)
        
        # Obtener eventos
        eventos, usuario = service.obtener_eventos(usuario_id)
        
        tiempo_info = service._formato_tiempo(usuario.tiempo_actual_segundos)
        
        mensaje = None
        if len(eventos) > 0:
            mensaje = f"Se encontraron {len(eventos)} evento(s) nuevo(s) en {tiempo_info.formato}"
        elif usuario.tiempo_actual_segundos >= service.duracion_partido_segundos:
            mensaje = "Partido finalizado. Sin más eventos."
        else:
            mensaje = f"Sin eventos nuevos. Tiempo: {tiempo_info.formato}"
        
        return EventosResponse(
            usuario_id=usuario.usuario_id,
            tiempo_actual=tiempo_info,
            eventos=eventos,
            proximo_request_segundos=5,
            mensaje=mensaje
        )
    
    except ValueError as e:
        raise HTTPException(404, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al obtener eventos: {str(e)}")


# ===== ENDPOINTS DE GESTIÓN DE USUARIOS =====

@router.get("/usuarios/{usuario_id}", response_model=UsuarioResponse)
async def obtener_info_usuario(
    usuario_id: str = Path(..., description="ID del usuario"),
    service: SimulacroService = Depends(get_simulacro_service)
):
    """
    Obtiene información detallada de un usuario registrado.
    
    **Retorna:**
    - Tiempo actual (minuto:segundo)
    - Velocidad de simulación
    - Timestamp del último request
    - Cantidad de eventos ya mostrados
    """
    usuario = service.obtener_usuario(usuario_id)
    
    if not usuario:
        raise HTTPException(404, f"Usuario '{usuario_id}' no encontrado")
    
    tiempo_info = service._formato_tiempo(usuario.tiempo_actual_segundos)
    
    return UsuarioResponse(
        usuario_id=usuario.usuario_id,
        tiempo_actual=tiempo_info,
        velocidad=usuario.velocidad,
        ultimo_request=usuario.ultimo_request,
        eventos_mostrados_count=len(usuario.eventos_mostrados),
        mensaje=f"Usuario en {tiempo_info.formato} del partido (velocidad: {usuario.velocidad}x)"
    )


@router.put("/usuarios/{usuario_id}/tiempo", response_model=UsuarioResponse)
async def actualizar_tiempo_usuario(
    usuario_id: str = Path(..., description="ID del usuario"),
    request: ActualizarTiempoRequest = Body(...),
    service: SimulacroService = Depends(get_simulacro_service)
):
    """
    Actualiza manualmente el tiempo de un usuario con precisión de segundos.
    
    **Útil para:**
    - Adelantar o atrasar el tiempo de un usuario
    - Sincronizar usuarios que se desconectaron
    - Saltar a un momento específico del partido
    - Testing y debugging
    
    **Ejemplo:**
    ```json
    {
        "minuto": 89,
        "segundo": 23
    }
    ```
    """
    usuario = service.actualizar_tiempo(usuario_id, request.tiempo_total_segundos)
    
    if not usuario:
        raise HTTPException(404, f"Usuario '{usuario_id}' no encontrado")
    
    tiempo_info = service._formato_tiempo(usuario.tiempo_actual_segundos)
    
    return UsuarioResponse(
        usuario_id=usuario.usuario_id,
        tiempo_actual=tiempo_info,
        velocidad=usuario.velocidad,
        ultimo_request=usuario.ultimo_request,
        eventos_mostrados_count=len(usuario.eventos_mostrados),
        mensaje=f"Tiempo actualizado a {tiempo_info.formato}"
    )


@router.put("/usuarios/{usuario_id}/velocidad", response_model=UsuarioResponse)
async def actualizar_velocidad_usuario(
    usuario_id: str = Path(..., description="ID del usuario"),
    request: ActualizarVelocidadRequest = Body(...),
    service: SimulacroService = Depends(get_simulacro_service)
):
    """
    Actualiza la velocidad de simulación de un usuario.
    
    **Velocidades:**
    - **0.5x**: Media velocidad (más lento)
    - **1.0x**: Tiempo real (normal)
    - **2.0x**: Doble velocidad (rápido)
    - **5.0x**: Quintuplicada (muy rápido)
    
    **Útil para:**
    - Acelerar o ralentizar la simulación
    - Permitir "avance rápido" en momentos sin eventos
    - Testing con diferentes velocidades
    
    **Ejemplo:**
    ```json
    {
        "velocidad": 2.0
    }
    ```
    """
    usuario = service.actualizar_velocidad(usuario_id, request.velocidad)
    
    if not usuario:
        raise HTTPException(404, f"Usuario '{usuario_id}' no encontrado")
    
    tiempo_info = service._formato_tiempo(usuario.tiempo_actual_segundos)
    
    return UsuarioResponse(
        usuario_id=usuario.usuario_id,
        tiempo_actual=tiempo_info,
        velocidad=usuario.velocidad,
        ultimo_request=usuario.ultimo_request,
        eventos_mostrados_count=len(usuario.eventos_mostrados),
        mensaje=f"Velocidad actualizada a {usuario.velocidad}x"
    )


@router.post("/usuarios/{usuario_id}/reiniciar", response_model=UsuarioResponse)
async def reiniciar_usuario(
    usuario_id: str = Path(..., description="ID del usuario"),
    service: SimulacroService = Depends(get_simulacro_service)
):
    """
    Reinicia el estado de un usuario (tiempo a 00:00, eventos borrados).
    
    **Útil para:**
    - Permitir al usuario volver a ver el partido desde el inicio
    - Limpiar estado después de un partido
    - Reset completo del usuario
    """
    usuario = service.reiniciar_usuario(usuario_id)
    
    if not usuario:
        raise HTTPException(404, f"Usuario '{usuario_id}' no encontrado")
    
    tiempo_info = service._formato_tiempo(usuario.tiempo_actual_segundos)
    
    return UsuarioResponse(
        usuario_id=usuario.usuario_id,
        tiempo_actual=tiempo_info,
        velocidad=usuario.velocidad,
        ultimo_request=usuario.ultimo_request,
        eventos_mostrados_count=len(usuario.eventos_mostrados),
        mensaje="Usuario reiniciado exitosamente"
    )


@router.delete("/usuarios/{usuario_id}", response_model=dict)
async def eliminar_usuario(
    usuario_id: str = Path(..., description="ID del usuario"),
    service: SimulacroService = Depends(get_simulacro_service)
):
    """
    Elimina un usuario del simulacro.
    
    **Útil para:**
    - Limpiar usuarios inactivos
    - Liberar memoria
    - Gestión de sesiones
    """
    success = service.eliminar_usuario(usuario_id)
    
    if not success:
        raise HTTPException(404, f"Usuario '{usuario_id}' no encontrado")
    
    return {
        "mensaje": f"Usuario '{usuario_id}' eliminado exitosamente"
    }


@router.get("/usuarios/{usuario_id}/proximos-eventos", response_model=List[EventoPartido])
async def obtener_proximos_eventos(
    usuario_id: str = Path(..., description="ID del usuario"),
    cantidad: int = Query(3, ge=1, le=10, description="Cantidad de eventos a retornar"),
    service: SimulacroService = Depends(get_simulacro_service)
):
    """
    Obtiene los próximos N eventos que verá el usuario.
    
    **Útil para:**
    - Preview de próximos eventos
    - Mostrar "Próximamente" en la UI
    - Planning y anticipación
    
    **Ejemplo de respuesta:**
    ```json
    [
        {
            "minuto": 86,
            "segundo": 42,
            "equipo": "Colombia",
            "jugador": "Jefferson Lerma",
            "tipo": "Card",
            "detalle": "Yellow Card"
        }
    ]
    ```
    """
    usuario = service.obtener_usuario(usuario_id)
    if not usuario:
        raise HTTPException(404, f"Usuario '{usuario_id}' no encontrado")
    
    proximos = service.obtener_proximos_eventos(usuario_id, cantidad)
    return proximos


# ===== ENDPOINTS DE INFORMACIÓN =====

@router.get("/estadisticas", response_model=EstadisticasSimulacroResponse)
async def obtener_estadisticas(
    service: SimulacroService = Depends(get_simulacro_service)
):
    """
    Obtiene estadísticas generales del simulacro.
    
    **Retorna:**
    - Total de usuarios registrados
    - Usuarios activos (con request en últimos 30 segundos)
    - Total de eventos disponibles
    - Lista completa de eventos con sus tiempos precisos
    """
    stats = service.obtener_estadisticas()
    
    return EstadisticasSimulacroResponse(
        total_usuarios=stats["total_usuarios"],
        usuarios_activos=stats["usuarios_activos"],
        eventos_totales=stats["eventos_totales"],
        eventos_disponibles=stats["eventos_disponibles"]
    )


@router.get("/configuracion", response_model=ConfiguracionSimulacroResponse)
async def obtener_configuracion(
    service: SimulacroService = Depends(get_simulacro_service)
):
    """
    Obtiene la configuración actual del simulacro.
    
    **Retorna:**
    - Intervalo de request (5 segundos)
    - Duración del partido (120 minutos / 7200 segundos)
    - Lista de todos los eventos con minutos y segundos exactos
    """
    config = service.obtener_configuracion()
    
    return ConfiguracionSimulacroResponse(
        intervalo_request_segundos=config["intervalo_request_segundos"],
        duracion_partido_minutos=config["duracion_partido_minutos"],
        duracion_partido_segundos=config["duracion_partido_segundos"],
        total_eventos=config["total_eventos"],
        eventos=config["eventos"]
    )


@router.get("/health", response_model=dict)
async def verificar_salud(
    service: SimulacroService = Depends(get_simulacro_service)
):
    """
    Verifica que el servicio de simulacro esté funcionando.
    """
    stats = service.obtener_estadisticas()
    
    return {
        "status": "healthy",
        "servicio": "Simulacro de Eventos (con segundos)",
        "total_usuarios": stats["total_usuarios"],
        "total_eventos": stats["eventos_totales"],
        "precision": "Segundos",
        "mensaje": "Servicio funcionando correctamente"
    }